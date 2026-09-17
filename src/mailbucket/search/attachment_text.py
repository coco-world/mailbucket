"""Optional local attachment text extraction; no OCR or external converters."""

import logging
from io import BytesIO

from pypdf import PdfReader

from mailbucket.models import Attachment
from mailbucket.utils.text import clean_text, html_to_text

log = logging.getLogger(__name__)
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_TEXT_CHARS = 2_000_000


def attachment_text(attachment: Attachment) -> str:
    """Return searchable text with explicit warnings for unreadable or limited content."""
    name = attachment.filename.lower()
    pdf = attachment.mime_type == "application/pdf" or name.endswith(".pdf")
    html = attachment.mime_type == "text/html" or name.endswith((".html", ".htm"))
    supported = (
        pdf
        or html
        or attachment.mime_type.startswith("text/")
        or name.endswith((".txt", ".csv", ".tsv", ".log", ".md"))
    )
    if not supported:
        return ""
    if len(attachment.data) > MAX_ATTACHMENT_BYTES:
        log.warning("Anhangsuche übersprungen (>20 MiB): %s", attachment.filename)
        return ""
    try:
        if pdf:
            reader = PdfReader(BytesIO(attachment.data))
            if reader.is_encrypted:
                raise ValueError("PDF ist verschlüsselt")
            if len(reader.pages) > MAX_PDF_PAGES:
                log.warning("Anhangsuche auf 500 PDF-Seiten begrenzt: %s", attachment.filename)
            chunks = []
            length = 0
            for page in reader.pages[:MAX_PDF_PAGES]:
                chunk = page.extract_text() or ""
                chunks.append(chunk)
                length += len(chunk)
                if length > MAX_TEXT_CHARS:
                    break
            text = "\n".join(chunks)
        else:
            data = attachment.data
            encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                text = data.decode("cp1252", errors="replace")
            if html:
                text = html_to_text(text)
        if len(text) > MAX_TEXT_CHARS:
            log.warning("Anhangsuche auf 2 Mio. Zeichen begrenzt: %s", attachment.filename)
        return clean_text(text[:MAX_TEXT_CHARS])
    except Exception:
        log.exception("Anhangtext konnte nicht gelesen werden: %s", attachment.filename)
        return ""
