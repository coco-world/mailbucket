"""Streaming scan, disk-backed hit spool, deterministic sorting, reusable PDF rendering."""

import json
import logging
import pickle
import tempfile
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from time import monotonic

from mailbucket.config import RunConfig
from mailbucket.export.attachments import merge_attachments, save_originals
from mailbucket.export.footer import apply_footer
from mailbucket.export.manifest import open_manifest
from mailbucket.export.pdf_renderer import PdfContext, render_email
from mailbucket.export.run_metadata import write_metadata
from mailbucket.importers import iter_source
from mailbucket.search.dedup import dedup_key
from mailbucket.search.matcher import ContainsMatcher
from mailbucket.utils.dates import sort_key
from mailbucket.utils.filenames import safe_name, unique_names
from mailbucket.utils.hashing import sha256

log = logging.getLogger(__name__)
Progress = Callable[[str, int, int | None], None]


@dataclass
class Stats:
    analyzed: int = 0
    duplicates: int = 0
    skipped_duplicates: int = 0
    exported: int = 0
    attachment_errors: int = 0
    errors: int = 0
    warnings: int = 0
    hits: dict[str, int] = field(default_factory=dict)


@dataclass
class Hit:
    path: Path
    key: tuple
    dedup: str
    matches: dict[str, list[str]]
    locations: dict[str, list[str]]


@dataclass(frozen=True)
class ProgressUpdate:
    phase: str
    done: int
    total: int | None
    mailbox: str
    terms: str
    analyzed: int
    matched: int
    exported: int
    hits: dict[str, int]


@dataclass
class Result:
    stats: Stats
    output: Path | None
    messages: list[str]


class RunLog(logging.Handler):
    """Capture only the current worker thread; stream full logs and bound UI messages."""

    def __init__(self, path: Path, stats: Stats):
        super().__init__(logging.WARNING)
        self.thread_id = threading.get_ident()
        self.stream = path.open("w", encoding="utf-8")
        self.stats = stats
        self.messages: list[str] = []
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    def emit(self, record):
        if record.thread != self.thread_id:
            return
        message = self.format(record)
        self.stream.write(message + "\n")
        self.stream.flush()
        if len(self.messages) < 100:
            self.messages.append(message)
        if record.levelno >= logging.ERROR:
            self.stats.errors += 1
        else:
            self.stats.warnings += 1

    def close(self):
        self.stream.close()
        super().close()


def execute(
    config: RunConfig,
    *,
    dry_run: bool = False,
    progress: Progress | None = None,
    on_progress: Callable[[ProgressUpdate], None] | None = None,
) -> Result:
    """Run locally. Dry runs create no output; temporary source/spool files are cleaned up."""
    config.validate()
    current_mailbox = ""
    current_terms = f"Alle {len(config.terms)} Suchbegriffe"
    matched_count = 0
    last_update = 0.0
    export_time = datetime.now().astimezone()

    def notify(phase: str, done: int, total: int | None, *, throttle: bool = False) -> None:
        nonlocal last_update
        now = monotonic()
        if throttle and now - last_update < 0.1:
            return
        last_update = now
        if progress:
            progress(phase, done, total)
        if on_progress:
            on_progress(
                ProgressUpdate(
                    phase,
                    done,
                    total,
                    current_mailbox,
                    current_terms,
                    stats.analyzed,
                    matched_count,
                    stats.exported,
                    stats.hits.copy(),
                )
            )

    output = None
    if not dry_run:
        if safe_name(config.run_name) != config.run_name or not config.run_name.strip():
            raise ValueError("Laufname enthält unzulässige Zeichen oder ist zu lang.")
        config.output_dir.mkdir(parents=True, exist_ok=True)
        output = config.output_dir / config.run_name
        output.mkdir(exist_ok=False)  # atomic reservation, never overwrite another run
    stats = Stats(hits={t.bucket: 0 for t in config.terms})
    names = unique_names([t.bucket for t in config.terms])
    with tempfile.TemporaryDirectory(prefix="mailbucket-run-") as directory:
        temp = Path(directory)
        handler = RunLog(output / "_run.log" if output else temp / "scan.log", stats)
        logger = logging.getLogger("mailbucket")
        logger.addHandler(handler)
        try:
            if output:
                write_metadata(output / "_run.json", config, asdict(stats), names, "running")
            matcher = ContainsMatcher(config.terms, config.search_fields)
            seen: set[str] = set()
            hits: list[Hit] = []
            for source in config.sources:
                current_mailbox = str(source)
                notify(f"Quelle analysieren: {source.name}", stats.analyzed, None)
                try:
                    for mail in iter_source(source):
                        stats.analyzed += 1
                        current_mailbox = mail.source_folder or mail.source_file
                        try:
                            key = dedup_key(mail)
                            duplicate = key in seen
                            if duplicate:
                                stats.duplicates += 1
                            seen.add(key)
                            if duplicate and config.deduplicate:
                                stats.skipped_duplicates += 1
                            else:
                                details = matcher.match_details(mail)
                                matches = details.buckets
                                if matches:
                                    matched_count += 1
                                    for bucket in matches:
                                        stats.hits[bucket] += 1
                                    if not dry_run:
                                        path = temp / f"{len(hits)}.mail"
                                        # Only our own private, freshly created pickle files are ever read.
                                        with path.open("wb") as stream:
                                            pickle.dump(
                                                mail, stream, protocol=pickle.HIGHEST_PROTOCOL
                                            )
                                        hits.append(
                                            Hit(
                                                path,
                                                sort_key(mail),
                                                key,
                                                matches,
                                                details.locations,
                                            )
                                        )
                        except Exception:
                            log.exception(
                                "Nachricht konnte nicht verarbeitet werden: %s", current_mailbox
                            )
                        notify(
                            "Nachrichten einlesen und durchsuchen",
                            stats.analyzed,
                            None,
                            throttle=True,
                        )
                except Exception:
                    log.exception("Quelle konnte nicht vollständig gelesen werden: %s", source)
            notify("Treffer sortieren", stats.analyzed, stats.analyzed)
            if output:
                hits.sort(key=lambda hit: hit.key)
                for name in names.values():
                    (output / name).mkdir()
                counts: Counter = Counter()
                stream, manifest = open_manifest(output / "_manifest.csv")
                try:
                    for number, hit in enumerate(hits, 1):
                        notify("PDFs erzeugen", number - 1, len(hits))
                        try:
                            with hit.path.open("rb") as source:
                                mail = pickle.load(source)
                            current_mailbox = mail.source_folder or mail.source_file
                            all_terms = sorted({t for terms in hit.matches.values() for t in terms})
                            # Render only when visible bucket-specific content changes. Footer-only
                            # variations reuse the same memo and original attachment pages.
                            content_key = None
                            cached_pdf = None
                            cached_final = None
                            for bucket, matched in hit.matches.items():
                                current_terms = ", ".join(matched)
                                counts[bucket] += 1
                                width = max(4, len(str(stats.hits[bucket])))
                                stem = f"{names[bucket]}_{counts[bucket]:0{width}d}"
                                if config.export.timestamp_names and mail.date:
                                    stem += mail.date.strftime("_%Y%m%d_%H%M%S")
                                target = output / names[bucket] / f"{stem}.pdf"
                                context = PdfContext(hit.locations, export_time, target.name)
                                terms = matched if config.export.pdf.bucket_specific else all_terms
                                key = (
                                    tuple(terms)
                                    if set(config.export.pdf.fields)
                                    & {"matched_terms", "match_locations"}
                                    else ()
                                )
                                if cached_pdf is None or content_key != key:
                                    pdf = render_email(mail, terms, config.export.pdf, context)
                                    notify("Anhänge verarbeiten", number - 1, len(hits))
                                    cached_pdf, failures = merge_attachments(
                                        pdf, mail, config.export
                                    )
                                    if content_key is None:
                                        stats.attachment_errors += failures
                                    content_key = key
                                    cached_final = None
                                if cached_final is None or config.export.pdf.bucket_specific:
                                    cached_final = apply_footer(
                                        cached_pdf, mail, terms, config.export.pdf, context
                                    )
                                target.write_bytes(cached_final)
                                pdf_hash = sha256(cached_final)
                                originals = save_originals(
                                    mail, target.parent / "attachments" / stem, config.export
                                )
                                for original in originals:
                                    if original["saved_file"]:
                                        original["saved_file"] = (
                                            (
                                                target.parent
                                                / "attachments"
                                                / stem
                                                / original["saved_file"]
                                            )
                                            .relative_to(output)
                                            .as_posix()
                                        )
                                manifest.writerow(
                                    {
                                        "bucket": bucket,
                                        "index": counts[bucket],
                                        "date": mail.date.isoformat() if mail.date else "",
                                        "from": mail.sender,
                                        "to": "; ".join(mail.to),
                                        "cc": "; ".join(mail.cc),
                                        "subject": mail.subject,
                                        "message_id": mail.message_id,
                                        "source_type": mail.source_type,
                                        "source_file": mail.source_file,
                                        "source_folder": mail.source_folder,
                                        "source_index": mail.source_index,
                                        "gmail_labels": json.dumps(mail.labels, ensure_ascii=False),
                                        "matched_terms": json.dumps(matched, ensure_ascii=False),
                                        "match_locations": json.dumps(
                                            {t: hit.locations[t] for t in matched},
                                            ensure_ascii=False,
                                        ),
                                        "pdf_file": target.relative_to(output).as_posix(),
                                        "pdf_sha256": pdf_hash,
                                        "attachment_count": len(mail.attachments),
                                        "dedup_key": hit.dedup,
                                        "date_status": "valid"
                                        if mail.date
                                        else "missing_or_invalid",
                                        "raw_sha256": mail.raw_sha256,
                                        "attachments": json.dumps(originals, ensure_ascii=False),
                                    }
                                )
                                stats.exported += 1
                                notify("PDFs exportieren", stats.exported, sum(stats.hits.values()))
                        except Exception:
                            log.exception(
                                "Treffer konnte nicht vollständig exportiert werden: %s",
                                hit.path.name,
                            )
                        finally:
                            hit.path.unlink(missing_ok=True)
                finally:
                    stream.close()
                notify("Manifest schreiben", len(hits), len(hits))
                write_metadata(
                    output / "_run.json",
                    config,
                    asdict(stats),
                    names,
                    "complete_with_errors" if stats.errors else "complete",
                )
                handler.stream.write(
                    "Lauf abgeschlossen: " + json.dumps(asdict(stats), ensure_ascii=False) + "\n"
                )
            notify("Abgeschlossen", stats.analyzed, stats.analyzed)
            return Result(stats, output, handler.messages.copy())
        except BaseException:
            if output:
                write_metadata(output / "_run.json", config, asdict(stats), names, "failed")
            raise
        finally:
            logger.removeHandler(handler)
            handler.close()
