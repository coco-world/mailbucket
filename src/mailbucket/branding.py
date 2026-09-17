"""Locate the supplied logo in an editable checkout or installed package."""

from pathlib import Path


def find_logo() -> Path | None:
    package = Path(__file__).resolve().parent
    for directory in (package / "assets", package.parent.parent / "assets"):
        if directory.is_dir():
            candidates = sorted(
                p
                for p in directory.iterdir()
                if p.is_file()
                and "logo" in p.stem.lower()
                and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}
            )
            if candidates:
                return candidates[0]
    return None
