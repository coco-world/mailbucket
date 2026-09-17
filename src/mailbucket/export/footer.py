"""Apply a configurable footer after merging, including the final total page count."""

from io import BytesIO
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from mailbucket.config import PdfOptions
from mailbucket.export.pdf_renderer import PdfContext, font_name
from mailbucket.models import NormalizedEmail
from mailbucket.utils.text import clean_text


def apply_footer(
    data: bytes, mail: NormalizedEmail, terms: list[str], options: PdfOptions, context: PdfContext
) -> bytes:
    """Add space below original pages rather than covering attachment contents."""
    if not options.footer_enabled or not options.footer_fields:
        return data
    reader = PdfReader(BytesIO(data))
    source_writer = PdfWriter(clone_from=reader)
    writer = PdfWriter()
    style = ParagraphStyle(
        "footer", fontName=font_name(), fontSize=7, leading=10, splitLongWords=True
    )
    for number, source in enumerate(source_writer.pages, 1):
        values = {
            "application": "MailBucket",
            "export_date": "Export: " + context.export_time.strftime("%d.%m.%Y"),
            "mail_date": "Mail: " + (mail.date.strftime("%d.%m.%Y") if mail.date else "unbekannt"),
            "terms": "Suchbegriff: " + ", ".join(terms),
            "mailbox": "Mailbox: " + (mail.source_folder or "(nicht vorhanden)"),
            "page_number": f"Seite {number}/{len(reader.pages)}",
            "filename": "Datei: " + context.export_file,
        }
        # Full values remain in the manifest; bound footer growth for pathological input.
        parts = [
            values[key] if len(values[key]) <= 240 else values[key][:237] + "..."
            for key in options.footer_fields
        ]
        paragraph = Paragraph(escape(clean_text(" | ".join(parts))), style)
        source.transfer_rotation_to_content()
        box = source.cropbox
        width = max(240, float(box.width))
        _, height = paragraph.wrap(width - 64, 10000)
        band = height + 30
        page = writer.add_blank_page(width=width, height=float(box.height) + band)
        page.merge_transformed_page(
            source,
            Transformation().translate(
                tx=-float(box.left) + (width - float(box.width)) / 2, ty=-float(box.bottom) + band
            ),
        )
        overlay = BytesIO()
        canvas = Canvas(overlay, pagesize=(width, float(box.height) + band))
        canvas.setStrokeColorRGB(0.7, 0.7, 0.7)
        canvas.setLineWidth(0.4)
        canvas.line(32, band - 5, width - 32, band - 5)
        paragraph.drawOn(canvas, 32, 15)
        canvas.save()
        page.merge_page(PdfReader(BytesIO(overlay.getvalue())).pages[0])
    output = BytesIO()
    writer.write(output)
    writer.close()
    source_writer.close()
    return output.getvalue()
