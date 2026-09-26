"""Small importer registry; register optional adapters without changing the pipeline."""

import logging
import zipfile
from collections.abc import Iterator
from pathlib import Path

from mailbucket.importers.base import Importer
from mailbucket.importers.eml import EmlImporter
from mailbucket.importers.maildir import MaildirImporter
from mailbucket.importers.mbox import MboxImporter
from mailbucket.importers.takeout import TakeoutImporter, safe_member
from mailbucket.models import NormalizedEmail

IMPORTERS: list[Importer] = [MaildirImporter(), EmlImporter(), MboxImporter(), TakeoutImporter()]


def register_importer(importer: Importer) -> None:
    """Register an optional EMLX/MSG/PST/OST adapter implementing Importer."""
    IMPORTERS.insert(0, importer)


def estimate_source_bytes(path: Path) -> int | None:
    """Cheap progress total without parsing every message before the real scan.

    ZIP central directories expose uncompressed MBOX sizes. Compressed TAR streams do not,
    so their total intentionally remains unknown instead of adding a costly first pass.
    """
    path = path.expanduser().resolve()
    if path.is_symlink():
        return 0
    if MaildirImporter().supports(path):
        folders = [path] + sorted(p for p in path.rglob("*") if MaildirImporter().supports(p))
        return sum(
            file.stat().st_size
            for folder in folders
            for sub in ("cur", "new")
            for file in (folder / sub).iterdir()
            if file.is_file() and not file.is_symlink()
        )
    if path.is_dir():
        totals = []
        for child in sorted(path.iterdir()):
            if child.is_symlink():
                continue
            if child.is_dir() or any(importer.supports(child) for importer in IMPORTERS):
                total = estimate_source_bytes(child)
                if total is None:
                    return None
                totals.append(total)
        return sum(totals)
    if path.is_file() and path.name.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as archive:
                return sum(
                    member.file_size
                    for member in archive.infolist()
                    if not member.is_dir()
                    and safe_member(member.filename)
                    and member.filename.lower().endswith(".mbox")
                )
        except (OSError, zipfile.BadZipFile):
            return path.stat().st_size
    if path.is_file() and path.name.lower().endswith((".tar.gz", ".tgz")):
        return None
    if path.is_file():
        return path.stat().st_size
    return None


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
