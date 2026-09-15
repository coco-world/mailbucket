"""Portable names with deterministic protection against sanitization collisions."""

import hashlib
import re
import unicodedata

_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{p}{n}" for p in ("COM", "LPT") for n in "123456789¹²³"
}


def safe_name(value: str, max_bytes: int = 120) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value).strip(" .")
    if not value:
        value = "Unbenannt"
    if value.split(".")[0].upper() in _RESERVED:
        value = "_" + value
    encoded = value.encode("utf-8", errors="replace")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore").rstrip(" .") or "Unbenannt"


def unique_names(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    used: set[str] = set()
    for value in sorted(set(values)):
        name = safe_name(value)
        if name.casefold() in used or name.startswith("_"):
            suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
            name = safe_name(value, 95) + "_" + suffix
        while name.casefold() in used:
            name += "_"
        used.add(name.casefold())
        result[value] = name
    return result
