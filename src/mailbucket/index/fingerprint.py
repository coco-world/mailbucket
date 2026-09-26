"""Stable source identity and inexpensive change detection."""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from mailbucket.importers.maildir import MaildirImporter

EDGE_BYTES = 64 * 1024


@dataclass(frozen=True)
class SourceIdentity:
    source_id: str
    canonical_path: str
    source_type: str
    fingerprint: str
    source_bytes: int


def canonical_source_path(source: Path) -> str:
    return os.path.normcase(str(source.expanduser().resolve()))


def source_type(source: Path) -> str:
    source = source.expanduser().resolve()
    if source.is_dir():
        return "maildir" if MaildirImporter().supports(source) else "directory"
    name = source.name.lower()
    if name.endswith(".mbox"):
        return "mbox"
    if name.endswith(".eml"):
        return "eml"
    if name.endswith(".zip"):
        return "takeout_zip"
    if name.endswith((".tar.gz", ".tgz")):
        return "takeout_tgz"
    if name.endswith(".tar"):
        return "takeout_tar"
    return "file"


def source_id(source: Path) -> str:
    canonical = canonical_source_path(source)
    kind = source_type(source)
    return hashlib.sha256(f"{kind}\0{canonical}".encode("utf-8")).hexdigest()


def _edge_signature(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        digest.update(stream.read(EDGE_BYTES))
        if size > EDGE_BYTES:
            stream.seek(max(0, size - EDGE_BYTES))
            digest.update(stream.read(EDGE_BYTES))
    return digest.hexdigest()


def _directory_entries(source: Path) -> tuple[list[list[int | str]], int]:
    entries: list[list[int | str]] = []
    total = 0
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        size = stat.st_size
        total += size
        entries.append([path.relative_to(source).as_posix(), size, stat.st_mtime_ns])
    return entries, total


def source_identity(source: Path) -> SourceIdentity:
    source = source.expanduser().resolve()
    canonical = canonical_source_path(source)
    kind = source_type(source)
    identifier = hashlib.sha256(f"{kind}\0{canonical}".encode("utf-8")).hexdigest()
    if source.is_dir():
        entries, total = _directory_entries(source)
        payload = {"kind": kind, "entries": entries}
    else:
        stat = source.stat()
        total = stat.st_size
        payload = {
            "kind": kind,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "edge_sha256": _edge_signature(source, stat.st_size),
        }
    fingerprint = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return SourceIdentity(identifier, canonical, kind, fingerprint, total)
