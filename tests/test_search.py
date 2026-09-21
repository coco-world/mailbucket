import pytest

from mailbucket.importers.normalize import normalize
from mailbucket.models import SearchTerm
from mailbucket.search.matcher import ContainsMatcher, parse_csv, parse_terms


@pytest.mark.parametrize(
    "field,term",
    [
        ("subject", "grüße"),
        ("body", "MUSTERMANN"),
        ("from", "ALICE"),
        ("to", "carol"),
        ("cc", "dave"),
        ("labels", "projekt müller"),
        ("attachment_names", "angebot"),
    ],
)
def test_fields(make_mail, field, term):
    msg = make_mail()
    msg.add_attachment(
        b"a", maintype="application", subtype="octet-stream", filename="Angebot.xlsx"
    )
    mail = normalize(msg.as_bytes())
    assert ContainsMatcher([SearchTerm(term, "B")], (field,)).match(mail) == {"B": [term]}
    assert not ContainsMatcher([SearchTerm("NO-MATCH", "B")], (field,)).match(mail)


def test_many_buckets_and_terms(make_mail):
    terms = parse_csv("term,bucket\n345678,A\nMustermann,B\nProjekt Alpha,B\n")
    assert ContainsMatcher(terms).match(normalize(make_mail().as_bytes())) == {
        "A": ["345678"],
        "B": ["Mustermann", "Projekt Alpha"],
    }


def test_input_and_field_exclusion(make_mail):
    assert parse_terms("\n a \n\nMüller\na") == [
        SearchTerm("a", "a"),
        SearchTerm("Müller", "Müller"),
    ]
    assert not ContainsMatcher(parse_terms("345678"), ("body",)).match(
        normalize(make_mail().as_bytes())
    )


def test_html_alternative_is_searchable(make_mail):
    msg = make_mail()
    msg.add_alternative("<p>Only-in-html</p>", subtype="html")
    assert ContainsMatcher(parse_terms("only-in-html")).match(normalize(msg.as_bytes()))


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("Vorgang 91235", False),
        ("Vorgang 9123", False),
        ("Vorgang 1235", False),
        ("Vorgang A123B", True),
        ("Vorgang 123.", True),
        ("Vorgang 91235 und 123", True),
    ],
)
def test_numeric_terms_require_digit_boundaries(make_mail, subject, expected):
    mail = normalize(make_mail(subject=subject).as_bytes())
    result = ContainsMatcher(parse_terms("123"), ("subject",)).match(mail)
    assert bool(result) is expected


@pytest.mark.parametrize(
    "text",
    [
        "bad,header\nx,y",
        "term,bucket\nx,",
        "term,bucket\nx,y,z",
        'term,bucket\n"broken',
        "term,bucket\n",
        "term,bucket\nx",
    ],
)
def test_invalid_csv(text):
    with pytest.raises(ValueError):
        parse_csv(text)


def test_csv_bom_and_quoted_comma():
    assert parse_csv('\ufeffterm,bucket\n"Müller, GmbH",Müller')[0] == SearchTerm(
        "Müller, GmbH", "Müller"
    )
