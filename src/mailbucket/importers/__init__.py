"""Small importer registry; register optional adapters without changing the pipeline."""

import logging
from collections.abc import Iterator
from pathlib import Path

from mailbucket.importers.base import Importer
from mailbucket.importers.eml import EmlImporter
from mailbucket.importers.maildir import MaildirImporter
from mailbucket.importers.mbox import MboxImporter
from mailbucket.importers.takeout import TakeoutImporter
from mailbucket.models import NormalizedEmail

IMPORTERS: list[Importer] = [MaildirImporter(), EmlImporter(), MboxImporter(), TakeoutImporter()]


def register_importer(importer: Importer) -> None:
    """Register an optional EMLX/MSG/PST/OST adapter implementing Importer."""
    IMPORTERS.insert(0, importer)


def iter_source(path: Path) -> Iterator[NormalizedEmail]:
    path = path.expanduser().resolve()
    for importer in IMPORTERS:
        if importer.supports(path):
            yield from importer.iter_emails(path)
            return
    if path.is_dir():
        # Recursive traversal stops at a Maildir root to avoid reading its messages twice.
        for child in sorted(path.iterdir()):
            if child.is_symlink():
                continue
            if child.is_dir() or any(i.supports(child) for i in IMPORTERS):
                try:
                    yield from iter_source(child)
                except Exception:
                    logging.getLogger(__name__).exception("Quelle übersprungen: %s", child)
        return
    raise ValueError(f"Nicht unterstützte Quelle: {path.name} (EMLX/MSG/PST/OST erst später)")
