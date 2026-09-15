import json

from mailbucket.models import NormalizedEmail
from mailbucket.utils.hashing import sha256


def dedup_key(mail: NormalizedEmail) -> str:
    if mail.message_id:
        return "message-id:" + mail.message_id.strip()
    fields = [
        mail.date.isoformat() if mail.date else mail.date_raw,
        mail.sender,
        mail.to,
        mail.cc,
        mail.bcc,
        mail.subject,
        mail.body_text,
        [(a.filename, a.sha256) for a in mail.attachments],
    ]
    return "sha256:" + sha256(
        json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
