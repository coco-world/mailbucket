from datetime import datetime, timezone
from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from mailbucket.config import (
    DEFAULT_PDF_FIELDS,
    FOOTER_LABELS,
    PDF_LABELS,
    ExportOptions,
    PdfOptions,
)
from mailbucket.export.attachments import merge_attachments
from mailbucket.export.footer import apply_footer
from mailbucket.export.pdf_renderer import PdfContext, document, render_email
from mailbucket.importers.normalize import normalize


def extract(data):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


def test_default_memo_and_opt_in_metadata(make_mail):
    mail = normalize(make_mail(body="Body-marker").as_bytes(), source_file="archive.mbox")
    text = extract(render_email(mail, ["query-marker"]))
    assert all(label in text for label in ["Von:", "Gesendet:", "An:", "Cc:", "Betreff:"])
    assert "Body-marker" in text
    assert "MailBucket-Metadaten" not in text and "archive.mbox" not in text
    assert "one@example.com" not in text and "query-marker" not in text
    options = PdfOptions(
        fields=(
            *DEFAULT_PDF_FIELDS,
            "message_id",
            "matched_terms",
            "source_file",
            "match_locations",
        )
    )
    text = extract(
        render_email(
            mail, ["query-marker"], options, PdfContext(locations={"query-marker": ["body"]})
        )
    )
    assert text.index("Body-marker") < text.index("MailBucket-Metadaten")
    assert "query-marker" in text and "one@example.com" in text and "Nachrichtentext" in text


def test_all_fields_off_keep_body_only(make_mail):
    mail = normalize(make_mail(subject="PRIVATE-SUBJECT", body="Visible-body").as_bytes())
    text = extract(
        render_email(mail, ["PRIVATE-TERM"], PdfOptions(fields=(), footer_enabled=False))
    )
    assert "Visible-body" in text
    assert not any(
        value in text for value in ["PRIVATE-SUBJECT", "PRIVATE-TERM", "Von:", "MailBucket"]
    )


@pytest.mark.parametrize("field", list(PDF_LABELS))
def test_each_pdf_field_can_be_selected(make_mail, field):
    msg = make_mail()
    msg["Bcc"] = "hidden@example.com"
    msg["Reply-To"] = "reply@example.com"
    msg["In-Reply-To"] = "<parent@example.com>"
    msg["References"] = "<root@example.com>"
    msg.add_attachment(b"bytes", maintype="text", subtype="plain", filename="report.txt")
    mail = normalize(
        msg.as_bytes(),
        source_file="archive.mbox",
        source_folder="folder",
        source_index=4,
        source_type="MBOX",
    )
    data = render_email(
        mail, ["query"], PdfOptions(fields=(field,)), PdfContext(locations={"query": ["subject"]})
    )
    assert data.startswith(b"%PDF") and extract(data)
    if field != "subject":
        assert "Betreff:" not in extract(data)


@pytest.mark.parametrize(
    "field,expected",
    [
        ("application", "MailBucket"),
        ("export_date", "Export: 17.09.2026"),
        ("mail_date", "Mail: 14.09.2026"),
        ("terms", "Suchbegriff: QUERY"),
        ("mailbox", "Mailbox: archive"),
        ("page_number", "Seite 1/1"),
        ("filename", "Datei: test.pdf"),
    ],
)
def test_footer_elements_independently(make_mail, field, expected):
    mail = normalize(make_mail().as_bytes(), source_folder="archive")
    base = render_email(mail, [])
    context = PdfContext(
        export_time=datetime(2026, 9, 17, tzinfo=timezone.utc), export_file="test.pdf"
    )
    output = apply_footer(base, mail, ["QUERY"], PdfOptions(footer_fields=(field,)), context)
    assert expected in extract(output)
    if field != "application":
        assert "MailBucket" not in extract(output)
    assert apply_footer(base, mail, [], PdfOptions(footer_enabled=False), context) == base
    assert apply_footer(base, mail, [], PdfOptions(footer_fields=()), context) == base


def test_footer_total_includes_attachment_and_no_overlay(make_mail):
    msg = make_mail()
    original = document("ORIGINAL", [("Text", "Preserve me")])
    msg.add_attachment(original, maintype="application", subtype="pdf", filename="doc.pdf")
    mail = normalize(msg.as_bytes())
    base = render_email(mail, [])
    merged, errors = merge_attachments(base, mail, ExportOptions())
    output = apply_footer(merged, mail, [], PdfOptions(), PdfContext())
    before = PdfReader(BytesIO(merged))
    pages = PdfReader(BytesIO(output)).pages
    assert errors == 0 and len(pages) == len(before.pages)
    for number, page in enumerate(pages, 1):
        assert f"Seite {number}/{len(pages)}" in page.extract_text()
        assert page.mediabox.height > before.pages[number - 1].mediabox.height
    assert "Preserve me" in extract(output)
    assert mail.attachments[0].data == original


def test_long_metadata_footer_and_rotated_crop(make_mail):
    mail = normalize(make_mail(subject="Ü" * 3000).as_bytes(), source_folder="Mailbox" * 300)
    mail.message_id = "<" + "long" * 1500 + "@example.com>"
    base = render_email(mail, ["query"], PdfOptions(fields=("subject", "message_id")))
    writer = PdfWriter(clone_from=BytesIO(base))
    writer.pages[0].rotate(90)
    writer.pages[0].cropbox.lower_left = (20, 20)
    stream = BytesIO()
    writer.write(stream)
    output = apply_footer(
        stream.getvalue(),
        mail,
        ["term" * 1000],
        PdfOptions(footer_fields=tuple(FOOTER_LABELS)),
        PdfContext(export_file="long" * 500),
    )
    assert "Seite 1/" in extract(output)
    assert all(page.mediabox.width > 0 for page in PdfReader(BytesIO(output)).pages)
