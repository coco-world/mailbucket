"""Contains matching and validated user input, independent of source formats."""

import csv
import io

from mailbucket.config import SEARCH_FIELDS
from mailbucket.models import NormalizedEmail, SearchTerm
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


class ContainsMatcher:
    def __init__(self, terms: list[SearchTerm], fields: tuple[str, ...] = SEARCH_FIELDS):
        self.terms = [(t, t.term.casefold()) for t in terms]
        self.fields = fields

    def match(self, mail: NormalizedEmail) -> dict[str, list[str]]:
        values = {
            "subject": mail.subject,
            "from": mail.sender,
            "to": "\n".join(mail.to),
            "cc": "\n".join(mail.cc),
            "body": mail.body_text,
            "attachment_names": "\n".join(a.filename for a in mail.attachments),
            "labels": "\n".join(mail.labels),
        }
        if "body" in self.fields and mail.body_html:
            values["body"] += "\n" + html_to_text(mail.body_html)
        haystacks = [values[f].casefold() for f in self.fields]
        matches: dict[str, list[str]] = {}
        for term, needle in self.terms:
            if any(needle in value for value in haystacks):
                matches.setdefault(term.bucket, []).append(term.term)
        return matches
