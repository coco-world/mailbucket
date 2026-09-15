import csv
from pathlib import Path

COLUMNS = [
    "bucket",
    "index",
    "date",
    "from",
    "to",
    "cc",
    "subject",
    "message_id",
    "source_type",
    "source_file",
    "source_folder",
    "source_index",
    "gmail_labels",
    "matched_terms",
    "pdf_file",
    "pdf_sha256",
    "attachment_count",
    "dedup_key",
    "date_status",
    "raw_sha256",
    "attachments",
]


def open_manifest(path: Path):
    stream = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    return stream, writer
