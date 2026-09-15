"""Run configuration, shared by UI and Python API."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mailbucket.models import SearchTerm

SEARCH_FIELDS = ("subject", "body", "from", "to", "cc", "attachment_names", "labels")


def default_run_name() -> str:
    return datetime.now().strftime("%y%m%d_Lauf1")


@dataclass
class ExportOptions:
    timestamp_names: bool = False
    include_attachments: bool = True
    pdf_mode: str = "merge"  # merge, separate, both
    images_as_pages: bool = True
    save_originals: bool = True
    cover_pages: bool = True

    def validate(self) -> None:
        if self.pdf_mode not in {"merge", "separate", "both"}:
            raise ValueError("PDF-Modus muss merge, separate oder both sein.")


@dataclass
class RunConfig:
    sources: list[Path]
    terms: list[SearchTerm]
    output_dir: Path = field(default_factory=lambda: Path.home() / "MailBucket-Exports")
    run_name: str = field(default_factory=default_run_name)
    search_fields: tuple[str, ...] = SEARCH_FIELDS
    deduplicate: bool = True
    export: ExportOptions = field(default_factory=ExportOptions)

    def validate(self) -> None:
        if not self.sources:
            raise ValueError("Bitte mindestens eine Quelle auswählen.")
        if not self.terms or any(not t.term.strip() or not t.bucket.strip() for t in self.terms):
            raise ValueError("Bitte gültige Suchbegriffe und Bucket-Namen eingeben.")
        if not self.search_fields or set(self.search_fields) - set(SEARCH_FIELDS):
            raise ValueError("Bitte gültige Suchfelder auswählen.")
        for source in self.sources:
            if not source.exists():
                raise ValueError(f"Quelle existiert nicht: {source}")
        self.export.validate()
