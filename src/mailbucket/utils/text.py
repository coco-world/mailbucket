import re

from bs4 import BeautifulSoup


def clean_text(value: str) -> str:
    value = value.encode("utf-8", errors="replace").decode("utf-8")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)


def html_to_text(html: str) -> str:
    """Extract text only; never fetch or execute embedded resources."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "noscript"]):
        tag.decompose()
    return clean_text(soup.get_text("\n", strip=True))
