"""Persistent, atomic, per-source SQLite/FTS5 index management."""

import json
import os
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from mailbucket import __version__
from mailbucket.importers import estimate_source_bytes, iter_source
from mailbucket.index.fingerprint import SourceIdentity, source_identity
from mailbucket.index.schema import (
    FTS_COLUMNS,
    SCHEMA_VERSION,
    create_schema,
    read_metadata,
    write_metadata,
)
from mailbucket.index.source_access import SourceLocator, load_originals
from mailbucket.models import Attachment, NormalizedEmail, SearchTerm
from mailbucket.search.attachment_text import attachment_text
from mailbucket.search.dedup import dedup_key
from mailbucket.search.matcher import ContainsMatcher, searchable_values


class IndexState(str, Enum):
    NOT_INDEXED = "NOT_INDEXED"
    CURRENT = "CURRENT"
    STALE = "STALE"
    BUILDING = "BUILDING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class IndexInfo:
    state: IndexState
    source_id: str
    source: Path
    source_type: str
    index_path: Path
    mail_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    index_bytes: int = 0
    source_bytes: int = 0
    error: str | None = None


@dataclass(frozen=True)
class IndexProgress:
    source: Path
    done: int
    processed_bytes: int
    total_bytes: int | None


@dataclass
class IndexedMatch:
    record_id: int
    mail: NormalizedEmail
    dedup: str
    matches: dict[str, list[str]]
    locations: dict[str, list[str]]

    @property
    def locator(self) -> SourceLocator:
        return SourceLocator(
            self.record_id,
            self.mail.source_type,
            self.mail.source_file,
            self.mail.source_folder,
            self.mail.source_index,
            self.mail.raw_sha256,
        )


class IndexManager:
    def __init__(self, directory: Path | None = None):
        if directory is None:
            from mailbucket.settings import indexes_path

            directory = indexes_path()
        self.directory = directory.expanduser()
        self._building: set[str] = set()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _paths(self, identity: SourceIdentity) -> tuple[Path, Path]:
        final = self.directory / f"{identity.source_id}.sqlite3"
        building = self.directory / f"{identity.source_id}.building.sqlite3"
        return final, building

    def _lock(self, identifier: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(identifier, threading.Lock())

    @staticmethod
    def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def status(self, source: Path) -> IndexInfo:
        try:
            identity = source_identity(source)
        except (OSError, ValueError) as error:
            source = source.expanduser()
            return IndexInfo(
                IndexState.ERROR,
                "",
                source,
                "unknown",
                self.directory / "unknown.sqlite3",
                error=str(error),
            )
        final, _ = self._paths(identity)
        if identity.source_id in self._building:
            return IndexInfo(
                IndexState.BUILDING,
                identity.source_id,
                Path(identity.canonical_path),
                identity.source_type,
                final,
                source_bytes=identity.source_bytes,
            )
        if not final.exists():
            return IndexInfo(
                IndexState.NOT_INDEXED,
                identity.source_id,
                Path(identity.canonical_path),
                identity.source_type,
                final,
                source_bytes=identity.source_bytes,
            )
        try:
            with self._connect(final, readonly=True) as connection:
                metadata = read_metadata(connection)
                required = {
                    "schema_version",
                    "source_id",
                    "canonical_path",
                    "source_type",
                    "source_fingerprint",
                    "mail_count",
                }
                if required - metadata.keys():
                    raise ValueError("Indexmetadaten sind unvollständig.")
                if metadata["source_id"] != identity.source_id:
                    raise ValueError("Index gehört zu einer anderen Quelle.")
                current = (
                    int(metadata["schema_version"]) == SCHEMA_VERSION
                    and metadata["canonical_path"] == identity.canonical_path
                    and metadata["source_type"] == identity.source_type
                    and metadata["source_fingerprint"] == identity.fingerprint
                )
                return IndexInfo(
                    IndexState.CURRENT if current else IndexState.STALE,
                    identity.source_id,
                    Path(identity.canonical_path),
                    identity.source_type,
                    final,
                    mail_count=int(metadata["mail_count"]),
                    created_at=metadata.get("created_at"),
                    updated_at=metadata.get("updated_at"),
                    index_bytes=final.stat().st_size,
                    source_bytes=identity.source_bytes,
                )
        except (OSError, sqlite3.DatabaseError, ValueError, KeyError) as error:
            return IndexInfo(
                IndexState.ERROR,
                identity.source_id,
                Path(identity.canonical_path),
                identity.source_type,
                final,
                index_bytes=final.stat().st_size if final.exists() else 0,
                source_bytes=identity.source_bytes,
                error=str(error),
            )

    def build(
        self,
        source: Path,
        on_progress: Callable[[IndexProgress], None] | None = None,
    ) -> IndexInfo:
        identity = source_identity(source)
        lock = self._lock(identity.source_id)
        with lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            final, building = self._paths(identity)
            self._building.add(identity.source_id)
            building.unlink(missing_ok=True)
            connection = None
            created_at = datetime.now().astimezone().isoformat()
            done = 0
            processed_bytes = 0
            total_bytes = estimate_source_bytes(source)
            try:
                connection = self._connect(building)
                tokenizer = create_schema(connection)
                write_metadata(
                    connection,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "source_id": identity.source_id,
                        "canonical_path": identity.canonical_path,
                        "source_type": identity.source_type,
                        "source_fingerprint": identity.fingerprint,
                        "created_at": created_at,
                        "updated_at": created_at,
                        "mail_count": 0,
                        "mailbucket_version": __version__,
                        "fts_tokenizer": tokenizer,
                    },
                )
                connection.commit()
                connection.execute("BEGIN")
                for mail in iter_source(source):
                    done += 1
                    processed_bytes += max(0, mail.source_bytes)
                    attachment_texts = [
                        (attachment.filename, attachment_text(attachment))
                        for attachment in mail.attachments
                    ]
                    values, _ = searchable_values(mail, attachment_texts)
                    cursor = connection.execute(
                        """
                        INSERT INTO mails(
                            source_type, source_file, source_folder, source_index,
                            message_id, date_iso, date_raw, sender, recipients_to,
                            cc, bcc, subject, body_text, body_html, attachment_names,
                            labels, headers, raw_sha256, source_bytes, dedup_key
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            mail.source_type,
                            mail.source_file,
                            mail.source_folder,
                            mail.source_index,
                            mail.message_id,
                            mail.date.isoformat() if mail.date else None,
                            mail.date_raw,
                            mail.sender,
                            json.dumps(mail.to, ensure_ascii=False),
                            json.dumps(mail.cc, ensure_ascii=False),
                            json.dumps(mail.bcc, ensure_ascii=False),
                            mail.subject,
                            mail.body_text,
                            mail.body_html,
                            json.dumps([a.filename for a in mail.attachments], ensure_ascii=False),
                            json.dumps(mail.labels, ensure_ascii=False),
                            json.dumps(mail.headers, ensure_ascii=False),
                            mail.raw_sha256,
                            mail.source_bytes,
                            dedup_key(mail),
                        ),
                    )
                    mail_id = cursor.lastrowid
                    connection.executemany(
                        """
                        INSERT INTO attachment_text(
                            mail_id, position, filename, mime_type, sha256, text
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                mail_id,
                                position,
                                attachment.filename,
                                attachment.mime_type,
                                attachment.sha256,
                                attachment_texts[position][1],
                            )
                            for position, attachment in enumerate(mail.attachments)
                        ],
                    )
                    fts_values = {
                        "subject": values["subject"],
                        "body": values["body"],
                        "sender_name": values["sender_name"],
                        "sender_email": values["sender_email"],
                        "sender_raw": values["from"],
                        "recipients_to": values["to"],
                        "cc": values["cc"],
                        "bcc": values["bcc"],
                        "attachment_names": values["attachment_names"],
                        "attachment_content": "\n".join(text for _, text in attachment_texts),
                        "labels": values["labels"],
                        "message_id": values["message_id"],
                        "source_folder": values["source_folder"],
                        "reply_to": values["reply_to"],
                        "in_reply_to": values["in_reply_to"],
                        "references_text": values["references"],
                    }
                    connection.execute(
                        f"INSERT INTO mail_fts(rowid, {', '.join(FTS_COLUMNS)}) "
                        f"VALUES (?, {', '.join('?' for _ in FTS_COLUMNS)})",
                        (mail_id, *(fts_values[column] for column in FTS_COLUMNS)),
                    )
                    if done % 250 == 0:
                        connection.commit()
                        connection.execute("BEGIN")
                    if on_progress:
                        on_progress(
                            IndexProgress(
                                Path(identity.canonical_path), done, processed_bytes, total_bytes
                            )
                        )
                connection.commit()
                current_identity = source_identity(source)
                if current_identity.fingerprint != identity.fingerprint:
                    raise RuntimeError("Quelle wurde während des Indexaufbaus verändert.")
                finished = datetime.now().astimezone().isoformat()
                write_metadata(
                    connection,
                    {
                        "source_fingerprint": current_identity.fingerprint,
                        "updated_at": finished,
                        "mail_count": done,
                        "status": "complete",
                    },
                )
                connection.commit()
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite-Integritätsprüfung fehlgeschlagen.")
                connection.close()
                connection = None
                os.replace(building, final)
                if on_progress:
                    on_progress(
                        IndexProgress(
                            Path(identity.canonical_path),
                            done,
                            total_bytes if total_bytes is not None else processed_bytes,
                            total_bytes,
                        )
                    )
                self._building.discard(identity.source_id)
                return self.status(source)
            except BaseException:
                if connection is not None:
                    connection.close()
                building.unlink(missing_ok=True)
                raise
            finally:
                self._building.discard(identity.source_id)

    def delete(self, source: Path) -> None:
        identity = source_identity(source)
        final, building = self._paths(identity)
        with self._lock(identity.source_id):
            final.unlink(missing_ok=True)
            building.unlink(missing_ok=True)

    def delete_index(self, info: IndexInfo) -> None:
        """Delete a listed index even when its original source is currently unavailable."""
        with self._lock(info.source_id):
            info.index_path.unlink(missing_ok=True)
            (self.directory / f"{info.source_id}.building.sqlite3").unlink(missing_ok=True)

    @staticmethod
    def _candidate_ids(
        connection: sqlite3.Connection,
        terms: list[SearchTerm],
        fields: tuple[str, ...],
        tokenizer: str,
    ) -> list[int]:
        fts_fields = {
            "subject": "subject",
            "body": "body",
            "from": "sender_raw",
            "sender_name": "sender_name",
            "sender_email": "sender_email",
            "to": "recipients_to",
            "cc": "cc",
            "bcc": "bcc",
            "attachment_names": "attachment_names",
            "attachment_content": "attachment_content",
            "labels": "labels",
            "message_id": "message_id",
            "source_folder": "source_folder",
            "reply_to": "reply_to",
            "in_reply_to": "in_reply_to",
            "references": "references_text",
        }
        reliable = tokenizer == "trigram" and all(
            len(term.term.casefold()) >= 3 and term.term.isascii() and "\x00" not in term.term
            for term in terms
        )
        selected = []
        for field in fields:
            if field in fts_fields:
                selected.append(fts_fields[field])
        selected = list(dict.fromkeys(selected))
        if reliable and selected:
            clauses = []
            for term in terms:
                quoted = term.term.replace('"', '""')
                clauses.extend(f'{column}:"{quoted}"' for column in selected)
            try:
                return [
                    row[0]
                    for row in connection.execute(
                        "SELECT rowid FROM mail_fts WHERE mail_fts MATCH ? ORDER BY rowid",
                        (" OR ".join(clauses),),
                    )
                ]
            except sqlite3.DatabaseError:
                pass
        return [row[0] for row in connection.execute("SELECT id FROM mails ORDER BY id")]

    @staticmethod
    def _mail_from_row(row: sqlite3.Row, attachments: list[sqlite3.Row]) -> NormalizedEmail:
        stored_names = json.loads(row["attachment_names"])
        return NormalizedEmail(
            source_type=row["source_type"],
            source_file=row["source_file"],
            source_folder=row["source_folder"],
            source_index=row["source_index"],
            message_id=row["message_id"],
            date=datetime.fromisoformat(row["date_iso"]) if row["date_iso"] else None,
            date_raw=row["date_raw"],
            sender=row["sender"],
            to=json.loads(row["recipients_to"]),
            cc=json.loads(row["cc"]),
            bcc=json.loads(row["bcc"]),
            subject=row["subject"],
            body_text=row["body_text"],
            body_html=row["body_html"],
            attachments=[
                Attachment(item["filename"], item["mime_type"], b"", item["sha256"])
                for item in attachments
            ]
            or [Attachment(name, "", b"", "") for name in stored_names],
            labels=json.loads(row["labels"]),
            raw_sha256=row["raw_sha256"],
            source_bytes=row["source_bytes"],
            headers=json.loads(row["headers"]),
        )

    def search(
        self,
        source: Path,
        terms: list[SearchTerm],
        fields: tuple[str, ...],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[IndexedMatch]:
        info = self.status(source)
        if info.state != IndexState.CURRENT:
            raise RuntimeError(f"Index ist nicht aktuell: {info.state.value}")
        matcher = ContainsMatcher(terms, fields)
        matches: list[IndexedMatch] = []
        with self._connect(info.index_path, readonly=True) as connection:
            metadata = read_metadata(connection)
            ids = self._candidate_ids(connection, terms, fields, metadata["fts_tokenizer"])
            if on_progress and not ids:
                on_progress(0, 0)
            for offset in range(0, len(ids), 500):
                batch = ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                mail_rows = connection.execute(
                    f"SELECT * FROM mails WHERE id IN ({placeholders}) ORDER BY id", batch
                ).fetchall()
                attachment_rows: dict[int, list[sqlite3.Row]] = {}
                if "attachment_content" in fields:
                    for row in connection.execute(
                        f"SELECT * FROM attachment_text WHERE mail_id IN ({placeholders}) "
                        "ORDER BY mail_id, position",
                        batch,
                    ):
                        attachment_rows.setdefault(row["mail_id"], []).append(row)
                for row in mail_rows:
                    attachments = attachment_rows.get(row["id"], [])
                    mail = self._mail_from_row(row, attachments)
                    extracted = [(item["filename"], item["text"]) for item in attachments]
                    details = matcher.match_details_with_attachment_text(mail, extracted)
                    if details.buckets:
                        matches.append(
                            IndexedMatch(
                                row["id"],
                                mail,
                                row["dedup_key"],
                                details.buckets,
                                details.locations,
                            )
                        )
                if on_progress:
                    on_progress(min(offset + len(batch), len(ids)), len(ids))
        return matches

    def load_original_matches(
        self, source: Path, matches: list[IndexedMatch]
    ) -> dict[int, NormalizedEmail]:
        if self.status(source).state != IndexState.CURRENT:
            raise RuntimeError("Quelle oder Index wurde seit der Suche verändert.")
        return load_originals(source, [match.locator for match in matches])

    def dedup_records(self, source: Path) -> list[tuple[int, str]]:
        info = self.status(source)
        if info.state != IndexState.CURRENT:
            raise RuntimeError(f"Index ist nicht aktuell: {info.state.value}")
        with self._connect(info.index_path, readonly=True) as connection:
            return [
                (row["id"], row["dedup_key"])
                for row in connection.execute("SELECT id, dedup_key FROM mails ORDER BY id")
            ]

    def list_indexes(self) -> list[IndexInfo]:
        result = []
        if not self.directory.exists():
            return result
        for path in sorted(self.directory.glob("*.sqlite3")):
            if path.name.endswith(".building.sqlite3"):
                continue
            try:
                with self._connect(path, readonly=True) as connection:
                    metadata = read_metadata(connection)
                source = Path(metadata["canonical_path"])
                if source.exists():
                    result.append(self.status(source))
                else:
                    result.append(
                        IndexInfo(
                            IndexState.STALE,
                            metadata["source_id"],
                            source,
                            metadata.get("source_type", "unknown"),
                            path,
                            mail_count=int(metadata.get("mail_count", 0)),
                            created_at=metadata.get("created_at"),
                            updated_at=metadata.get("updated_at"),
                            index_bytes=path.stat().st_size,
                            error="Quelle momentan nicht vorhanden.",
                        )
                    )
            except (OSError, sqlite3.DatabaseError, ValueError, KeyError) as error:
                result.append(
                    IndexInfo(
                        IndexState.ERROR,
                        path.stem,
                        Path(""),
                        "unknown",
                        path,
                        index_bytes=path.stat().st_size if path.exists() else 0,
                        error=str(error),
                    )
                )
        return result
