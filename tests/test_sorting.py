from mailbucket.models import NormalizedEmail
from mailbucket.utils.dates import parse_date, sort_key


def test_dates_order_and_ties():
    date = parse_date("Mon, 14 Sep 2026 08:31:42 +0200")
    early = parse_date("Mon, 14 Sep 2026 05:31:42 +0000")
    mails = [
        NormalizedEmail(date=None),
        NormalizedEmail(date=date, message_id="b"),
        NormalizedEmail(date=early),
        NormalizedEmail(date=date, message_id="a", source_index=2),
        NormalizedEmail(date=date, message_id="a", source_index=1),
    ]
    assert sorted(mails, key=sort_key) == [mails[2], mails[4], mails[3], mails[1], mails[0]]
    assert parse_date("garbage") is None and parse_date(None) is None
    assert parse_date("Mon, 14 Sep 2026 08:31:42").tzinfo is not None
