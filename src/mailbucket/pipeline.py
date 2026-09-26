"""Streaming scan, disk-backed hit spool, deterministic sorting, reusable PDF rendering."""

import json
import logging
import pickle
import shutil
import tempfile
import threading
from collections import Counter, deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from time import monotonic
from uuid import uuid4

from mailbucket.config import RunConfig
from mailbucket.export.attachments import merge_attachments, save_originals
from mailbucket.export.bucket_csv import bucket_row, open_bucket_csv
from mailbucket.export.footer import apply_footer
from mailbucket.export.manifest import open_manifest
from mailbucket.export.pdf_renderer import PdfContext, render_email
from mailbucket.export.run_metadata import write_metadata
from mailbucket.importers import estimate_source_bytes, iter_source
from mailbucket.index import IndexedMatch, IndexManager, IndexState
from mailbucket.models import NormalizedEmail
from mailbucket.search.dedup import dedup_key
from mailbucket.search.matcher import ContainsMatcher
from mailbucket.utils.dates import sort_key
from mailbucket.utils.filenames import safe_name, unique_names
from mailbucket.utils.hashing import sha256

log = logging.getLogger(__name__)
Progress = Callable[[str, int, int | None], None]
_RUN_ID: ContextVar[str | None] = ContextVar("mailbucket_run_id", default=None)
_PROCESS_MATCHER: ContainsMatcher | None = None


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
    mailbox: str
    date: datetime | None


@dataclass(frozen=True)
class ProgressUpdate:
    stage: str
    phase: str
    done: int
    total: int | None
    mailbox: str
    terms: str
    analyzed: int
    matched: int
    exported: int
    hits: dict[str, int]
    processed_bytes: int
    total_bytes: int | None
    work_done: int
    work_total: int | None
    elapsed_seconds: float
    rate: float | None
    rate_unit: str
    eta_seconds: float | None
    search_workers: int
    export_workers: int


@dataclass
class Result:
    stats: Stats
    output: Path | None
    messages: list[str]


@dataclass
class SearchTask:
    mail: NormalizedEmail
    dedup: str
    duplicate: bool
    skip: bool = False
    failed: bool = False


@dataclass
class SearchOutcome:
    task: SearchTask
    matches: dict[str, list[str]] = field(default_factory=dict)
    locations: dict[str, list[str]] = field(default_factory=dict)
    failed: bool = False
    logs: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class ExportJob:
    number: int
    hit: Hit
    targets: dict[str, tuple[Path, str, int]]
    export_time: datetime
    config: RunConfig
    output: Path


@dataclass
class ExportArtifact:
    bucket: str
    bucket_row: dict[str, str]
    manifest_row: dict


@dataclass
class ExportOutcome:
    job: ExportJob
    artifacts: list[ExportArtifact] = field(default_factory=list)
    attachment_errors: int = 0
    failed: bool = False
    logs: list[tuple[int, str]] = field(default_factory=list)


class RunLog(logging.Handler):
    """Capture one run, including replayed worker logs; stream and bound UI messages."""

    def __init__(self, path: Path, stats: Stats, run_id: str):
        super().__init__(logging.WARNING)
        self.run_id = run_id
        self.lock = threading.RLock()
        self.stream = path.open("w", encoding="utf-8")
        self.stats = stats
        self.messages: list[str] = []
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    def emit(self, record):
        if _RUN_ID.get() != self.run_id:
            return
        with self.lock:
            message = self.format(record)
            self.stream.write(message + "\n")
            self.stream.flush()
            if len(self.messages) < 100:
                self.messages.append(message)
            if record.levelno >= logging.ERROR:
                self.stats.errors += 1
            else:
                self.stats.warnings += 1

    def relocate(self, path: Path) -> None:
        """Move the scan log into an output folder once the first hit is known."""
        with self.lock:
            self.stream.flush()
            source = Path(self.stream.name)
            self.stream.close()
            shutil.move(source, path)
            self.stream = path.open("a", encoding="utf-8")

    def close(self):
        with self.lock:
            self.stream.close()
        super().close()


class _TaskLog(logging.Handler):
    """Collect worker-process warnings so the main process owns the run log."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.records: list[tuple[int, str]] = []
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        self.records.append((record.levelno, self.format(record)))


def _initialize_process_logging() -> None:
    """A child must never write through a RunLog inherited from the parent."""
    logger = logging.getLogger("mailbucket")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.WARNING)


def _initialize_search_process(matcher: ContainsMatcher) -> None:
    global _PROCESS_MATCHER
    _initialize_process_logging()
    _PROCESS_MATCHER = matcher


def _capture_worker_logs(callback: Callable[[], SearchOutcome | ExportOutcome]):
    logger = logging.getLogger("mailbucket")
    handler = _TaskLog()
    logger.addHandler(handler)
    try:
        outcome = callback()
        outcome.logs = handler.records
        return outcome
    finally:
        logger.removeHandler(handler)


def _search_mail_in_process(task: SearchTask) -> SearchOutcome:
    if _PROCESS_MATCHER is None:
        raise RuntimeError("Suchprozess wurde nicht initialisiert.")
    return _capture_worker_logs(lambda: _search_mail(task, _PROCESS_MATCHER))


def _export_hit_in_process(job: ExportJob) -> ExportOutcome:
    return _capture_worker_logs(lambda: _export_hit(job))


def _bounded_process_map(
    worker: Callable,
    items: Iterable,
    max_workers: int,
    *,
    serial_worker: Callable | None = None,
    initializer: Callable = _initialize_process_logging,
    initargs: tuple = (),
) -> Iterator:
    """Process in input order while keeping at most two tasks per worker in memory."""
    if max_workers == 1:
        yield from map(serial_worker or worker, items)
        return
    iterator = iter(items)
    pending = deque()
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=initializer,
        initargs=initargs,
    ) as executor:
        for _ in range(max_workers * 2):
            try:
                pending.append(executor.submit(worker, next(iterator)))
            except StopIteration:
                break
        while pending:
            yield pending.popleft().result()
            try:
                pending.append(executor.submit(worker, next(iterator)))
            except StopIteration:
                pass


def _replay_worker_logs(records: list[tuple[int, str]]) -> None:
    for level, message in records:
        log.log(level, message)


def _search_mail(task: SearchTask, matcher: ContainsMatcher) -> SearchOutcome:
    if task.failed or task.skip:
        return SearchOutcome(task, failed=task.failed)
    try:
        details = matcher.match_details(task.mail)
        return SearchOutcome(task, details.buckets, details.locations)
    except Exception:
        log.exception(
            "Nachricht konnte nicht verarbeitet werden: %s",
            task.mail.source_folder or task.mail.source_file,
        )
        return SearchOutcome(task, failed=True)


def _export_hit(job: ExportJob) -> ExportOutcome:
    """Render one matched message and all of its bucket variants independently."""
    hit = job.hit
    outcome = ExportOutcome(job)
    try:
        with hit.path.open("rb") as source:
            mail = pickle.load(source)
        all_terms = sorted({term for terms in hit.matches.values() for term in terms})
        content_key = None
        cached_pdf = None
        cached_final = None
        for bucket, matched in hit.matches.items():
            target, stem, bucket_index = job.targets[bucket]
            context = PdfContext(hit.locations, job.export_time, target.name)
            terms = matched if job.config.export.pdf.bucket_specific else all_terms
            key = (
                tuple(terms)
                if set(job.config.export.pdf.fields) & {"matched_terms", "match_locations"}
                else ()
            )
            if cached_pdf is None or content_key != key:
                pdf = render_email(mail, terms, job.config.export.pdf, context)
                cached_pdf, failures = merge_attachments(pdf, mail, job.config.export)
                if content_key is None:
                    outcome.attachment_errors += failures
                content_key = key
                cached_final = None
            if cached_final is None or job.config.export.pdf.bucket_specific:
                cached_final = apply_footer(cached_pdf, mail, terms, job.config.export.pdf, context)
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(cached_final)
            pdf_hash = sha256(cached_final)
            originals = save_originals(
                mail, target.parent / "attachments" / stem, job.config.export
            )
            for original in originals:
                if original["saved_file"]:
                    original["saved_file"] = (
                        (target.parent / "attachments" / stem / original["saved_file"])
                        .relative_to(job.output)
                        .as_posix()
                    )
            outcome.artifacts.append(
                ExportArtifact(
                    bucket,
                    bucket_row(mail),
                    {
                        "bucket": bucket,
                        "index": bucket_index,
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
                            {term: hit.locations[term] for term in matched}, ensure_ascii=False
                        ),
                        "pdf_file": target.relative_to(job.output).as_posix(),
                        "pdf_sha256": pdf_hash,
                        "attachment_count": len(mail.attachments),
                        "dedup_key": hit.dedup,
                        "date_status": "valid" if mail.date else "missing_or_invalid",
                        "raw_sha256": mail.raw_sha256,
                        "attachments": json.dumps(originals, ensure_ascii=False),
                    },
                )
            )
    except Exception:
        outcome.failed = True
        log.exception("Treffer konnte nicht vollständig exportiert werden: %s", hit.path.name)
    finally:
        hit.path.unlink(missing_ok=True)
    return outcome


def execute(
    config: RunConfig,
    *,
    dry_run: bool = False,
    progress: Progress | None = None,
    on_progress: Callable[[ProgressUpdate], None] | None = None,
) -> Result:
    """Run locally. Dry runs create no output; temporary source/spool files are cleaned up."""
    config.validate()
    run_id = uuid4().hex
    run_token = _RUN_ID.set(run_id)
    current_mailbox = ""
    current_terms = f"Alle {len(config.terms)} Suchbegriffe"
    matched_count = 0
    last_update = 0.0
    export_time = datetime.now().astimezone()
    run_started = monotonic()
    current_stage = ""
    stage_started = run_started
    stage_initial_work = 0
    processed_bytes = 0
    scan_total_bytes: int | None = None

    def notify(
        phase: str,
        done: int,
        total: int | None,
        *,
        stage: str,
        work_done: int | None = None,
        work_total: int | None = None,
        rate_unit: str = "items",
        throttle: bool = False,
    ) -> None:
        nonlocal current_stage, last_update, stage_initial_work, stage_started
        now = monotonic()
        if throttle and stage == current_stage and now - last_update < 0.1:
            return
        last_update = now
        measured_done = done if work_done is None else work_done
        measured_total = total if work_total is None else work_total
        if stage != current_stage:
            current_stage = stage
            stage_started = now
            stage_initial_work = measured_done
        stage_elapsed = now - stage_started
        completed_work = measured_done - stage_initial_work
        rate = (
            completed_work / stage_elapsed if stage_elapsed >= 0.25 and completed_work > 0 else None
        )
        eta = (
            max(0.0, (measured_total - measured_done) / rate)
            if rate and measured_total is not None and measured_total >= measured_done
            else None
        )
        if progress:
            progress(phase, done, total)
        if on_progress:
            on_progress(
                ProgressUpdate(
                    stage=stage,
                    phase=phase,
                    done=done,
                    total=total,
                    mailbox=current_mailbox,
                    terms=current_terms,
                    analyzed=stats.analyzed,
                    matched=matched_count,
                    exported=stats.exported,
                    hits=stats.hits.copy(),
                    processed_bytes=processed_bytes,
                    total_bytes=scan_total_bytes,
                    work_done=measured_done,
                    work_total=measured_total,
                    elapsed_seconds=now - run_started,
                    rate=rate,
                    rate_unit=rate_unit,
                    eta_seconds=eta,
                    search_workers=config.search_workers,
                    export_workers=config.export_workers,
                )
            )

    output = None
    planned_output = None
    if not dry_run:
        if safe_name(config.run_name) != config.run_name or not config.run_name.strip():
            raise ValueError("Laufname enthält unzulässige Zeichen oder ist zu lang.")
        planned_output = config.output_dir / config.run_name
        if planned_output.exists():
            raise FileExistsError(planned_output)
    stats = Stats(hits={t.bucket: 0 for t in config.terms})
    names = unique_names([t.bucket for t in config.terms])
    try:
        with tempfile.TemporaryDirectory(prefix="mailbucket-run-") as directory:
            temp = Path(directory)
            handler = RunLog(temp / "scan.log", stats, run_id)
            logger = logging.getLogger("mailbucket")
            logger.addHandler(handler)
            try:
                current_mailbox = str(config.sources[0])
                notify(
                    "Quellenumfang ermitteln",
                    0,
                    None,
                    stage="scan",
                    work_done=0,
                    work_total=None,
                    rate_unit="bytes",
                )
                try:
                    source_totals = [estimate_source_bytes(source) for source in config.sources]
                    if all(total is not None for total in source_totals):
                        scan_total_bytes = sum(total or 0 for total in source_totals)
                except OSError:
                    scan_total_bytes = None

                matcher = ContainsMatcher(config.terms, config.search_fields)
                seen: set[str] = set()
                hits: list[Hit] = []
                index_manager = IndexManager() if config.use_index else None

                def record_hit(
                    mail: NormalizedEmail,
                    key: str,
                    matches: dict[str, list[str]],
                    locations: dict[str, list[str]],
                ) -> None:
                    nonlocal current_mailbox, matched_count
                    matched_count += 1
                    current_mailbox = mail.source_folder or mail.source_file
                    for bucket in matches:
                        stats.hits[bucket] += 1
                    if not dry_run:
                        path = temp / f"{len(hits)}.mail"
                        # Only private, freshly created pickle files are ever read.
                        with path.open("wb") as stream:
                            pickle.dump(mail, stream, protocol=pickle.HIGHEST_PROTOCOL)
                        hits.append(
                            Hit(
                                path,
                                sort_key(mail),
                                key,
                                matches,
                                locations,
                                current_mailbox,
                                mail.date,
                            )
                        )

                def classic_tasks(source: Path) -> Iterator[SearchTask]:
                    nonlocal current_mailbox
                    try:
                        for mail in iter_source(source):
                            current_mailbox = mail.source_folder or mail.source_file
                            try:
                                key = dedup_key(mail)
                                duplicate = key in seen
                                if duplicate:
                                    stats.duplicates += 1
                                seen.add(key)
                                yield SearchTask(
                                    mail,
                                    key,
                                    duplicate,
                                    skip=duplicate and config.deduplicate,
                                )
                            except Exception:
                                log.exception(
                                    "Nachricht konnte nicht verarbeitet werden: %s",
                                    current_mailbox,
                                )
                                yield SearchTask(mail, "", False, failed=True)
                    except Exception:
                        log.exception("Quelle konnte nicht vollständig gelesen werden: %s", source)

                def scan_classically(source: Path) -> None:
                    nonlocal current_mailbox, processed_bytes
                    current_mailbox = str(source)
                    notify(
                        f"Quelle klassisch analysieren: {source.name}",
                        stats.analyzed,
                        None,
                        stage="scan",
                        work_done=processed_bytes,
                        work_total=scan_total_bytes,
                        rate_unit="bytes",
                    )
                    serial_search = partial(_search_mail, matcher=matcher)
                    outcomes = _bounded_process_map(
                        _search_mail_in_process,
                        classic_tasks(source),
                        config.search_workers,
                        serial_worker=serial_search,
                        initializer=_initialize_search_process,
                        initargs=(matcher,),
                    )
                    for outcome in outcomes:
                        _replay_worker_logs(outcome.logs)
                        task = outcome.task
                        mail = task.mail
                        stats.analyzed += 1
                        processed_bytes += max(0, mail.source_bytes)
                        current_mailbox = mail.source_folder or mail.source_file
                        if task.skip:
                            stats.skipped_duplicates += 1
                        elif not outcome.failed and outcome.matches:
                            record_hit(mail, task.dedup, outcome.matches, outcome.locations)
                        notify(
                            "Nachrichten parallel einlesen und durchsuchen",
                            stats.analyzed,
                            None,
                            stage="scan",
                            work_done=processed_bytes,
                            work_total=scan_total_bytes,
                            rate_unit="bytes",
                            throttle=True,
                        )

                def scan_indexed(source: Path) -> bool:
                    nonlocal current_mailbox, processed_bytes
                    if index_manager is None:
                        return False
                    current_mailbox = str(source)
                    info = index_manager.status(source)
                    if info.state != IndexState.CURRENT and config.auto_index:
                        notify(
                            f"Index vorbereiten: {source.name}",
                            0,
                            None,
                            stage="index_prepare",
                        )

                        def index_progress(update) -> None:
                            notify(
                                f"Index erstellen: {source.name}",
                                update.done,
                                None,
                                stage="index",
                                work_done=update.processed_bytes,
                                work_total=update.total_bytes,
                                rate_unit="bytes",
                                throttle=True,
                            )

                        try:
                            info = index_manager.build(source, index_progress)
                        except Exception:
                            log.warning(
                                "Index konnte nicht erstellt werden; klassische Suche wird verwendet: %s",
                                source,
                                exc_info=True,
                            )
                            return False
                    if info.state != IndexState.CURRENT:
                        return False
                    notify(
                        f"Lokalen Index durchsuchen: {source.name}",
                        0,
                        info.mail_count,
                        stage="index_search_prepare",
                    )

                    def search_progress(done: int, total: int) -> None:
                        notify(
                            f"Index-Kandidaten exakt prüfen: {source.name}",
                            done,
                            total,
                            stage="index_match",
                            throttle=True,
                        )

                    try:
                        indexed_matches = index_manager.search(
                            source,
                            config.terms,
                            config.search_fields,
                            search_progress,
                        )
                        records = index_manager.dedup_records(source)
                    except Exception:
                        log.warning(
                            "Indexsuche fehlgeschlagen; klassische Suche wird verwendet: %s",
                            source,
                            exc_info=True,
                        )
                        return False
                    by_id = {match.record_id: match for match in indexed_matches}
                    accepted: list[IndexedMatch] = []
                    seen_before = seen.copy()
                    analyzed_before = stats.analyzed
                    duplicates_before = stats.duplicates
                    skipped_before = stats.skipped_duplicates
                    for number, (record_id, key) in enumerate(records, 1):
                        stats.analyzed += 1
                        duplicate = key in seen
                        if duplicate:
                            stats.duplicates += 1
                        seen.add(key)
                        match = by_id.get(record_id)
                        if duplicate and config.deduplicate:
                            stats.skipped_duplicates += 1
                        elif match is not None:
                            accepted.append(match)
                        notify(
                            f"Lokalen Index durchsuchen: {source.name}",
                            number,
                            len(records),
                            stage="index_search",
                            throttle=True,
                        )
                    originals = {}
                    if accepted and not dry_run:
                        try:
                            originals = index_manager.load_original_matches(source, accepted)
                        except Exception:
                            log.exception(
                                "Indizierte Treffer konnten nicht aus der Quelle geladen werden: %s",
                                source,
                            )
                            seen.clear()
                            seen.update(seen_before)
                            stats.analyzed = analyzed_before
                            stats.duplicates = duplicates_before
                            stats.skipped_duplicates = skipped_before
                            return False
                    for match in accepted:
                        mail = originals.get(match.record_id, match.mail)
                        record_hit(mail, match.dedup, match.matches, match.locations)
                    processed_bytes += info.source_bytes
                    notify(
                        f"Lokalen Index durchsuchen: {source.name}",
                        len(records),
                        len(records),
                        stage="index_search",
                    )
                    return True

                for source in config.sources:
                    if not scan_indexed(source):
                        scan_classically(source)

                if scan_total_bytes is not None:
                    processed_bytes = scan_total_bytes
                notify(
                    "Nachrichten parallel einlesen und durchsuchen",
                    stats.analyzed,
                    None,
                    stage="scan",
                    work_done=processed_bytes,
                    work_total=scan_total_bytes,
                    rate_unit="bytes",
                )
                notify(
                    "Treffer sortieren",
                    stats.analyzed,
                    stats.analyzed,
                    stage="sort",
                )
                if planned_output and hits:
                    config.output_dir.mkdir(parents=True, exist_ok=True)
                    planned_output.mkdir(exist_ok=False)  # atomic reservation, never overwrite
                    output = planned_output
                    handler.relocate(output / "_run.log")
                    write_metadata(output / "_run.json", config, asdict(stats), names, "running")
                if output:
                    hits.sort(key=lambda hit: hit.key)
                    export_total = sum(stats.hits.values())
                    counts: Counter = Counter()
                    bucket_streams = {}
                    bucket_writers = {}
                    manifest_stream, manifest = open_manifest(output / "_manifest.csv")

                    def export_jobs() -> Iterator[ExportJob]:
                        for number, hit in enumerate(hits, 1):
                            targets = {}
                            for bucket in hit.matches:
                                counts[bucket] += 1
                                width = max(4, len(str(stats.hits[bucket])))
                                stem = f"{names[bucket]}_{counts[bucket]:0{width}d}"
                                if config.export.timestamp_names and hit.date:
                                    stem += hit.date.strftime("_%Y%m%d_%H%M%S")
                                target = output / names[bucket] / f"{stem}.pdf"
                                targets[bucket] = (target, stem, counts[bucket])
                            yield ExportJob(number, hit, targets, export_time, config, output)

                    notify(
                        "PDFs und Anhänge parallel erzeugen",
                        0,
                        export_total,
                        stage="export",
                    )
                    try:
                        export_outcomes = _bounded_process_map(
                            _export_hit_in_process,
                            export_jobs(),
                            config.export_workers,
                            serial_worker=_export_hit,
                        )
                        for outcome in export_outcomes:
                            _replay_worker_logs(outcome.logs)
                            current_mailbox = outcome.job.hit.mailbox
                            current_terms = ", ".join(
                                sorted(
                                    {
                                        term
                                        for terms in outcome.job.hit.matches.values()
                                        for term in terms
                                    }
                                )
                            )
                            stats.attachment_errors += outcome.attachment_errors
                            try:
                                for artifact in outcome.artifacts:
                                    bucket = artifact.bucket
                                    if bucket not in bucket_writers:
                                        bucket_dir = output / names[bucket]
                                        bucket_stream, bucket_writer = open_bucket_csv(
                                            bucket_dir / f"{names[bucket]}.csv"
                                        )
                                        bucket_streams[bucket] = bucket_stream
                                        bucket_writers[bucket] = bucket_writer
                                    bucket_writers[bucket].writerow(artifact.bucket_row)
                                    manifest.writerow(artifact.manifest_row)
                                    stats.exported += 1
                                    notify(
                                        "PDFs und Anhänge parallel erzeugen",
                                        stats.exported,
                                        export_total,
                                        stage="export",
                                        rate_unit="pdfs",
                                    )
                            except Exception:
                                log.exception(
                                    "Manifest/CSV konnte nicht vollständig geschrieben werden: %s",
                                    outcome.job.hit.path.name,
                                )
                    finally:
                        manifest_stream.close()
                        for bucket_stream in bucket_streams.values():
                            bucket_stream.close()
                    notify(
                        "Manifest und Laufdaten schreiben",
                        len(hits),
                        len(hits),
                        stage="finalize",
                    )
                    write_metadata(
                        output / "_run.json",
                        config,
                        asdict(stats),
                        names,
                        "complete_with_errors" if stats.errors else "complete",
                    )
                    with handler.lock:
                        handler.stream.write(
                            "Lauf abgeschlossen: "
                            + json.dumps(asdict(stats), ensure_ascii=False)
                            + "\n"
                        )
                        handler.stream.flush()
                notify(
                    "Abgeschlossen",
                    stats.analyzed,
                    stats.analyzed,
                    stage="complete",
                )
                return Result(stats, output, handler.messages.copy())
            except BaseException:
                if output:
                    write_metadata(output / "_run.json", config, asdict(stats), names, "failed")
                raise
            finally:
                logger.removeHandler(handler)
                handler.close()
    finally:
        _RUN_ID.reset(run_token)
