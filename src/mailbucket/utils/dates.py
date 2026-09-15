from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from mailbucket.models import NormalizedEmail


def parse_date(raw: str | None) -> datetime | None:
    try:
        date = parsedate_to_datetime(raw) if raw else None
        if date is not None and date.tzinfo is None:
            date = date.replace(tzinfo=UTC)
        return date
    except (ValueError, TypeError, OverflowError, IndexError):
        return None


def sort_key(mail: NormalizedEmail) -> tuple:
    date = mail.date
    if date is not None and date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return (
        date is None,
        date.astimezone(UTC) if date else datetime.max.replace(tzinfo=UTC),
        mail.message_id or "",
        mail.source_file,
        mail.source_index if mail.source_index is not None else -1,
        mail.source_folder or "",
    )
