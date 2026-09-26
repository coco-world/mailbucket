"""Versioned local UI preferences; never persist mail contents, terms or source paths."""

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mailbucket.config import (
    DEFAULT_SEARCH_FIELDS,
    MAX_EXPORT_WORKERS,
    MAX_SEARCH_WORKERS,
    SEARCH_FIELDS,
    ExportOptions,
    PdfOptions,
    default_export_workers,
    default_search_workers,
)


@dataclass
class Preferences:
    search_fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS
    deduplicate: bool = True
    export: ExportOptions = field(default_factory=ExportOptions)
    search_workers: int = field(default_factory=default_search_workers)
    export_workers: int = field(default_factory=default_export_workers)
    auto_index: bool = True


def application_data_dir() -> Path:
    override = os.environ.get("MAILBUCKET_SETTINGS_PATH")
    if override:
        return Path(override).expanduser().parent
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "MailBucket"


def settings_path() -> Path:
    override = os.environ.get("MAILBUCKET_SETTINGS_PATH")
    return Path(override).expanduser() if override else application_data_dir() / "settings.json"


def indexes_path() -> Path:
    override = os.environ.get("MAILBUCKET_INDEX_PATH")
    return Path(override).expanduser() if override else application_data_dir() / "indexes"


def load_preferences(path: Path | None = None) -> Preferences:
    path = path or settings_path()
    if not path.exists():
        return Preferences()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Nicht unterstützte Einstellungsversion")
        search = data["search_fields"]
        export_data = dict(data["export"])
        pdf_data = dict(export_data.pop("pdf"))
        for values in (search, pdf_data["fields"], pdf_data["footer_fields"]):
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise ValueError("Ungültige Feldauswahl")
        if set(search) - set(SEARCH_FIELDS):
            raise ValueError("Unbekanntes Suchfeld")
        for key, value in export_data.items():
            if key != "pdf_mode" and type(value) is not bool:
                raise ValueError("Ungültiger Schalter")
        if not isinstance(pdf_data.get("custom_header", ""), str):
            raise ValueError("Ungültiger PDF-Kopftext")
        if type(data["deduplicate"]) is not bool or type(pdf_data["footer_enabled"]) is not bool:
            raise ValueError("Ungültiger Schalter")
        auto_index = data.get("auto_index", True)
        if type(auto_index) is not bool:
            raise ValueError("Ungültiger Index-Schalter")
        search_workers = data.get("search_workers", default_search_workers())
        export_workers = data.get("export_workers", default_export_workers())
        if (
            type(search_workers) is not int
            or not 1 <= search_workers <= MAX_SEARCH_WORKERS
            or type(export_workers) is not int
            or not 1 <= export_workers <= MAX_EXPORT_WORKERS
        ):
            raise ValueError("Ungültige Parallelität")
        pdf_data["fields"] = tuple(pdf_data["fields"])
        pdf_data["footer_fields"] = tuple(pdf_data["footer_fields"])
        export = ExportOptions(**export_data, pdf=PdfOptions(**pdf_data))
        export.validate()
        return Preferences(
            tuple(search),
            data["deduplicate"],
            export,
            search_workers,
            export_workers,
            auto_index,
        )
    except (OSError, ValueError, TypeError, KeyError):
        logging.getLogger(__name__).warning("Einstellungen unlesbar; Standards verwendet: %s", path)
        return Preferences()


def save_preferences(preferences: Preferences, path: Path | None = None) -> None:
    """Atomically replace preferences; keep a previous valid file if writing fails."""
    preferences.export.validate()
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".settings-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                {"schema_version": 1, **asdict(preferences)}, stream, ensure_ascii=False, indent=2
            )
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
