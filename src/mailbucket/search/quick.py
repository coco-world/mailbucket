"""Small, sortable search results for the interactive index browser."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from mailbucket.config import SEARCH_FIELDS
from mailbucket.index import IndexManager, IndexState
from mailbucket.models import SearchTerm

PAGE_SIZE = 20
FIELD_WEIGHTS = {
    "subject": 12,
    "sender_name": 9,
    "sender_email": 9,
    "from": 9,
    "to": 6,
    "cc": 6,
    "bcc": 6,
    "attachment_names": 5,
    "message_id": 4,
    "labels": 4,
    "body": 3,
    "attachment_content": 2,
}


@dataclass(frozen=True)
class QuickHit:
    source: Path
    source_id: str
    record_id: int
    raw_sha256: str
    date: datetime | None
    sender: str
    subject: str
    folder: str
    locations: tuple[str, ...]
    snippet: str
    relevance: int

    @property
    def key(self) -> tuple[str, int, str]:
        return self.source_id, self.record_id, self.raw_sha256


def _snippet(body: str, term: str, limit: int = 180) -> str:
    clean = " ".join(body.split())
    position = clean.casefold().find(term.casefold())
    start = max(0, position - 55) if position >= 0 else 0
    excerpt = clean[start : start + limit]
    return ("…" if start else "") + excerpt + ("…" if start + limit < len(clean) else "")


def search_sources(
    manager: IndexManager,
    sources: list[Path],
    term: str,
    fields: tuple[str, ...] = SEARCH_FIELDS,
) -> list[QuickHit]:
    """Search current indexes and retain only compact metadata for the result list."""
    needle = term.strip()
    if not needle:
        raise ValueError("Bitte einen Suchbegriff eingeben.")
    if not fields or set(fields) - set(SEARCH_FIELDS):
        raise ValueError("Bitte ein gültiges Suchfeld auswählen.")
    result = []
    for source in sources:
        info = manager.status(source)
        if info.state != IndexState.CURRENT:
            raise RuntimeError(f"Index für {source.name} ist nicht aktuell: {info.state.value}")
        for match in manager.iter_search(source, [SearchTerm(needle, needle)], fields):
            mail = match.mail
            locations = tuple(match.locations[needle])
            score = max(
                (FIELD_WEIGHTS.get(location.split(":", 1)[0], 3) for location in locations),
                default=0,
            ) + len(locations)
            result.append(
                QuickHit(
                    source=source,
                    source_id=info.source_id,
                    record_id=match.record_id,
                    raw_sha256=mail.raw_sha256,
                    date=mail.date,
                    sender=mail.sender,
                    subject=mail.subject,
                    folder=mail.source_folder or mail.source_file,
                    locations=locations,
                    snippet=_snippet(mail.body_text, needle),
                    relevance=score,
                )
            )
    return result


def sort_hits(hits: list[QuickHit], order: str) -> list[QuickHit]:
    def date_value(hit: QuickHit) -> datetime:
        date = hit.date
        if date is None:
            return datetime.min.replace(tzinfo=UTC)
        return (date if date.tzinfo else date.replace(tzinfo=UTC)).astimezone(UTC)

    if order == "relevance":
        return sorted(
            hits,
            key=lambda hit: (hit.relevance, date_value(hit), hit.source_id, hit.record_id),
            reverse=True,
        )
    if order == "newest":
        return sorted(
            hits,
            key=lambda hit: (date_value(hit), hit.source_id, hit.record_id),
            reverse=True,
        )
    if order == "oldest":
        return sorted(
            hits,
            key=lambda hit: (hit.date is None, date_value(hit), hit.source_id, hit.record_id),
        )
    raise ValueError("Unbekannte Sortierung.")
