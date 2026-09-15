import mailbox

from mailbucket.importers import iter_source


def test_mbox(tmp_path, make_mail):
    path = tmp_path / "archive.mbox"
    box = mailbox.mbox(str(path))
    box.add(make_mail())
    box.add(make_mail(message_id="<two@example.com>"))
    box.close()
    mails = list(iter_source(path))
    assert len(mails) == 2
    assert [m.source_index for m in mails] == [0, 1]
    assert mails[0].source_file == str(path)


def test_nested_eml_directory(tmp_path, make_mail):
    folder = tmp_path / "deep"
    folder.mkdir()
    (folder / "a.EML").write_bytes(make_mail().as_bytes())
    (tmp_path / "b.eml").write_bytes(make_mail().as_bytes())
    assert len(list(iter_source(tmp_path))) == 2


def test_maildir_and_subfolders(tmp_path, make_mail):
    path = tmp_path / "maildir"
    box = mailbox.Maildir(path, create=True)
    box.add(make_mail())
    folder = box.add_folder("project")
    folder.add(make_mail(message_id="<sub@example.com>"))
    folder.close()
    box.close()
    mails = list(iter_source(tmp_path))
    assert len(mails) == 2
    assert all(m.source_type == "Maildir" for m in mails)


def test_broken_archive_in_directory_does_not_hide_other_sources(tmp_path, make_mail):
    (tmp_path / "a.zip").write_bytes(b"broken")
    (tmp_path / "b.eml").write_bytes(make_mail().as_bytes())
    assert len(list(iter_source(tmp_path))) == 1
