from io import BytesIO

import pytest
from pypdf import PdfReader

from mailbucket.config import DEFAULT_SEARCH_FIELDS
from mailbucket.export.pdf_renderer import document
from mailbucket.importers.normalize import normalize
from mailbucket.models import Attachment
from mailbucket.search.attachment_text import attachment_text
from mailbucket.search.matcher import ContainsMatcher, parse_terms
from mailbucket.utils.hashing import sha256


@pytest.mark.parametrize(
    "field,term",
    [
        ("sender_name", "müller"),
        ("sender_email", "alice@example.com"),
        ("bcc", "hidden@example.com"),
        ("message_id", "one@example.com"),
        ("source_folder", "Ordner/Projekt"),
        ("reply_to", "reply@example.com"),
        ("in_reply_to", "parent@example.com"),
        ("references", "root@example.com"),
    ],
)
def test_new_fields_and_locations(make_mail, field, term):
    msg = make_mail()
    msg["Bcc"] = "hidden@example.com"
    msg["Reply-To"] = "reply@example.com"
    msg["In-Reply-To"] = "<parent@example.com>"
    msg["References"] = "<root@example.com> <parent@example.com>"
    mail = normalize(msg.as_bytes(), source_folder="Ordner/Projekt")
    details = ContainsMatcher(parse_terms(term), (field,)).match_details(mail)
    assert details.buckets == {term: [term]}
    assert details.locations == {term: [field]}


def test_sender_name_and_address_are_distinct(make_mail):
    mail = normalize(make_mail().as_bytes())
    assert not ContainsMatcher(parse_terms("example.com"), ("sender_name",)).match(mail)
    assert not ContainsMatcher(parse_terms("Müller"), ("sender_email",)).match(mail)
    assert set(DEFAULT_SEARCH_FIELDS) == {"subject", "body", "sender_name", "sender_email", "to"}


def test_attachment_text_is_opt_in_and_preserves_bytes(make_mail, monkeypatch):
    msg = make_mail()
    data = document("INVOICE", [("Test", "NurImAnhang")])
    msg.add_attachment(data, maintype="application", subtype="pdf", filename="invoice.pdf")
    msg.add_attachment(b"broken", maintype="application", subtype="pdf", filename="bad.pdf")
    mail = normalize(msg.as_bytes())
    assert not ContainsMatcher(parse_terms("NurImAnhang")).match(mail)
    result = ContainsMatcher(parse_terms("nurimanhang"), ("attachment_content",)).match_details(
        mail
    )
    assert result.locations == {"nurimanhang": ["attachment_content:invoice.pdf"]}
    assert mail.attachments[0].data == data and mail.attachments[0].sha256 == sha256(data)
    assert len(PdfReader(BytesIO(data)).pages) == 1


@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("text.txt", "text/plain", "Grüße Müller".encode()),
        ("text.txt", "application/octet-stream", "Grüße Müller".encode("utf-16")),
        ("text.txt", "text/plain", "Grüße Müller".encode("cp1252")),
        ("web.html", "text/html", b"<style>secret</style><p>Hello</p><script>secret</script>"),
    ],
)
def test_text_attachment_formats(name, mime, data):
    text = attachment_text(Attachment(name, mime, data, sha256(data)))
    assert "Müller" in text or "Hello" in text
    assert "secret" not in text


def test_content_limits_and_unsupported_attachment(caplog, monkeypatch):
    import mailbucket.search.attachment_text as module

    monkeypatch.setattr(module, "MAX_ATTACHMENT_BYTES", 4)
    assert attachment_text(Attachment("large.txt", "text/plain", b"12345", "")) == ""
    assert "übersprungen" in caplog.text
    assert attachment_text(Attachment("test.exe", "application/octet-stream", b"text", "")) == ""
