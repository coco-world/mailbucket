import csv
from datetime import datetime
from types import SimpleNamespace

from mailbucket.export.bucket_csv import COLUMNS, bucket_row, open_bucket_csv


def test_bucket_csv_keeps_one_physical_line_and_correct_columns_per_mail(tmp_path):
    path = tmp_path / "Treffer.csv"
    stream, writer = open_bucket_csv(path)
    try:
        for number in range(1, 4201):
            messy = number in {400, 401, 4000, 4001}
            separator = "\r\n" if messy else " "
            mail = SimpleNamespace(
                date=datetime(2026, 10, 29, 12, 34),
                date_raw=None,
                sender=f"Absender{separator}{number} <mail{number}@example.com>",
                to=[f"Empfänger {number}; Team <ziel{number}@example.com>"],
                body_text=(
                    f'Anfang {number}; "Zitat"\r\nFortsetzung {number}\u2028Ende'
                    if messy
                    else f"Nachricht {number}"
                ),
            )
            writer.writerow(bucket_row(mail))
    finally:
        stream.close()

    assert len(path.read_bytes().splitlines()) == 4201
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=";", strict=True)
        rows = list(reader)

    assert reader.fieldnames == COLUMNS
    assert len(rows) == 4200
    for number in (399, 400, 401, 402, 3999, 4000, 4001, 4002):
        row = rows[number - 1]
        assert row["Datum"] == "29.10.2026"
        assert row["Uhrzeit"] == "12:34:00"
        assert row["von"] == f"Absender {number} <mail{number}@example.com>"
        assert row["an"] == f"Empfänger {number}; Team <ziel{number}@example.com>"
        expected = (
            f'Anfang {number}; "Zitat" Fortsetzung {number} Ende'
            if number in {400, 401, 4000, 4001}
            else f"Nachricht {number}"
        )
        assert row["Text"] == expected
