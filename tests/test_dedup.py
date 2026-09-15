from mailbucket.importers.normalize import normalize
from mailbucket.search.dedup import dedup_key


def test_message_id(make_mail):
    a = normalize(make_mail().as_bytes())
    b = normalize(make_mail(body="different copy").as_bytes())
    c = normalize(make_mail(message_id="<other@example.com>").as_bytes())
    assert dedup_key(a) == dedup_key(b)
    assert dedup_key(a) != dedup_key(c)


def test_fallback(make_mail):
    a = normalize(make_mail(message_id=None).as_bytes())
    b = normalize(make_mail(message_id=None).as_bytes())
    c = normalize(make_mail(message_id=None, body="different").as_bytes())
    assert dedup_key(a) == dedup_key(b)
    assert dedup_key(a) != dedup_key(c)
