"""Contains matching and validated user input, independent of source formats."""

import csv
import io
import re
from dataclasses import dataclass
from email.utils import getaddresses

from mailbucket.config import DEFAULT_SEARCH_FIELDS, SEARCH_FIELDS
from mailbucket.models import NormalizedEmail, SearchTerm
from mailbucket.search.attachment_text import attachment_text
from mailbucket.utils.text import html_to_text


def parse_terms(text: str) -> list[SearchTerm]:
    return list(
        dict.fromkeys(
            SearchTerm(line.strip(), line.strip()) for line in text.splitlines() if line.strip()
        )
    )


def parse_csv(text: str) -> list[SearchTerm]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    if reader.fieldnames != ["term", "bucket"]:
        raise ValueError("CSV-Kopf muss exakt term,bucket lauten (UTF-8, Komma als Trennzeichen).")
    result = []
    try:
        for row in reader:
            if None in row or any(not (row.get(k) or "").strip() for k in ("term", "bucket")):
                raise ValueError(
                    f"CSV-Zeile {reader.line_num}: Suchbegriff oder Bucket fehlt / zu viele Spalten."
                )
            result.append(SearchTerm(row["term"].strip(), row["bucket"].strip()))
    except csv.Error as error:
        raise ValueError(f"CSV-Zeile {reader.line_num}: {error}") from error
    if not result:
        raise ValueError("CSV enthält keine Suchbegriffe.")
    return list(dict.fromkeys(result))


@dataclass
class MatchResult:
    buckets: dict[str, list[str]]
    locations: dict[str, list[str]]


def searchable_values(
    mail: NormalizedEmail,
    attachment_texts: list[tuple[str, str]] | None = None,
    *,
    extract_attachment_text: bool = True,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Build the canonical searchable representation used by scans and indexes."""
    senders = getaddresses([mail.sender])
    values = {
        "subject": mail.subject,
        "from": mail.sender,
        "sender_name": "\n".join(name for name, _ in senders),
        "sender_email": "\n".join(address for _, address in senders),
        "to": "\n".join(mail.to),
        "cc": "\n".join(mail.cc),
        "bcc": "\n".join(mail.bcc),
        "body": mail.body_text,
        "attachment_names": "\n".join(a.filename for a in mail.attachments),
        "labels": "\n".join(mail.labels),
        "message_id": mail.message_id or "",
        "source_folder": mail.source_folder or "",
        "reply_to": mail.headers.get("Reply-To", ""),
        "in_reply_to": mail.headers.get("In-Reply-To", ""),
        "references": mail.headers.get("References", ""),
    }
    if mail.body_html:
        values["body"] += "\n" + html_to_text(mail.body_html)
    if attachment_texts is None:
        attachment_texts = (
            [(a.filename, attachment_text(a)) for a in mail.attachments]
            if extract_attachment_text
            else []
        )
    return values, attachment_texts


def contains_term(value: str, needle: str, numeric_pattern: re.Pattern | None) -> bool:
    return (
        numeric_pattern.search(value) is not None
        if numeric_pattern is not None
        else needle in value
    )


class ContainsMatcher:
    def __init__(self, terms: list[SearchTerm], fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS):
        if set(fields) - set(SEARCH_FIELDS):
            raise ValueError("Unbekanntes Suchfeld.")
        self.terms = []
        for term in terms:
            needle = term.term.casefold()
            numeric_pattern = (
                re.compile(rf"(?<!\d){re.escape(needle)}(?!\d)") if needle.isdecimal() else None
            )
            self.terms.append((term, needle, numeric_pattern))
        self.fields = fields

    def match(self, mail: NormalizedEmail) -> dict[str, list[str]]:
        return self.match_details(mail).buckets

    def match_details(self, mail: NormalizedEmail) -> MatchResult:
        """Record actual fields for each term while extracting attachments only once per mail."""
        values, extracted_attachments = searchable_values(
            mail, extract_attachment_text="attachment_content" in self.fields
        )
        return self._match_values(values, extracted_attachments)

    def match_details_with_attachment_text(
        self, mail: NormalizedEmail, attachment_texts: list[tuple[str, str]]
    ) -> MatchResult:
        """Exact match using attachment text already persisted in the local index."""
        values, extracted_attachments = searchable_values(mail, attachment_texts)
        return self._match_values(values, extracted_attachments)

    def _match_values(
        self, values: dict[str, str], extracted_attachments: list[tuple[str, str]]
    ) -> MatchResult:
        haystacks = {f: values[f].casefold() for f in self.fields if f != "attachment_content"}
        attachment_values = (
            [(name, text.casefold()) for name, text in extracted_attachments]
            if "attachment_content" in self.fields
            else []
        )
        matches: dict[str, list[str]] = {}
        locations: dict[str, list[str]] = {}
        for term, needle, numeric_pattern in self.terms:
            found = [
                field
                for field, value in haystacks.items()
                if contains_term(value, needle, numeric_pattern)
            ]
            found.extend(
                f"attachment_content:{name}"
                for name, text in attachment_values
                if contains_term(text, needle, numeric_pattern)
            )
            if found:
                matches.setdefault(term.bucket, []).append(term.term)
                locations[term.term] = found
        return MatchResult(matches, locations)
