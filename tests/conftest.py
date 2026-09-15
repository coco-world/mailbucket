from email.message import EmailMessage

import pytest


@pytest.fixture
def make_mail():
    def make(
        subject="Vorgang 345678 – Grüße Müller",
        date="Mon, 14 Sep 2026 08:31:42 +0200",
        message_id="<one@example.com>",
        body="Hallo Bob, Projekt Alpha und Mustermann.",
    ):
        mail = EmailMessage()
        mail["From"] = "Alice Müller <alice@example.com>"
        mail["To"] = "Bob <bob@example.com>, Carol <carol@example.com>"
        mail["Cc"] = "dave@example.com"
        mail["Subject"] = subject
        if date is not None:
            mail["Date"] = date
        if message_id is not None:
            mail["Message-ID"] = message_id
        mail["X-Gmail-Labels"] = 'Inbox, Important, "Projekt Müller"'
        mail.set_content(body)
        return mail

    return make
