"""SQLite schema and FTS5 capability detection."""

import sqlite3

SCHEMA_VERSION = 1
FTS_COLUMNS = (
    "subject",
    "body",
    "sender_name",
    "sender_email",
    "sender_raw",
    "recipients_to",
    "cc",
    "bcc",
    "attachment_names",
    "attachment_content",
    "labels",
    "message_id",
    "source_folder",
    "reply_to",
    "in_reply_to",
    "references_text",
)


def supports_trigram(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE temp.mailbucket_trigram_test "
            "USING fts5(value, tokenize='trigram')"
        )
        connection.execute("DROP TABLE temp.mailbucket_trigram_test")
        return True
    except sqlite3.DatabaseError:
        return False


def create_schema(connection: sqlite3.Connection) -> str:
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE mails (
            id INTEGER PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_folder TEXT,
            source_index INTEGER,
            message_id TEXT,
            date_iso TEXT,
            date_raw TEXT,
            sender TEXT NOT NULL,
            recipients_to TEXT NOT NULL,
            cc TEXT NOT NULL,
            bcc TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_text TEXT NOT NULL,
            body_html TEXT,
            attachment_names TEXT NOT NULL,
            labels TEXT NOT NULL,
            headers TEXT NOT NULL,
            raw_sha256 TEXT NOT NULL,
            source_bytes INTEGER NOT NULL,
            dedup_key TEXT NOT NULL
        );

        CREATE INDEX mails_source_locator
        ON mails(source_file, source_folder, source_index);

        CREATE TABLE attachment_text (
            mail_id INTEGER NOT NULL REFERENCES mails(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY(mail_id, position)
        );
        """
    )
    tokenizer = "trigram" if supports_trigram(connection) else "unicode61 remove_diacritics 0"
    columns = ", ".join(FTS_COLUMNS)
    connection.execute(
        f"CREATE VIRTUAL TABLE mail_fts USING fts5({columns}, tokenize='{tokenizer}')"
    )
    return tokenizer


def read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return dict(connection.execute("SELECT key, value FROM metadata"))


def write_metadata(connection: sqlite3.Connection, values: dict[str, object]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        [(key, str(value)) for key, value in values.items()],
    )
