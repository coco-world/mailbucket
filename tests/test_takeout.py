import io
import mailbox
import tarfile
import zipfile

import pytest

from mailbucket.importers import iter_source


@pytest.mark.parametrize("extension", ["zip", "tar", "tar.gz", "tgz"])
def test_archive_discovery_and_traversal(tmp_path, make_mail, extension):
    mbox = tmp_path / "temporary.mbox"
    box = mailbox.mbox(mbox)
    box.add(make_mail())
    box.close()
    data = mbox.read_bytes()
    archive = tmp_path / f"takeout.{extension}"
    if extension == "zip":
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("arbitrary/nested/Ungewöhnlicher Name.MBOX", data)
            z.writestr("other/second.mbox", data)
            z.writestr("../../escape.mbox", data)
            z.writestr("C:\\escape.mbox", data)
            link = zipfile.ZipInfo("link.mbox")
            link.external_attr = 0o120777 << 16
            z.writestr(link, data)
    else:
        with tarfile.open(archive, "w:gz" if extension != "tar" else "w") as t:
            for name in [
                "arbitrary/nested/Ungewöhnlicher Name.MBOX",
                "other/second.mbox",
                "../../escape.mbox",
            ]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("link.mbox")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../escape.mbox"
            t.addfile(link)
    mails = list(iter_source(archive))
    assert len(mails) == 2
    assert all(m.source_type == "Google Takeout" and m.source_file == str(archive) for m in mails)
    assert mails[0].source_folder == "arbitrary/nested/Ungewöhnlicher Name.MBOX"
    assert not (tmp_path.parent / "escape.mbox").exists()
