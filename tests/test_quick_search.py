import mailbox

import pytest

from mailbucket.config import RunConfig
from mailbucket.index import IndexManager, IndexState
from mailbucket.models import SearchTerm
from mailbucket.pipeline import execute
from mailbucket.search.quick import search_sources, sort_hits


def make_source(path, make_mail):
    box = mailbox.mbox(path)
    box.add(
        make_mail(
            subject="Alpha im Betreff",
            body="Erster Brief",
            date="Mon, 14 Sep 2026 08:31:42 +0200",
            message_id="<subject@example.com>",
        )
    )
    box.add(
        make_mail(
            subject="Anderer Betreff",
            body="Alpha im Nachrichtentext",
            date="Tue, 15 Sep 2026 08:31:42 +0200",
            message_id="<body@example.com>",
        )
    )
    box.close()
    return path


def test_quick_results_sort_preview_and_export_selection(tmp_path, make_mail, monkeypatch):
    source = make_source(tmp_path / "mail.mbox", make_mail)
    monkeypatch.setenv("MAILBUCKET_INDEX_PATH", str(tmp_path / "indexes"))
    manager = IndexManager()
    manager.build(source)

    hits = search_sources(manager, [source], "Alpha", ("subject", "body"))
    assert len(hits) == 2
    assert sort_hits(hits, "relevance")[0].subject == "Alpha im Betreff"
    assert sort_hits(hits, "newest")[0].subject == "Anderer Betreff"
    assert sort_hits(hits, "oldest")[0].subject == "Alpha im Betreff"
    assert manager.get_mail(source, hits[0].record_id).raw_sha256 == hits[0].raw_sha256

    selected = next(hit for hit in hits if hit.subject == "Anderer Betreff")
    config = RunConfig(
        sources=[source],
        terms=[SearchTerm("Alpha", "Alpha")],
        output_dir=tmp_path / "exports",
        run_name="selection",
        search_fields=("subject", "body"),
        search_workers=1,
        export_workers=1,
        use_index=True,
        auto_index=False,
        selected_index_records={selected.source_id: {selected.record_id: selected.raw_sha256}},
    )

    def full_index_scan(*_args):
        raise AssertionError("Der Export ausgewählter Treffer darf keinen Gesamtscan starten.")

    monkeypatch.setattr(IndexManager, "_candidate_ids", staticmethod(full_index_scan))
    result = execute(config)

    assert result.stats.analyzed == 1
    assert result.stats.exported == 1
    assert len(list((result.output / "Alpha").glob("*.pdf"))) == 1
    assert "Anderer Betreff" in (result.output / "_manifest.csv").read_text(encoding="utf-8")
    assert "Alpha im Betreff" not in (result.output / "_manifest.csv").read_text(encoding="utf-8")


def test_selected_export_rejects_stale_index(tmp_path, make_mail, monkeypatch):
    source = make_source(tmp_path / "mail.mbox", make_mail)
    monkeypatch.setenv("MAILBUCKET_INDEX_PATH", str(tmp_path / "indexes"))
    manager = IndexManager()
    manager.build(source)
    hit = search_sources(manager, [source], "Alpha", ("subject",))[0]
    box = mailbox.mbox(source)
    box.add(make_mail(subject="Neu", message_id="<new@example.com>"))
    box.close()
    assert manager.status(source).state == IndexState.STALE

    config = RunConfig(
        sources=[source],
        terms=[SearchTerm("Alpha", "Alpha")],
        output_dir=tmp_path / "exports",
        run_name="selection",
        search_fields=("subject",),
        use_index=True,
        auto_index=False,
        selected_index_records={hit.source_id: {hit.record_id: hit.raw_sha256}},
    )
    with pytest.raises(RuntimeError, match="aktuellen Index"):
        execute(config)
    assert not (config.output_dir / config.run_name).exists()
