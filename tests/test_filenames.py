import pytest

from mailbucket.utils.filenames import safe_name, unique_names


@pytest.mark.parametrize(
    "name",
    [
        'a<b>c:d"e|f?g*h',
        "a/b",
        "a\\b",
        "a:b",
        "../../foo",
        "CON",
        "nul.txt",
        ".",
        " ",
        "ü" * 300,
        "abc. ",
    ],
)
def test_portable(name):
    result = safe_name(name)
    assert result and len(result.encode("utf-8")) <= 120
    assert all(c not in result for c in '<>:"/\\|?*')
    assert result not in {".", "..", "CON", "nul.txt"}
    assert not result.endswith((" ", "."))


def test_unicode_and_collision():
    assert safe_name("Müller") == "Müller"
    names = unique_names(["a/b", "a\\b", "ABC", "abc", "_manifest.csv"])
    assert len({n.casefold() for n in names.values()}) == 5
    assert names["_manifest.csv"] != "_manifest.csv"
