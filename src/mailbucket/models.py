"""Format-independent data exchanged between import, search and export."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Attachment:
    filename: str
    mime_type: str
    data: bytes
    sha256: str


@dataclass
class NormalizedEmail:
    source_type: str = ""
    source_file: str = ""
    source_folder: str | None = None
    source_index: int | None = None
    message_id: str | None = None
    date: datetime | None = None
    date_raw: str | None = None
    sender: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    body_text: str = ""
    body_html: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    raw_sha256: str = ""
    source_bytes: int = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchTerm:
    term: str
    bucket: str
