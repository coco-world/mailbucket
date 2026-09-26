import json

from mailbucket.branding import find_logo
from mailbucket.config import ExportOptions, PdfOptions
from mailbucket.settings import (
    Preferences,
    indexes_path,
    load_preferences,
    save_preferences,
    settings_path,
)


def test_round_trip_and_no_mail_data(tmp_path):
    path = tmp_path / "config" / "settings.json"
    preferences = Preferences(
        ("bcc", "message_id"),
        False,
        ExportOptions(
            pdf=PdfOptions(
                custom_header="Interner Prüfvermerk",
                fields=("subject", "message_id"),
                footer_enabled=False,
                footer_fields=(),
            )
        ),
        6,
        3,
        False,
    )
    save_preferences(preferences, path)
    assert load_preferences(path) == preferences
    data = json.loads(path.read_text())
    assert set(data) == {
        "schema_version",
        "search_fields",
        "deduplicate",
        "export",
        "search_workers",
        "export_workers",
        "auto_index",
    }
    assert not list(path.parent.glob(".settings-*"))


def test_old_settings_receive_parallel_defaults(tmp_path):
    path = tmp_path / "settings.json"
    current = Preferences()
    save_preferences(current, path)
    data = json.loads(path.read_text())
    data.pop("search_workers")
    data.pop("export_workers")
    path.write_text(json.dumps(data))

    loaded = load_preferences(path)

    assert loaded.search_workers == Preferences().search_workers
    assert loaded.export_workers == Preferences().export_workers


def test_invalid_preferences_fallback(tmp_path):
    path = tmp_path / "settings.json"
    for content in [
        "broken",
        "null",
        '{"schema_version":42}',
        '{"schema_version":1,"search_fields":["nonexistent"]}',
    ]:
        path.write_text(content)
        assert load_preferences(path) == Preferences()


def test_settings_override(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    monkeypatch.setenv("MAILBUCKET_SETTINGS_PATH", str(path))
    assert settings_path() == path
    assert load_preferences() == Preferences()


def test_index_path_override(tmp_path, monkeypatch):
    path = tmp_path / "portable-indexes"
    monkeypatch.setenv("MAILBUCKET_INDEX_PATH", str(path))
    assert indexes_path() == path


def test_supplied_logo_is_packaged():
    path = find_logo()
    assert path is not None and path.name == "logo_mailbucket.png"
    assert path.read_bytes().startswith(b"\x89PNG")
