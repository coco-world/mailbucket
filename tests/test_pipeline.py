import csv
import json
import mailbox
from concurrent.futures import ThreadPoolExecutor

import pytest

from mailbucket.config import ExportOptions, RunConfig
from mailbucket.pipeline import execute
from mailbucket.search.matcher import parse_csv
from mailbucket.utils.hashing import file_sha256


def config(tmp_path, make_mail):
    source = tmp_path / "archive.mbox"
    box = mailbox.mbox(source)
    box.add(make_mail(date="Mon, 14 Sep 2026 08:00:00 +0200", message_id="<late>"))
    box.add(make_mail(date="Sun, 13 Sep 2026 08:00:00 +0200", message_id="<early>"))
    box.add(make_mail(date="Sun, 13 Sep 2026 08:00:00 +0200", message_id="<early>"))
    box.add(make_mail(date=None, message_id="<missing>"))
    box.close()
    return RunConfig(
        [source],
        parse_csv("term,bucket\n345678,A\nMustermann,B\nProjekt Alpha,B"),
        tmp_path / "out",
        "run",
        export=ExportOptions(timestamp_names=True),
    )


def test_dry_export_sort_manifest_and_no_overwrite(tmp_path, make_mail, monkeypatch):
    cfg = config(tmp_path, make_mail)
    cfg.export_workers = 1  # keep the monkeypatched call counter in this process
    dry = execute(cfg, dry_run=True)
    assert dry.stats.analyzed == 4 and dry.stats.duplicates == 1
    assert dry.stats.hits == {"A": 3, "B": 3}
    assert not cfg.output_dir.exists()
    from mailbucket import pipeline

    original = pipeline.render_email
    calls = []

    def render(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(pipeline, "render_email", render)
    result = execute(cfg)
    assert result.stats.exported == 6 and result.stats.errors == 0
    assert len(calls) == 3
    with (result.output / "_manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    a = [row for row in rows if row["bucket"] == "A"]
    assert [r["message_id"] for r in a] == ["<early>", "<late>", "<missing>"]
    assert a[0]["pdf_file"] == "A/A_0001_20260913_080000.pdf"
    assert a[-1]["date_status"] == "missing_or_invalid"
    for row in rows:
        assert row["pdf_sha256"] == file_sha256(result.output / row["pdf_file"])
    assert rows[0]["pdf_sha256"] == rows[1]["pdf_sha256"]
    assert json.loads((result.output / "_run.json").read_text())["status"] == "complete"
    assert (result.output / "_run.log").exists()
    with pytest.raises(FileExistsError):
        execute(cfg)


def test_keep_duplicates(tmp_path, make_mail):
    cfg = config(tmp_path, make_mail)
    cfg.deduplicate = False
    result = execute(cfg, dry_run=True)
    assert result.stats.hits == {"A": 4, "B": 4}
    assert result.stats.duplicates == 1 and result.stats.skipped_duplicates == 0


def test_bad_source_continues(tmp_path, make_mail):
    cfg = config(tmp_path, make_mail)
    corrupt = tmp_path / "bad.zip"
    corrupt.write_bytes(b"broken")
    cfg.sources.insert(0, corrupt)
    result = execute(cfg)
    assert result.stats.exported == 6 and result.stats.errors == 1
    assert json.loads((result.output / "_run.json").read_text())["status"] == "complete_with_errors"


def test_bad_run_name(tmp_path, make_mail):
    cfg = config(tmp_path, make_mail)
    cfg.run_name = "../escape"
    with pytest.raises(ValueError):
        execute(cfg)


def test_dry_run_never_renders(tmp_path, make_mail, monkeypatch):
    from mailbucket import pipeline

    def forbidden(*args):
        raise AssertionError("Dry run rendered a PDF")

    monkeypatch.setattr(pipeline, "render_email", forbidden)
    result = execute(config(tmp_path, make_mail), dry_run=True)
    assert result.stats.errors == 0 and result.output is None


def test_multiple_sources_deduplicate(tmp_path, make_mail):
    cfg = config(tmp_path, make_mail)
    other = tmp_path / "copy.eml"
    other.write_bytes(make_mail(message_id="<early>").as_bytes())
    cfg.sources.append(other)
    result = execute(cfg, dry_run=True)
    assert result.stats.duplicates == 2
    assert result.stats.hits == {"A": 3, "B": 3}


def test_invalid_date_goes_to_manifest(tmp_path, make_mail):
    source = tmp_path / "bad-date.eml"
    raw = make_mail(date=None).as_bytes()
    source.write_bytes(b"Date: this is not a date\n" + raw)
    cfg = RunConfig([source], parse_csv("term,bucket\n345678,A"), tmp_path / "out", "run")
    result = execute(cfg)
    assert result.stats.exported == 1 and result.stats.warnings == 1
    with (result.output / "_manifest.csv").open(encoding="utf-8") as stream:
        assert next(csv.DictReader(stream))["date_status"] == "missing_or_invalid"


def test_no_hit_creates_no_output_folder(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    source.write_bytes(make_mail(subject="Kein Treffer").as_bytes())
    config = RunConfig(
        [source],
        parse_csv("term,bucket\nNichtVorhanden,A"),
        tmp_path / "new-output-root",
        "run",
    )

    result = execute(config)

    assert result.output is None
    assert result.stats.exported == 0
    assert not config.output_dir.exists()


def test_only_hit_buckets_get_excel_csv(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    source.write_bytes(
        make_mail(
            subject="Alpha",
            body="Erste Zeile; mit Semikolon\nZweite Zeile mit Umlaut ä",
        ).as_bytes()
    )
    config = RunConfig(
        [source],
        parse_csv("term,bucket\nAlpha,Treffer\nNichtVorhanden,Leer"),
        tmp_path / "out",
        "run",
    )

    result = execute(config)

    bucket = result.output / "Treffer"
    csv_path = bucket / "Treffer.csv"
    assert bucket.is_dir()
    assert len(list(bucket.glob("*.pdf"))) == 1
    assert not (result.output / "Leer").exists()
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";")
        rows = list(reader)
    assert reader.fieldnames == ["Datum", "Uhrzeit", "von", "an", "Text"]
    assert len(rows) == 1
    assert rows[0]["Datum"] == "14.09.2026"
    assert rows[0]["Uhrzeit"] == "08:31:42"
    assert "Alice Müller" in rows[0]["von"]
    assert "bob@example.com" in rows[0]["an"]
    assert "Erste Zeile; mit Semikolon\nZweite Zeile mit Umlaut ä" in rows[0]["Text"]


def test_progress_reports_bytes_timing_and_worker_counts(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    source.write_bytes(make_mail(subject="Alpha").as_bytes())
    cfg = RunConfig(
        [source],
        parse_csv("term,bucket\nAlpha,A"),
        tmp_path / "out",
        "run",
        search_workers=2,
        export_workers=1,
    )
    updates = []

    execute(cfg, dry_run=True, on_progress=updates.append)

    scan = [update for update in updates if update.stage == "scan"]
    assert scan[-1].processed_bytes == source.stat().st_size
    assert scan[-1].total_bytes == source.stat().st_size
    assert scan[-1].elapsed_seconds >= 0
    assert scan[-1].search_workers == 2 and scan[-1].export_workers == 1
    assert updates[-1].stage == "complete"


def test_worker_limits_are_validated(tmp_path, make_mail):
    cfg = config(tmp_path, make_mail)
    cfg.search_workers = 0
    with pytest.raises(ValueError, match="Such-Worker"):
        cfg.validate()
    cfg.search_workers = 1
    cfg.export_workers = 99
    with pytest.raises(ValueError, match="Ablage-Worker"):
        cfg.validate()


def test_parallel_search_runs_from_ui_background_thread(tmp_path, make_mail):
    source = tmp_path / "parallel.mbox"
    box = mailbox.mbox(source)
    box.add(make_mail(subject="Alpha", message_id="<one>"))
    box.add(make_mail(subject="Alpha", message_id="<two>"))
    box.close()
    cfg = RunConfig(
        [source],
        parse_csv("term,bucket\nAlpha,A"),
        tmp_path / "out",
        "run",
        search_workers=2,
        export_workers=1,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(execute, cfg, dry_run=True).result(timeout=20)

    assert result.stats.analyzed == 2
    assert result.stats.hits == {"A": 2}
