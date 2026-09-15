"""Tolerant MIME parsing, shared by all source adapters."""

import csv
import logging
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses

from mailbucket.models import Attachment, NormalizedEmail
from mailbucket.utils.dates import parse_date
from mailbucket.utils.hashing import sha256
from mailbucket.utils.text import clean_text, html_to_text

log = logging.getLogger(__name__)


def decoded_payload(part: Message) -> str:
    data = part.get_payload(decode=True) or b""
    try:
        return clean_text(data.decode(part.get_content_charset() or "utf-8", errors="replace"))
    except LookupError:
        return clean_text(data.decode("utf-8", errors="replace"))


def normalize(raw: bytes, **source) -> NormalizedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    def header(name: str) -> str:
        try:
            return clean_text(str(msg.get(name, "")))
        except (ValueError, LookupError, IndexError):
            log.warning("Defekter Header %s in %s", name, source)
            return ""

    def addresses(name: str) -> list[str]:
        values = [clean_text(str(v)) for v in msg.get_all(name, [])]
        try:
            return [f"{n} <{a}>" if n else a for n, a in getaddresses(values) if n or a]
        except (ValueError, IndexError):
            return values

    plain: list[str] = []
    html: list[str] = []
    attachments: list[Attachment] = []

    def visit(part: Message) -> None:
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if (
            filename
            or disposition == "attachment"
            or (
                not part.is_multipart() and part.get_content_maintype() not in {"text", "multipart"}
            )
        ):
            payload = part.get_payload(decode=True)
            if payload is None:
                nested = part.get_payload()
                payload = (
                    b"\n".join(p.as_bytes() for p in nested) if isinstance(nested, list) else b""
                )
            attachments.append(
                Attachment(
                    clean_text(filename or f"attachment-{len(attachments) + 1}"),
                    part.get_content_type(),
                    payload,
                    sha256(payload),
                )
            )
        elif part.is_multipart():
            for child in part.get_payload():
                visit(child)
        elif part.get_content_type() == "text/plain":
            plain.append(decoded_payload(part))
        elif part.get_content_type() == "text/html":
            html.append(decoded_payload(part))

    visit(msg)
    date_raw = header("Date") or None
    date = parse_date(date_raw)
    if date_raw and date is None:
        log.warning("Ungültiges Datum in %s: %r", source, date_raw)
    body_html = "\n".join(html) or None
    labels = next(csv.reader([header("X-Gmail-Labels")], skipinitialspace=True), [])
    return NormalizedEmail(
        **source,
        message_id=header("Message-ID").strip() or None,
        date=date,
        date_raw=date_raw,
        sender=header("From"),
        to=addresses("To"),
        cc=addresses("Cc"),
        bcc=addresses("Bcc"),
        subject=header("Subject"),
        body_text="\n".join(plain) if plain else html_to_text(body_html or ""),
        body_html=body_html,
        attachments=attachments,
        labels=[s.strip() for s in labels if s.strip()],
        raw_sha256=sha256(raw),
    )
