import logging
from collections.abc import Iterator
from pathlib import Path

from mailbucket.importers.normalize import normalize
from mailbucket.models import NormalizedEmail


class MaildirImporter:
    def supports(self, path: Path) -> bool:
        return path.is_dir() and all((path / p).is_dir() for p in ("cur", "new", "tmp"))

    def iter_emails(self, path: Path) -> Iterator[NormalizedEmail]:
        folders = [path] + sorted(p for p in path.rglob("*") if self.supports(p))
        index = 0
        for folder in folders:
            for sub in ("cur", "new"):
                for file in sorted((folder / sub).iterdir()):
                    if not file.is_file() or file.is_symlink():
                        continue
                    try:
                        yield normalize(
                            file.read_bytes(),
                            source_type="Maildir",
                            source_file=str(file),
                            source_folder=str(folder.relative_to(path)),
                            source_index=index,
                        )
                    except Exception:
                        logging.getLogger(__name__).exception("Defekte Maildir-Mail %s", file)
                    index += 1
