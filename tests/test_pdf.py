from io import BytesIO

from PIL import Image
from pypdf import PdfReader

from mailbucket.config import ExportOptions
from mailbucket.export.attachments import merge_attachments, save_originals
from mailbucket.export.pdf_renderer import document, render_email
from mailbucket.importers.normalize import normalize
from mailbucket.models import Attachment
from mailbucket.utils.hashing import sha256


def text(data):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(data)).pages)


def test_pdf_metadata_unicode_long_body(make_mail):
    mail = normalize(make_mail(body=("Langer Text mit Umlauten äöüß. " * 300)).as_bytes())
    data = render_email(mail, ["345678"])
    assert data.startswith(b"%PDF")
    assert "Grüße Müller" in text(data) and "alice@example.com" in text(data)
    assert "345678" in text(data) and len(PdfReader(BytesIO(data)).pages) > 1


def test_pdf_attachment_and_bad_pdf(make_mail):
    msg = make_mail()
    msg.add_attachment(
        document("RECHNUNG", [("Betrag", "100 EUR")]),
        maintype="application",
        subtype="pdf",
        filename="Rechnung.pdf",
    )
    msg.add_attachment(b"broken", maintype="application", subtype="pdf", filename="kaputt.pdf")
    mail = normalize(msg.as_bytes())
    output, failures = merge_attachments(render_email(mail, ["345678"]), mail, ExportOptions())
    assert failures == 1
    assert "RECHNUNG" in text(output) and "ANHANG 1 VON 2" in text(output)
    assert "nicht in die PDF integriert" in text(output)
    assert len(PdfReader(BytesIO(output)).pages) >= 4


def test_image_and_original_collision(tmp_path, make_mail):
    image = BytesIO()
    Image.new("RGB", (800, 200), "teal").save(image, format="PNG")
    data = image.getvalue()
    mail = normalize(make_mail().as_bytes())
    mail.attachments = [
        Attachment("../../a.png", "image/png", data, sha256(data)),
        Attachment("../../a.png", "image/png", b"different", sha256(b"different")),
    ]
    output, failures = merge_attachments(render_email(mail, []), mail, ExportOptions())
    assert failures == 1
    assert len(PdfReader(BytesIO(output)).pages) >= 4
    records = save_originals(mail, tmp_path / "attachments", ExportOptions())
    assert records[0]["saved_file"] != records[1]["saved_file"]
    assert (tmp_path / "attachments" / records[0]["saved_file"]).read_bytes() == data


def test_modes_and_truthful_placeholder(tmp_path, make_mail):
    mail = normalize(make_mail().as_bytes())
    pdf = document("ORIGINAL", [])
    mail.attachments = [
        Attachment("a.pdf", "application/pdf", pdf, sha256(pdf)),
        Attachment("a.exe", "application/octet-stream", b"x", sha256(b"x")),
    ]
    options = ExportOptions(pdf_mode="separate", save_originals=False)
    output, errors = merge_attachments(render_email(mail, []), mail, options)
    assert errors == 0 and "nicht gespeichert" in text(output)
    assert "ORIGINAL" not in text(output)
    records = save_originals(mail, tmp_path, options)
    assert records[0]["saved_file"] == "a.pdf" and records[1]["saved_file"] is None
    options.include_attachments = False
    assert save_originals(mail, tmp_path / "none", options)[0]["saved_file"] is None
    assert not (tmp_path / "none").exists()


def test_long_unbroken_header_and_body(make_mail):
    mail = normalize(make_mail(subject="Müller" * 500, body="abcdef" * 2000).as_bytes())
    output = render_email(mail, [])
    assert len(PdfReader(BytesIO(output)).pages) > 1


def test_both_mode_and_cover_disabled(tmp_path, make_mail):
    mail = normalize(make_mail().as_bytes())
    pdf = document("INVOICE", [])
    mail.attachments = [Attachment("invoice.pdf", "application/pdf", pdf, sha256(pdf))]
    options = ExportOptions(pdf_mode="both", cover_pages=False, save_originals=False)
    base = render_email(mail, [])
    output, errors = merge_attachments(base, mail, options)
    assert errors == 0
    assert len(PdfReader(BytesIO(output)).pages) == len(PdfReader(BytesIO(base)).pages) + 1
    assert save_originals(mail, tmp_path, options)[0]["saved_file"] == "invoice.pdf"
    assert (tmp_path / "invoice.pdf").read_bytes() == pdf
