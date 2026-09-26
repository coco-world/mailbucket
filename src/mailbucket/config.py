"""Run configuration, shared by UI and Python API."""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mailbucket.models import SearchTerm

SEARCH_GROUPS = {
    "Nachricht": {"subject": "Betreff", "body": "Nachrichtentext / Body"},
    "Personen": {
        "sender_name": "Absendername",
        "sender_email": "Absender-E-Mail-Adresse",
        "to": "Empfänger / An",
        "cc": "CC",
        "bcc": "BCC (soweit vorhanden)",
    },
    "Anhänge": {
        "attachment_names": "Dateinamen von Anhängen",
        "attachment_content": "Anhanginhalt (Text, HTML, PDF-Text; ohne OCR)",
    },
    "Herkunft und Header": {
        "message_id": "Message-ID / Internet Message ID",
        "labels": "Gmail Labels",
        "source_folder": "Mailbox / Ordnerpfad",
        "reply_to": "Reply-To",
        "in_reply_to": "In-Reply-To",
        "references": "References",
    },
}
SEARCH_LABELS = {key: label for group in SEARCH_GROUPS.values() for key, label in group.items()}
SEARCH_LABELS["from"] = "Absender"
SEARCH_FIELDS = tuple(SEARCH_LABELS)
DEFAULT_SEARCH_FIELDS = ("subject", "body", "sender_name", "sender_email", "to")

PDF_GROUPS = {
    "Standard-Maildaten": {
        "from": "Von",
        "date": "Gesendet / Datum",
        "to": "An",
        "cc": "CC",
        "bcc": "BCC",
        "subject": "Betreff",
        "attachments": "Anhänge",
    },
    "Technische Metadaten": {
        "message_id": "Message-ID / Internet Message ID",
        "source_type": "Quellformat",
        "source_file": "Archiv-Quelldatei (vollständiger Pfad)",
        "source_filename": "Dateiname der Quelldatei",
        "source_folder": "Mailbox / ursprünglicher Ordnerpfad",
        "source_index": "Mailbox-Position (nullbasiert)",
        "labels": "Gmail Labels",
        "reply_to": "Reply-To",
        "in_reply_to": "In-Reply-To",
        "references": "References",
    },
    "MailBucket-Daten": {
        "matched_terms": "Treffer / Suchbegriffe",
        "match_locations": "Fundstellen",
        "export_time": "Exportzeitpunkt",
        "version": "MailBucket-Version",
    },
}
PDF_LABELS = {key: label for group in PDF_GROUPS.values() for key, label in group.items()}
DEFAULT_PDF_FIELDS = ("from", "date", "to", "cc", "subject", "attachments")
FOOTER_LABELS = {
    "application": "MailBucket",
    "export_date": "Exportdatum",
    "mail_date": "Datum der E-Mail",
    "terms": "Suchbegriffe",
    "mailbox": "Mailbox",
    "page_number": "Seite / Gesamtseiten",
    "filename": "Dateiname der Exportdatei",
}
DEFAULT_FOOTER_FIELDS = ("application", "page_number")
MAX_SEARCH_WORKERS = 8
MAX_EXPORT_WORKERS = 4


def default_search_workers() -> int:
    """Leave one logical CPU responsive and avoid excessive attachment memory use."""
    return min(MAX_SEARCH_WORKERS, max(1, (os.cpu_count() or 2) - 1), 4)


def default_export_workers() -> int:
    """PDF work is memory and disk intensive, so a smaller pool is preferable."""
    return min(MAX_EXPORT_WORKERS, max(1, (os.cpu_count() or 2) - 1), 2)


@dataclass
class PdfOptions:
    custom_header: str = ""
    fields: tuple[str, ...] = DEFAULT_PDF_FIELDS
    footer_enabled: bool = True
    footer_fields: tuple[str, ...] = DEFAULT_FOOTER_FIELDS

    def validate(self) -> None:
        if not isinstance(self.custom_header, str):
            raise ValueError("Der freie PDF-Kopftext muss Text sein.")
        if set(self.fields) - set(PDF_LABELS) or set(self.footer_fields) - set(FOOTER_LABELS):
            raise ValueError("Unbekanntes PDF- oder Fußzeilenfeld.")

    @property
    def bucket_specific(self) -> bool:
        return bool(
            set(self.fields) & {"matched_terms", "match_locations"}
            or (self.footer_enabled and set(self.footer_fields) & {"terms", "filename"})
        )


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
    pdf: PdfOptions = field(default_factory=PdfOptions)

    def validate(self) -> None:
        if self.pdf_mode not in {"merge", "separate", "both"}:
            raise ValueError("PDF-Modus muss merge, separate oder both sein.")
        self.pdf.validate()


@dataclass
class RunConfig:
    sources: list[Path]
    terms: list[SearchTerm]
    output_dir: Path = field(default_factory=lambda: Path.home() / "MailBucket-Exports")
    run_name: str = field(default_factory=default_run_name)
    search_fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS
    deduplicate: bool = True
    export: ExportOptions = field(default_factory=ExportOptions)
    search_workers: int = field(default_factory=default_search_workers)
    export_workers: int = field(default_factory=default_export_workers)
    use_index: bool = False
    auto_index: bool = True

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
        if (
            type(self.search_workers) is not int
            or not 1 <= self.search_workers <= MAX_SEARCH_WORKERS
        ):
            raise ValueError(
                f"Parallele Such-Worker müssen zwischen 1 und {MAX_SEARCH_WORKERS} liegen."
            )
        if (
            type(self.export_workers) is not int
            or not 1 <= self.export_workers <= MAX_EXPORT_WORKERS
        ):
            raise ValueError(
                f"Parallele Ablage-Worker müssen zwischen 1 und {MAX_EXPORT_WORKERS} liegen."
            )
        if type(self.use_index) is not bool or type(self.auto_index) is not bool:
            raise ValueError("Indexoptionen müssen boolesche Werte sein.")
        self.export.validate()
