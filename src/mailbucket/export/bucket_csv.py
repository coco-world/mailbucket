"""Small, Excel-friendly mail list stored beside every bucket's PDFs."""

import csv
from pathlib import Path

from mailbucket.models import NormalizedEmail
from mailbucket.utils.text import clean_text

COLUMNS = ["Datum", "Uhrzeit", "von", "an", "Text"]


def _single_line(value: str) -> str:
    """Keep one mail on one physical CSV line, regardless of Excel import settings."""
    return " ".join(clean_text(value).split())


def open_bucket_csv(path: Path):
    """Open a German Excel-friendly CSV and return its stream and writer."""
    stream = path.open("w", encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=COLUMNS,
        delimiter=";",
        lineterminator="\r\n",
    )
    writer.writeheader()
    return stream, writer


def bucket_row(mail: NormalizedEmail) -> dict[str, str]:
    date = mail.date.strftime("%d.%m.%Y") if mail.date else (mail.date_raw or "")
    time = mail.date.strftime("%H:%M:%S") if mail.date else ""
    body = _single_line(mail.body_text or "(Kein lesbarer Nachrichtentext)")
    return {
        "Datum": _single_line(date),
        "Uhrzeit": time,
        "von": _single_line(mail.sender),
        "an": _single_line("; ".join(mail.to)),
        "Text": body,
    }
