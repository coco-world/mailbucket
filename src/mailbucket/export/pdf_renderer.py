"""Documentary, offline PDF rendering with an embedded Unicode TrueType font."""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from mailbucket import __version__
from mailbucket.config import PDF_LABELS, SEARCH_LABELS, PdfOptions
from mailbucket.models import NormalizedEmail
from mailbucket.utils.text import clean_text

_FONT_LOCK = threading.Lock()


def font_name(bold: bool = False) -> str:
    # ReportLab ships Vera with a redistribution license on all supported platforms.
    with _FONT_LOCK:
        if "MailBucketVera" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont(
                    "MailBucketVera", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")
                )
            )
            pdfmetrics.registerFont(
                TTFont(
                    "MailBucketVeraBold",
                    str(Path(reportlab.__file__).parent / "fonts" / "VeraBd.ttf"),
                )
            )
    return "MailBucketVeraBold" if bold else "MailBucketVera"


@dataclass
class PdfContext:
    locations: dict[str, list[str]] = field(default_factory=dict)
    export_time: datetime = field(default_factory=lambda: datetime.now().astimezone())
    export_file: str = ""


def formatted_date(mail: NormalizedEmail) -> str:
    return (
        mail.date.strftime("%d.%m.%Y %H:%M:%S %z")
        if mail.date
        else (f"Unbekannt / ungültig: {mail.date_raw or 'kein Date-Header'}")
    )


def location_label(value: str) -> str:
    if value.startswith("attachment_content:"):
        return "Anhanginhalt: " + value.partition(":")[2]
    return SEARCH_LABELS.get(value, value)


def build_document(story: list, title: str = "E-Mail") -> bytes:
    target = BytesIO()
    SimpleDocTemplate(
        target,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=38,
        bottomMargin=36,
        title=title,
        author="MailBucket",
    ).build(story)
    return target.getvalue()


def document(title: str, sections: list[tuple[str, str]]) -> bytes:
    style = ParagraphStyle(
        "body", fontName=font_name(), fontSize=9, leading=11, spaceAfter=3, splitLongWords=True
    )
    heading = ParagraphStyle(
        "heading",
        parent=style,
        fontSize=17,
        leading=19,
        textColor=colors.HexColor("#134e4a"),
        spaceAfter=12,
    )
    label = ParagraphStyle(
        "label",
        parent=style,
        fontSize=8,
        textColor=colors.HexColor("#52616b"),
        spaceAfter=2,
        keepWithNext=True,
    )
    story = [Paragraph(escape(title), heading)]
    for name, value in sections:
        if name:
            story.append(Paragraph(escape(name), label))
        # Break into paragraphs so arbitrarily long bodies can split across pages.
        for line in clean_text(value).splitlines() or [""]:
            story.append(Paragraph(escape(line).replace("\t", "    ") or "&#160;", style))
        story.append(Spacer(1, 3))

    return build_document(story, title)


def render_email(
    mail: NormalizedEmail,
    matched_terms: list[str],
    options: PdfOptions | None = None,
    context: PdfContext | None = None,
) -> bytes:
    """Outlook-like memo; optional technical metadata follows the readable message."""
    options = options or PdfOptions()
    context = context or PdfContext()
    options.validate()
    body = ParagraphStyle(
        "memo-body",
        fontName=font_name(),
        fontSize=9.5,
        leading=11.5,
        spaceAfter=1,
        splitLongWords=True,
    )
    custom_header = ParagraphStyle(
        "custom-header",
        parent=body,
        fontName=font_name(True),
        fontSize=10.5,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#134e4a"),
        spaceAfter=2,
    )
    header = ParagraphStyle(
        "memo-header",
        parent=body,
        leftIndent=78,
        bulletIndent=0,
        bulletFontName=font_name(True),
        bulletFontSize=9.5,
        spaceAfter=3,
    )
    label = ParagraphStyle(
        "metadata-label",
        parent=body,
        fontName=font_name(True),
        fontSize=8,
        leading=10,
        keepWithNext=True,
        spaceBefore=5,
    )
    metadata = ParagraphStyle("metadata-value", parent=body, fontSize=8, leading=10)
    story = []
    header_text = clean_text(options.custom_header)
    if header_text.strip():
        for line in header_text.splitlines() or [""]:
            story.append(Paragraph(escape(line) or "&#160;", custom_header))
        story.append(Spacer(1, 5))
    headers = [
        ("from", "Von:", mail.sender),
        ("date", "Gesendet:", formatted_date(mail)),
        ("to", "An:", "; ".join(mail.to)),
        ("cc", "Cc:", "; ".join(mail.cc)),
        ("bcc", "Bcc:", "; ".join(mail.bcc)),
        ("subject", "Betreff:", mail.subject),
    ]
    for key, title, value in headers:
        if key in options.fields:
            story.append(Paragraph(escape(clean_text(value)) or "&#160;", header, bulletText=title))
    if "attachments" in options.fields and mail.attachments:
        # Separate paragraphs keep very large attachment inventories splittable.
        for index, attachment in enumerate(mail.attachments):
            story.append(
                Paragraph(
                    escape(clean_text(attachment.filename)) + f" ({len(attachment.data):,} Bytes)",
                    header,
                    bulletText="Anlagen:" if index == 0 else None,
                )
            )
    if story:
        story.extend(
            [
                Spacer(1, 6),
                HRFlowable(width="100%", thickness=0.6, color=colors.black),
                Spacer(1, 9),
            ]
        )
    for line in clean_text(mail.body_text or "(Kein lesbarer Nachrichtentext)").splitlines():
        story.append(Paragraph(escape(line).replace("\t", "    ") or "&#160;", body))
    values = {
        "message_id": mail.message_id or "(fehlt)",
        "source_type": mail.source_type,
        "source_file": mail.source_file,
        "source_filename": Path(mail.source_file).name,
        "source_folder": mail.source_folder or "",
        "source_index": str(mail.source_index) if mail.source_index is not None else "",
        "labels": ", ".join(mail.labels),
        "matched_terms": ", ".join(matched_terms),
        "match_locations": "\n".join(
            f"{term}: {', '.join(location_label(f) for f in fields)}"
            for term, fields in context.locations.items()
            if term in matched_terms
        ),
        "export_time": context.export_time.strftime("%d.%m.%Y %H:%M:%S %z"),
        "version": __version__,
        "reply_to": mail.headers.get("Reply-To", ""),
        "in_reply_to": mail.headers.get("In-Reply-To", ""),
        "references": mail.headers.get("References", ""),
    }
    selected = [key for key in PDF_LABELS if key in options.fields and key in values]
    if selected:
        story.extend(
            [
                Spacer(1, 12),
                HRFlowable(width="100%", thickness=0.4, color=colors.grey),
                Paragraph("MailBucket-Metadaten", label),
            ]
        )
        for key in selected:
            story.append(Paragraph(escape(PDF_LABELS[key]), label))
            for line in clean_text(values[key]).splitlines() or [""]:
                story.append(Paragraph(escape(line) or "(nicht vorhanden)", metadata))
    return build_document(story)
