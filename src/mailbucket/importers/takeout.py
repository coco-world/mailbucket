"""Read discovered MBOX members without trusting archive paths or extracting links."""

import logging
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from mailbucket.importers.mbox import MboxImporter
from mailbucket.models import NormalizedEmail

log = logging.getLogger(__name__)


def safe_member(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and ":" not in name


class TakeoutImporter:
    def supports(self, path: Path) -> bool:
        return path.is_file() and path.name.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz"))

    def iter_emails(self, path: Path) -> Iterator[NormalizedEmail]:
        # Only one MBOX on disk at a time. No archive-controlled filesystem names are used.
        with tempfile.TemporaryDirectory(prefix="mailbucket-takeout-") as directory:
            temporary = Path(directory) / "mailbox.mbox"

            def read_member(stream, name: str):
                with stream, temporary.open("wb") as target:
                    shutil.copyfileobj(stream, target, length=1024 * 1024)
                for mail in MboxImporter().iter_emails(temporary):
                    mail.source_type = "Google Takeout"
                    mail.source_file = str(path)
                    mail.source_folder = name
                    yield mail
                temporary.unlink()

            found = False
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    for member in sorted(archive.infolist(), key=lambda m: m.filename):
                        if not safe_member(member.filename):
                            log.warning("Unsicherer Archivpfad übersprungen: %s", member.filename)
                            continue
                        if member.is_dir() or (member.external_attr >> 16) & 0o170000 == 0o120000:
                            continue
                        if member.filename.lower().endswith(".mbox"):
                            found = True
                            try:
                                yield from read_member(archive.open(member), member.filename)
                            except Exception:
                                log.exception(
                                    "Archiv-MBOX konnte nicht gelesen werden: %s", member.filename
                                )
            else:
                with tarfile.open(path, "r|*") as archive:
                    for member in archive:
                        if not safe_member(member.name):
                            log.warning("Unsicherer Archivpfad übersprungen: %s", member.name)
                            continue
                        if member.isfile() and member.name.lower().endswith(".mbox"):
                            found = True
                            try:
                                yield from read_member(archive.extractfile(member), member.name)
                            except Exception:
                                log.exception(
                                    "Archiv-MBOX konnte nicht gelesen werden: %s", member.name
                                )
            if not found:
                log.warning("Keine MBOX-Dateien im Archiv: %s", path)
