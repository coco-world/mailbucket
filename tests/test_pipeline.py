import csv
import json
import mailbox

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
