"""Integrate original PDF pages or proportional image pages; never execute attachments."""

import logging
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from mailbucket.config import ExportOptions
from mailbucket.export.pdf_renderer import document
from mailbucket.models import Attachment, NormalizedEmail
from mailbucket.utils.filenames import safe_name

log = logging.getLogger(__name__)


def is_pdf(attachment: Attachment) -> bool:
    return attachment.mime_type == "application/pdf" or attachment.filename.lower().endswith(".pdf")


def should_save(attachment: Attachment, options: ExportOptions) -> bool:
    return options.include_attachments and (
        options.save_originals or (is_pdf(attachment) and options.pdf_mode in {"separate", "both"})
    )


def image_pdf(data: bytes) -> bytes:
    output = BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            width, height = image.size
            scale = min((A4[0] - 84) / width, (A4[1] - 84) / height)
            canvas = Canvas(output, pagesize=A4)
            canvas.drawImage(
                ImageReader(image),
                (A4[0] - width * scale) / 2,
                (A4[1] - height * scale) / 2,
                width * scale,
                height * scale,
            )
            canvas.showPage()
            canvas.save()
    return output.getvalue()


def merge_attachments(
    email_pdf: bytes, mail: NormalizedEmail, options: ExportOptions
) -> tuple[bytes, int]:
    if not options.include_attachments or not mail.attachments:
        return email_pdf, 0
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(email_pdf)), import_outline=False)
    failures = 0
    for index, attachment in enumerate(mail.attachments, 1):
        convertible = is_pdf(attachment) and options.pdf_mode in {"merge", "both"}
        image = attachment.mime_type in {
            "image/jpeg",
            "image/png",
        } or attachment.filename.lower().endswith((".jpg", ".jpeg", ".png"))
        data = None
        reason = "Dieser Anhang konnte nicht in die PDF integriert werden."
        try:
            if convertible:
                data = attachment.data
            elif image and options.images_as_pages:
                data = image_pdf(attachment.data)
            if data is not None:
                reader = PdfReader(BytesIO(data), strict=False)
                if reader.is_encrypted:
                    raise ValueError("Verschlüsselter PDF-Anhang")
                if not reader.pages:
                    raise ValueError("PDF-Anhang enthält keine Seiten")
                # Build in isolation: corrupt input must not partially alter the final document.
                part = PdfWriter()
                if options.cover_pages:
                    details = [("Original-Dateiname", attachment.filename)]
                    if "subject" in options.pdf.fields:
                        details.append(("E-Mail", mail.subject))
                    if "message_id" in options.pdf.fields:
                        details.append(("Message-ID", mail.message_id or "(fehlt)"))
                    details.extend(
                        [("MIME-Type", attachment.mime_type), ("SHA-256", attachment.sha256)]
                    )
                    cover = document(
                        f"ANHANG {index} VON {len(mail.attachments)}",
                        details,
                    )
                    part.append(PdfReader(BytesIO(cover)), import_outline=False)
                for page in reader.pages:
                    # Retain page contents; strip interactive annotations/actions from the export.
                    part.add_page(page, excluded_keys=["/Annots", "/AA"])
                buffer = BytesIO()
                part.write(buffer)
                writer.append(PdfReader(BytesIO(buffer.getvalue())), import_outline=False)
                continue
        except Exception:
            failures += 1
            log.exception("Anhang konnte nicht integriert werden: %s", attachment.filename)
            reason += " Die Datei ist beschädigt, verschlüsselt oder nicht lesbar."
        if is_pdf(attachment) and options.pdf_mode == "separate":
            reason = "Dieser PDF-Anhang wird separat gespeichert."
        location = (
            "Die Originaldatei befindet sich im attachments-Verzeichnis dieser E-Mail."
            if should_save(attachment, options)
            else "Die Originaldatei wurde entsprechend der Export-Einstellung nicht gespeichert."
        )
        note = document(
            "ANHANG",
            [
                ("Dateiname", attachment.filename),
                ("Status", reason + "\n" + location),
                ("SHA-256", attachment.sha256),
            ],
        )
        writer.append(PdfReader(BytesIO(note)), import_outline=False)
    output = BytesIO()
    writer.write(output)
    writer.close()
    return output.getvalue(), failures


def save_originals(mail: NormalizedEmail, directory: Path, options: ExportOptions) -> list[dict]:
    records = []
    used: set[str] = set()
    for attachment in mail.attachments:
        record = {
            "filename": attachment.filename,
            "sha256": attachment.sha256,
            "size": len(attachment.data),
            "saved_file": None,
        }
        if should_save(attachment, options):
            directory.mkdir(parents=True, exist_ok=True)
            name = safe_name(attachment.filename)
            candidate = name
            index = 2
            while candidate.casefold() in used or (directory / candidate).exists():
                path = Path(name)
                candidate = f"{path.stem}_{index}{path.suffix}"
                index += 1
            used.add(candidate.casefold())
            with (directory / candidate).open("xb") as stream:
                stream.write(attachment.data)
            record["saved_file"] = candidate
        records.append(record)
    return records
