"""Versioned local UI preferences; never persist mail contents, terms or source paths."""

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mailbucket.config import DEFAULT_SEARCH_FIELDS, SEARCH_FIELDS, ExportOptions, PdfOptions


@dataclass
class Preferences:
    search_fields: tuple[str, ...] = DEFAULT_SEARCH_FIELDS
    deduplicate: bool = True
    export: ExportOptions = field(default_factory=ExportOptions)


def settings_path() -> Path:
    override = os.environ.get("MAILBUCKET_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "MailBucket" / "settings.json"


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
        if type(data["deduplicate"]) is not bool or type(pdf_data["footer_enabled"]) is not bool:
            raise ValueError("Ungültiger Schalter")
        pdf_data["fields"] = tuple(pdf_data["fields"])
        pdf_data["footer_fields"] = tuple(pdf_data["footer_fields"])
        export = ExportOptions(**export_data, pdf=PdfOptions(**pdf_data))
        export.validate()
        return Preferences(tuple(search), data["deduplicate"], export)
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
