import logging
import mailbox
from collections.abc import Iterator
from pathlib import Path

from mailbucket.importers.normalize import normalize
from mailbucket.models import NormalizedEmail


class MboxImporter:
    def supports(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".mbox"

    def iter_emails(self, path: Path) -> Iterator[NormalizedEmail]:
        box = mailbox.mbox(str(path), create=False)
        try:
            for index, key in enumerate(box.iterkeys()):
                try:
                    yield normalize(
                        box.get_bytes(key),
                        source_type="MBOX",
                        source_file=str(path),
                        source_folder=path.name,
                        source_index=index,
                    )
                except Exception:
                    logging.getLogger(__name__).exception("Defekte MBOX-Mail %s #%s", path, index)
        finally:
            box.close()
