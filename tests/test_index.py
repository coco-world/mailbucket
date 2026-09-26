import mailbox
import sqlite3
import zipfile

import pytest

from mailbucket.config import RunConfig
from mailbucket.importers.normalize import normalize
from mailbucket.index import IndexManager, IndexState
from mailbucket.index.fingerprint import source_id
from mailbucket.pipeline import execute
from mailbucket.search.matcher import ContainsMatcher, parse_terms


def make_mbox(path, make_mail):
    path.parent.mkdir(parents=True, exist_ok=True)
    box = mailbox.mbox(path)
    first = make_mail(subject="Projekt Alpha 242340", message_id="<alpha>")
    first.add_attachment(b"AttachmentOnly", maintype="text", subtype="plain", filename="notes.txt")
    box.add(first)
    box.add(make_mail(subject="Nummer 124234056", message_id="<other>"))
    box.close()
    return path


def test_index_reuse_search_and_original_loading(tmp_path, make_mail):
    source = make_mbox(tmp_path / "a.mbox", make_mail)
    manager = IndexManager(tmp_path / "indexes")
    updates = []

    built = manager.build(source, updates.append)

    assert built.state == IndexState.CURRENT
    assert built.mail_count == 2
    assert manager.status(source).state == IndexState.CURRENT
    assert updates[-1].done == 2 and updates[-1].processed_bytes > 0

    search_updates = []
    subject = manager.search(
        source,
        parse_terms("Alpha"),
        ("subject",),
        lambda done, total: search_updates.append((done, total)),
    )
    numeric = manager.search(source, parse_terms("242340"), ("subject",))
    attachment = manager.search(source, parse_terms("AttachmentOnly"), ("attachment_content",))
    assert [match.mail.message_id for match in subject] == ["<alpha>"]
    assert search_updates[-1][0] == search_updates[-1][1]
    assert [match.mail.message_id for match in numeric] == ["<alpha>"]
    assert attachment[0].locations == {"AttachmentOnly": ["attachment_content:notes.txt"]}
    originals = manager.load_original_matches(source, attachment)
    assert originals[attachment[0].record_id].attachments[0].data == b"AttachmentOnly"


def test_numeric_boundaries_match_classic_search(tmp_path, make_mail):
    source = make_mbox(tmp_path / "numbers.mbox", make_mail)
    manager = IndexManager(tmp_path / "indexes")
    manager.build(source)

    matches = manager.search(source, parse_terms("242340"), ("subject",))

    assert [match.mail.message_id for match in matches] == ["<alpha>"]


def test_each_source_has_its_own_index(tmp_path, make_mail):
    source_a = make_mbox(tmp_path / "one" / "mail.mbox", make_mail)
    source_b = make_mbox(tmp_path / "two" / "mail.mbox", make_mail)
    manager = IndexManager(tmp_path / "indexes")

    info_a = manager.build(source_a)

    assert source_id(source_a) != source_id(source_b)
    assert manager.status(source_a).state == IndexState.CURRENT
    assert manager.status(source_b).state == IndexState.NOT_INDEXED
    assert info_a.index_path.exists()


def test_switching_a_b_a_reuses_only_the_matching_index(tmp_path, make_mail):
    source_a = make_mbox(tmp_path / "one" / "mail.mbox", make_mail)
    source_b = tmp_path / "two" / "mail.eml"
    source_b.parent.mkdir()
    source_b.write_bytes(
        make_mail(subject="Nur Quelle B", message_id="<source-b@example.com>").as_bytes()
    )
    manager = IndexManager(tmp_path / "indexes")

    first_a = manager.build(source_a)
    built_b = manager.build(source_b)
    second_a = manager.status(source_a)

    assert first_a.index_path != built_b.index_path
    assert second_a.state == IndexState.CURRENT
    assert second_a.index_path == first_a.index_path
    assert manager.search(source_a, parse_terms("Alpha"), ("subject",))
    assert not manager.search(source_a, parse_terms("Nur Quelle B"), ("subject",))
    assert manager.search(source_b, parse_terms("Nur Quelle B"), ("subject",))


def test_takeout_index_loads_only_matching_originals(tmp_path, make_mail):
    mbox_path = make_mbox(tmp_path / "mailbox.mbox", make_mail)
    source = tmp_path / "takeout.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.write(mbox_path, "Takeout/Mail/Alle Nachrichten.mbox")
    manager = IndexManager(tmp_path / "indexes")
    manager.build(source)

    matches = manager.search(source, parse_terms("Alpha"), ("subject",))
    originals = manager.load_original_matches(source, matches)

    assert len(matches) == 1
    assert originals[matches[0].record_id].subject == "Projekt Alpha 242340"
    assert originals[matches[0].record_id].source_type == "Google Takeout"
    assert originals[matches[0].record_id].source_folder == "Takeout/Mail/Alle Nachrichten.mbox"


def test_file_and_directory_changes_make_index_stale(tmp_path, make_mail):
    source = make_mbox(tmp_path / "mail.mbox", make_mail)
    manager = IndexManager(tmp_path / "indexes")
    manager.build(source)
    box = mailbox.mbox(source)
    box.add(make_mail(subject="Neu", message_id="<new>"))
    box.close()
    assert manager.status(source).state == IndexState.STALE

    folder = tmp_path / "folder"
    folder.mkdir()
    eml = folder / "one.eml"
    eml.write_bytes(make_mail().as_bytes())
    manager.build(folder)
    eml.write_bytes(make_mail(subject="Geändert").as_bytes())
    assert manager.status(folder).state == IndexState.STALE


def test_failed_rebuild_keeps_previous_index(tmp_path, make_mail, monkeypatch):
    import mailbucket.index.manager as module

    source = make_mbox(tmp_path / "mail.mbox", make_mail)
    manager = IndexManager(tmp_path / "indexes")
    original = manager.build(source)
    original_bytes = original.index_path.read_bytes()

    box = mailbox.mbox(source)
    box.add(make_mail(subject="Neu", message_id="<new>"))
    box.close()

    def broken(_source):
        raise RuntimeError("synthetic build failure")
        yield

    monkeypatch.setattr(module, "iter_source", broken)
    with pytest.raises(RuntimeError, match="synthetic"):
        manager.build(source)

    assert original.index_path.read_bytes() == original_bytes
    assert manager.status(source).state == IndexState.STALE
    assert not list((tmp_path / "indexes").glob("*.building.sqlite3"))


def test_corrupt_index_is_reported_and_can_be_deleted(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    source.write_bytes(make_mail().as_bytes())
    manager = IndexManager(tmp_path / "indexes")
    manager.directory.mkdir()
    path = manager.directory / f"{source_id(source)}.sqlite3"
    path.write_bytes(b"not sqlite")

    assert manager.status(source).state == IndexState.ERROR
    manager.delete(source)
    assert manager.status(source).state == IndexState.NOT_INDEXED


def test_schema_uses_fts5(tmp_path, make_mail):
    source = tmp_path / "source.eml"
    source.write_bytes(make_mail().as_bytes())
    manager = IndexManager(tmp_path / "indexes")
    info = manager.build(source)

    with sqlite3.connect(info.index_path) as connection:
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'mail_fts'"
        ).fetchone()[0]
        tokenizer = connection.execute(
            "SELECT value FROM metadata WHERE key = 'fts_tokenizer'"
        ).fetchone()[0]
    assert "fts5" in sql.lower()
    assert tokenizer in {"trigram", "unicode61 remove_diacritics 0"}


def test_pipeline_builds_and_reuses_index_without_full_scan(tmp_path, make_mail, monkeypatch):
    import mailbucket.pipeline as pipeline

    source = make_mbox(tmp_path / "source.mbox", make_mail)
    index_dir = tmp_path / "indexes"
    monkeypatch.setenv("MAILBUCKET_INDEX_PATH", str(index_dir))
    config = RunConfig(
        [source],
        parse_terms("Alpha"),
        tmp_path / "out",
        "run",
        search_fields=("subject",),
        use_index=True,
        auto_index=True,
    )
    updates = []

    first = execute(config, dry_run=True, on_progress=updates.append)
    assert first.stats.hits == {"Alpha": 1}
    assert IndexManager().status(source).state == IndexState.CURRENT
    assert any(update.stage == "index" for update in updates)

    def forbidden(_source):
        raise AssertionError("current index unexpectedly fell back to the full scan")
        yield

    monkeypatch.setattr(pipeline, "iter_source", forbidden)
    updates.clear()
    second = execute(config, dry_run=True, on_progress=updates.append)

    assert second.stats.hits == first.stats.hits
    assert any(update.stage == "index_search" for update in updates)

    exported = execute(config)
    assert exported.stats.exported == 1
    assert len(list((exported.output / "Alpha").glob("*.pdf"))) == 1


def test_stale_index_is_never_used_when_auto_rebuild_is_disabled(tmp_path, make_mail, monkeypatch):
    source = make_mbox(tmp_path / "source.mbox", make_mail)
    index_dir = tmp_path / "indexes"
    monkeypatch.setenv("MAILBUCKET_INDEX_PATH", str(index_dir))
    manager = IndexManager()
    manager.build(source)
    box = mailbox.mbox(source)
    box.add(make_mail(subject="Frisch hinzugefügt", message_id="<fresh@example.com>"))
    box.close()
    assert manager.status(source).state == IndexState.STALE
    updates = []
    config = RunConfig(
        [source],
        parse_terms("Frisch hinzugefügt"),
        tmp_path / "out",
        "run",
        search_fields=("subject",),
        search_workers=1,
        use_index=True,
        auto_index=False,
    )

    result = execute(config, dry_run=True, on_progress=updates.append)

    assert result.stats.hits == {"Frisch hinzugefügt": 1}
    assert manager.status(source).state == IndexState.STALE
    assert any(update.phase.startswith("Quelle klassisch analysieren") for update in updates)


@pytest.mark.parametrize(
    "field,term",
    [
        ("subject", "Project-X"),
        ("body", "body-marker"),
        ("from", "<alice@"),
        ("sender_name", "Müller"),
        ("sender_email", "alice@example.com"),
        ("to", "bob@example.com"),
        ("cc", "dave@example.com"),
        ("bcc", "hidden@example.com"),
        ("attachment_names", "evidence.txt"),
        ("attachment_content", "attachment-marker"),
        ("labels", "Important"),
        ("message_id", "indexed@example.com"),
        ("source_folder", "IndexedFolder"),
        ("reply_to", "reply@example.com"),
        ("in_reply_to", "parent@example.com"),
        ("references", "root@example.com"),
    ],
)
def test_index_search_matches_classic_semantics(tmp_path, make_mail, field, term):
    message = make_mail(
        subject="Project-X",
        body="body-marker",
        message_id="<indexed@example.com>",
    )
    message["Bcc"] = "hidden@example.com"
    message["Reply-To"] = "reply@example.com"
    message["In-Reply-To"] = "<parent@example.com>"
    message["References"] = "<root@example.com> <parent@example.com>"
    message.add_attachment(
        b"attachment-marker", maintype="text", subtype="plain", filename="evidence.txt"
    )
    source = tmp_path / "IndexedFolder" / "source.eml"
    source.parent.mkdir()
    source.write_bytes(message.as_bytes())
    manager = IndexManager(tmp_path / "indexes")
    manager.build(source)
    terms = parse_terms(term)
    classic_mail = normalize(
        source.read_bytes(),
        source_type="EML",
        source_file=str(source),
        source_folder=str(source.parent),
        source_index=0,
    )

    classic = ContainsMatcher(terms, (field,)).match_details(classic_mail)
    indexed = manager.search(source, terms, (field,))

    assert bool(indexed) is bool(classic.buckets)
    if indexed:
        assert indexed[0].matches == classic.buckets
        assert indexed[0].locations == classic.locations
