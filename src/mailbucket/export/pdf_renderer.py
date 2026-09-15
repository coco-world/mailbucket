"""Documentary, offline PDF rendering with an embedded Unicode TrueType font."""

import threading
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from mailbucket.models import NormalizedEmail
from mailbucket.utils.text import clean_text

_FONT_LOCK = threading.Lock()


def font_name() -> str:
    # ReportLab ships Vera with a redistribution license on all supported platforms.
    with _FONT_LOCK:
        if "MailBucketVera" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont(
                    "MailBucketVera", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")
                )
            )
    return "MailBucketVera"


def document(title: str, sections: list[tuple[str, str]]) -> bytes:
    target = BytesIO()
    style = ParagraphStyle(
        "body", fontName=font_name(), fontSize=9, leading=14, spaceAfter=7, splitLongWords=True
    )
    heading = ParagraphStyle(
        "heading",
        parent=style,
        fontSize=17,
        leading=22,
        textColor=colors.HexColor("#134e4a"),
        spaceAfter=20,
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
        story.append(Spacer(1, 5))

    def footer(canvas, doc):
        canvas.setFont(font_name(), 8)
        canvas.setFillColor(colors.HexColor("#52616b"))
        canvas.drawString(42, 25, "MailBucket | Lokaler E-Mail-Export")
        canvas.drawRightString(A4[0] - 42, 25, str(doc.page))

    SimpleDocTemplate(
        target,
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=45,
        title=title,
        author="MailBucket",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return target.getvalue()


def render_email(mail: NormalizedEmail, matched_terms: list[str]) -> bytes:
    sections = [
        (
            "Datum",
            mail.date.isoformat(sep=" ")
            if mail.date
            else f"Unbekannt / ungültig: {mail.date_raw or '(kein Date-Header)'}",
        ),
        ("Von", mail.sender),
        ("An", "; ".join(mail.to)),
        ("CC", "; ".join(mail.cc)),
        ("BCC", "; ".join(mail.bcc)),
        ("Betreff", mail.subject),
        ("Message-ID", mail.message_id or "(fehlt)"),
        ("Quelle", mail.source_type),
        ("Archiv / Quelldatei", mail.source_file),
        ("Mailbox", mail.source_folder or ""),
        ("Position (nullbasiert)", str(mail.source_index)),
        ("Gmail Labels", ", ".join(mail.labels)),
        ("Treffer (alle Buckets)", ", ".join(matched_terms)),
        ("NACHRICHT", mail.body_text or "(Kein lesbarer Nachrichtentext)"),
    ]
    for index, attachment in enumerate(mail.attachments, 1):
        sections.append(
            (
                f"ANHANG {index}: {attachment.filename}",
                f"MIME: {attachment.mime_type}\nGröße: {len(attachment.data)} Bytes\n"
                f"SHA-256: {attachment.sha256}",
            )
        )
    return document("E-MAIL", sections)
