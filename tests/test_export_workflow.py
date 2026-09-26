import csv
import json
import mailbox
import zipfile

from pypdf import PdfReader

from mailbucket.config import ExportOptions, PdfOptions, RunConfig
from mailbucket.export.pdf_renderer import document
from mailbucket.pipeline import execute
from mailbucket.search.matcher import parse_csv, parse_terms
from mailbucket.utils.hashing import file_sha256


def test_failed_message_does_not_skip_remaining_mailbox(tmp_path, make_mail, monkeypatch):
    from mailbucket.search.matcher import ContainsMatcher

    source = tmp_path / "source.mbox"
    box = mailbox.mbox(source)
    box.add(make_mail(subject="Broken", message_id="<broken@example.com>"))
    box.add(make_mail(subject="Alpha", message_id="<good@example.com>"))
    box.close()
    original = ContainsMatcher.match_details

    def match(self, mail):
        if mail.subject == "Broken":
            raise ValueError("Synthetic processing failure")
        return original(self, mail)

    monkeypatch.setattr(ContainsMatcher, "match_details", match)
    result = execute(
        RunConfig(
            [source],
            parse_terms("Alpha"),
            tmp_path / "out",
            "run",
            search_workers=1,
        )
    )
    assert result.stats.analyzed == 2
    assert result.stats.errors == 1
    assert result.stats.exported == 1


def test_pack_search_and_bucket_specific_export(tmp_path, make_mail):
    box = mailbox.mbox(tmp_path / "source.mbox")
    msg = make_mail(subject="Alpha/Beta", body="Both Alpha and Beta")
    original = document("INVOICE", [("Marker", "AttachmentOnly")])
    msg.add_attachment(original, maintype="application", subtype="pdf", filename="invoice.pdf")
    box.add(msg)
    box.add(msg)
    box.close()
    archive = tmp_path / "takeout.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(tmp_path / "source.mbox", "takeout/unusual-folder/mail.mbox")
    config = RunConfig(
        [archive],
        parse_csv("term,bucket\nAlpha,A\nBeta,B"),
        tmp_path / "export",
        "workflow",
        export=ExportOptions(
            pdf=PdfOptions(
                fields=("from", "matched_terms", "match_locations"),
                footer_fields=("terms", "filename", "page_number"),
            )
        ),
    )
    updates = []
    dry = execute(config, dry_run=True, on_progress=updates.append)
    assert dry.stats.hits == {"A": 1, "B": 1}
    assert dry.stats.duplicates == 1 and not config.output_dir.exists()
    result = execute(config, on_progress=updates.append)
    assert result.stats.errors == 0 and result.stats.exported == 2
    assert updates[-1].analyzed == 2 and updates[-1].matched == 1 and updates[-1].exported == 2
    assert any(u.total is None and "takeout.zip" in u.mailbox for u in updates)
    assert any(u.total == 2 and u.exported == 1 for u in updates)
    with (result.output / "_manifest.csv").open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row, term in zip(rows, ("Alpha", "Beta")):
        path = result.output / row["pdf_file"]
        pages = PdfReader(path).pages
        text = "\n".join(p.extract_text() for p in pages)
        assert f"Suchbegriff: {term}" in text and path.name in text
        assert json.loads(row["matched_terms"]) == [term]
        assert json.loads(row["match_locations"])[term] == ["subject", "body"]
        assert file_sha256(path) == row["pdf_sha256"]
        assert "AttachmentOnly" in text
        attachments = json.loads(row["attachments"])
        assert (result.output / attachments[0]["saved_file"]).read_bytes() == original
    assert rows[0]["pdf_sha256"] != rows[1]["pdf_sha256"]


def test_sanitized_bucket_keeps_original_search_term(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    term = "Projekt: A/B"
    source.write_bytes(make_mail(subject=term).as_bytes())
    config = RunConfig(
        [source],
        parse_terms(term),
        tmp_path / "out",
        "run",
        export=ExportOptions(pdf=PdfOptions(fields=("matched_terms",))),
    )
    result = execute(config)
    metadata = json.loads((result.output / "_run.json").read_text())
    name = metadata["bucket_directories"][term]
    assert name == "Projekt_ A_B"
    path = next((result.output / name).glob("*.pdf"))
    assert term in "\n".join(p.extract_text() for p in PdfReader(path).pages)
    assert config.terms[0].term == term


def test_footer_only_variants_reuse_memo(tmp_path, make_mail, monkeypatch):
    from mailbucket import pipeline

    source = tmp_path / "source.eml"
    source.write_bytes(make_mail().as_bytes())
    original = pipeline.render_email
    calls = []

    def render(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "render_email", render)
    config = RunConfig(
        [source],
        parse_terms("345678\nMustermann"),
        tmp_path / "out",
        "run",
        export=ExportOptions(pdf=PdfOptions(footer_fields=("filename",))),
        export_workers=1,
    )
    result = execute(config)
    assert result.stats.exported == 2 and len(calls) == 1
