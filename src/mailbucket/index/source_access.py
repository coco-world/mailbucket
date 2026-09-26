"""Load only indexed hits from their original source for faithful PDF export."""

import mailbox
import shutil
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from mailbucket.importers import iter_source
from mailbucket.importers.normalize import normalize
from mailbucket.models import NormalizedEmail


@dataclass(frozen=True)
class SourceLocator:
    record_id: int
    source_type: str
    source_file: str
    source_folder: str | None
    source_index: int | None
    raw_sha256: str


def _normalized(raw: bytes, locator: SourceLocator) -> NormalizedEmail:
    mail = normalize(
        raw,
        source_type=locator.source_type,
        source_file=locator.source_file,
        source_folder=locator.source_folder,
        source_index=locator.source_index,
    )
    if mail.raw_sha256 != locator.raw_sha256:
        raise RuntimeError("Die Quelle wurde während der Suche verändert.")
    return mail


def _load_mbox(path: Path, locators: list[SourceLocator]) -> dict[int, NormalizedEmail]:
    wanted = {locator.source_index: locator for locator in locators}
    if None in wanted:
        raise RuntimeError("MBOX-Position fehlt im Index.")
    result = {}
    box = mailbox.mbox(str(path), create=False)
    try:
        keys = list(box.iterkeys())
        for index, locator in wanted.items():
            if index is None or index >= len(keys):
                raise RuntimeError("MBOX-Position existiert nicht mehr.")
            result[locator.record_id] = _normalized(box.get_bytes(keys[index]), locator)
    finally:
        box.close()
    return result


def _load_archive_member(
    archive_path: Path, member_name: str, locators: list[SourceLocator]
) -> dict[int, NormalizedEmail]:
    with tempfile.TemporaryDirectory(prefix="mailbucket-index-hit-") as directory:
        temporary = Path(directory) / "mailbox.mbox"
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                with archive.open(member_name) as source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        else:
            with tarfile.open(archive_path, "r:*") as archive:
                member = archive.getmember(member_name)
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError(f"Archiv-Mailbox fehlt: {member_name}")
                with source, temporary.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
        return _load_mbox(temporary, locators)


def load_originals(
    selected_source: Path, locators: list[SourceLocator]
) -> dict[int, NormalizedEmail]:
    """Resolve indexed hits without normalizing every message in the source again."""
    result: dict[int, NormalizedEmail] = {}
    direct = [locator for locator in locators if locator.source_type in {"EML", "Maildir"}]
    for locator in direct:
        result[locator.record_id] = _normalized(Path(locator.source_file).read_bytes(), locator)

    mboxes: dict[str, list[SourceLocator]] = defaultdict(list)
    archives: dict[tuple[str, str], list[SourceLocator]] = defaultdict(list)
    fallback: list[SourceLocator] = []
    for locator in locators:
        if locator in direct:
            continue
        if locator.source_type == "MBOX":
            mboxes[locator.source_file].append(locator)
        elif locator.source_type == "Google Takeout" and locator.source_folder:
            archives[(locator.source_file, locator.source_folder)].append(locator)
        else:
            fallback.append(locator)

    for source_file, grouped in mboxes.items():
        result.update(_load_mbox(Path(source_file), grouped))
    for (source_file, member), grouped in archives.items():
        result.update(_load_archive_member(Path(source_file), member, grouped))

    if fallback:
        wanted = {
            (item.source_file, item.source_folder, item.source_index, item.raw_sha256): item
            for item in fallback
        }
        for mail in iter_source(selected_source):
            key = (mail.source_file, mail.source_folder, mail.source_index, mail.raw_sha256)
            if key in wanted:
                result[wanted[key].record_id] = mail
                if len(result) == len(locators):
                    break
    if len(result) != len(locators):
        raise RuntimeError("Nicht alle indizierten Treffer konnten in der Quelle geladen werden.")
    return result
