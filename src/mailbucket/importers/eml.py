import logging
from collections.abc import Iterator
from pathlib import Path

from mailbucket.importers.normalize import normalize
from mailbucket.models import NormalizedEmail


class EmlImporter:
    def supports(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".eml"

    def iter_emails(self, path: Path) -> Iterator[NormalizedEmail]:
        try:
            yield normalize(
                path.read_bytes(),
                source_type="EML",
                source_file=str(path),
                source_folder=str(path.parent),
                source_index=0,
            )
        except Exception:
            logging.getLogger(__name__).exception("EML konnte nicht gelesen werden: %s", path)
