from mailbucket.importers.eml import EmlImporter
from mailbucket.importers.normalize import normalize
from mailbucket.utils.hashing import sha256


def test_eml_unicode_headers_addresses_attachment(tmp_path, make_mail):
    msg = make_mail()
    msg.add_attachment(
        b"original\x00bytes",
        maintype="application",
        subtype="octet-stream",
        filename="Rechnung_Müller.xlsx",
    )
    path = tmp_path / "mail.eml"
    path.write_bytes(msg.as_bytes())
    mail = next(EmlImporter().iter_emails(path))
    assert mail.subject == "Vorgang 345678 – Grüße Müller"
    assert len(mail.to) == 2 and "carol@example.com" in mail.to[1]
    assert mail.cc == ["dave@example.com"]
    assert mail.labels == ["Inbox", "Important", "Projekt Müller"]
    assert mail.attachments[0].filename == "Rechnung_Müller.xlsx"
    assert mail.attachments[0].sha256 == sha256(b"original\x00bytes")
    assert mail.raw_sha256 == sha256(path.read_bytes())
    assert mail.date.utcoffset().total_seconds() == 7200


def test_html_only_and_no_remote_resources(make_mail):
    msg = make_mail()
    msg.set_content(
        "<html><head><style>secret-style</style></head><body><p>Grüße</p>"
        '<script>secret-script</script><img src="https://invalid.example/track">Müller</body></html>',
        subtype="html",
    )
    mail = normalize(msg.as_bytes())
    assert "Müller" in mail.body_text and "Grüße" in mail.body_text
    assert "secret" not in mail.body_text and "https" not in mail.body_text


def test_plain_preferred(make_mail):
    msg = make_mail(body="Plaintext bevorzugt")
    msg.add_alternative("<p>HTML alternative</p>", subtype="html")
    mail = normalize(msg.as_bytes())
    assert mail.body_text.strip() == "Plaintext bevorzugt"
    assert mail.body_html == "<p>HTML alternative</p>\n"


def test_unknown_charset_and_broken_date():
    raw = b"Subject: =?utf-8?b?R3LDvMOfZQ==?=\nDate: invalid-date\nContent-Type: text/plain; charset=unknown\n\nHi\xff"
    mail = normalize(raw)
    assert mail.subject == "Grüße"
    assert mail.date is None
    assert "Hi" in mail.body_text


def test_attached_message_is_not_body(make_mail):
    msg = make_mail(body="Outer")
    msg.add_attachment(make_mail(body="Hidden inner"), filename="forward.eml")
    parsed = normalize(msg.as_bytes())
    assert "Hidden inner" not in parsed.body_text
    assert b"Hidden inner" in parsed.attachments[0].data
