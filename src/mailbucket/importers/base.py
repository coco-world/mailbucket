"""Importer extension protocol; adapters must yield the common normalized model."""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from mailbucket.models import NormalizedEmail


class Importer(Protocol):
    def supports(self, path: Path) -> bool: ...
    def iter_emails(self, path: Path) -> Iterator[NormalizedEmail]: ...
