"""The manual download: checksums, extraction without the prefix, and nothing inside the repository.

Nothing is downloaded: the sources are patched to a small archive in `tmp_path` and read through a file:// URL,
and any attempt to open a network connection fails the test.
"""

import hashlib
import io
import socket
import tarfile
from pathlib import Path

import pytest

from workshop import manual

PREFIX = "CalculiX/ccx_2.21/doc/ccx/"
PARENTS = ["CalculiX", "CalculiX/ccx_2.21", "CalculiX/ccx_2.21/doc", "CalculiX/ccx_2.21/doc/ccx"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to use the network")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _dir(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    return info


def _file(name: str, data: bytes = b"<p>hello</p>\n") -> tuple[tarfile.TarInfo, io.BytesIO]:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    return info, io.BytesIO(data)


def _special(name: str, kind: bytes, linkname: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = linkname
    return info


def make_archive(path: Path, entries) -> tuple[str, str, int]:
    """Write a .tar.bz2 of `entries` (TarInfo, or (TarInfo, data)); return the (url, sha256, size) of a SOURCES entry."""
    with tarfile.open(path, "w:bz2") as tar:
        for entry in entries:
            if isinstance(entry, tuple):
                tar.addfile(*entry)
            else:
                tar.addfile(entry)
    data = path.read_bytes()
    return path.as_uri(), hashlib.sha256(data).hexdigest(), len(data)


def good_entries():
    return [
        *(_dir(name) for name in PARENTS),
        _file(PREFIX + "node1.html", b"<p>node one</p>\n"),
        _dir(PREFIX + "sub"),
        _file(PREFIX + "sub/page.html", b"<p>page</p>\n"),
        _dir(PREFIX + "empty"),
    ]


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Patch SOURCES['html'] to a good archive that lives outside the destination."""
    (tmp_path / "src").mkdir()
    source = make_archive(tmp_path / "src" / "manual.tar.bz2", good_entries())
    monkeypatch.setitem(manual.SOURCES, "html", source)
    return source


def _leftovers(dest: Path) -> list[Path]:
    """Everything below the destination's parent: nothing but the destination itself may remain after a failure."""
    return sorted(p for p in dest.parent.rglob("*") if not (p == dest or dest in p.parents))


def test_html_is_checked_and_extracted_without_the_prefix(tmp_path, archive):
    dest = tmp_path / "out" / "2.21"
    result = manual.fetch("html", dest, root=tmp_path / "repo")
    assert result == dest / "html"
    assert (dest / "html" / "node1.html").read_bytes() == b"<p>node one</p>\n"
    assert (dest / "html" / "sub" / "page.html").read_bytes() == b"<p>page</p>\n"
    assert (dest / "html" / "empty").is_dir()
    assert not (dest / "html" / "CalculiX").exists()
    assert _leftovers(dest) == []  # the temporary download and staging folder are gone


def test_a_second_download_replaces_the_files_and_keeps_the_others(tmp_path, archive):
    dest = tmp_path / "out"
    manual.fetch("html", dest, root=tmp_path / "repo")
    (dest / "html" / "node1.html").write_bytes(b"changed")
    (dest / "html" / "mine.txt").write_bytes(b"my notes")
    manual.fetch("html", dest, root=tmp_path / "repo")
    assert (dest / "html" / "node1.html").read_bytes() == b"<p>node one</p>\n"
    assert (dest / "html" / "mine.txt").read_bytes() == b"my notes"


def test_pdf_is_checked_and_written(tmp_path, monkeypatch):
    data = b"a stand-in for the manual, not a real one"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.bin").write_bytes(data)
    monkeypatch.setitem(manual.SOURCES, "pdf", ((tmp_path / "src" / "m.bin").as_uri(), hashlib.sha256(data).hexdigest(), len(data)))
    dest = tmp_path / "out" / "2.21"
    result = manual.fetch("pdf", dest, root=tmp_path / "repo")
    assert result == dest / "ccx_2.21.pdf"
    assert result.read_bytes() == data
    assert _leftovers(dest) == []


@pytest.mark.parametrize("kind", ["html", "pdf"])
@pytest.mark.parametrize("what", ["checksum", "size"])
def test_checksum_mismatch_keeps_nothing(tmp_path, monkeypatch, kind, what):
    source = tmp_path / "src.bin"
    source.write_bytes(b"not what was promised")
    sha = "0" * 64 if what == "checksum" else hashlib.sha256(source.read_bytes()).hexdigest()
    size = len(source.read_bytes()) + (0 if what == "checksum" else 1)
    monkeypatch.setitem(manual.SOURCES, kind, (source.as_uri(), sha, size))
    dest = tmp_path / "out" / "2.21"
    with pytest.raises(ValueError, match="checksum|size"):
        manual.fetch(kind, dest, root=tmp_path / "repo")
    assert not dest.exists() or not any(dest.rglob("*"))
    assert _leftovers(dest) == []


def test_download_stops_at_the_pinned_size(tmp_path, monkeypatch):
    class Endless(io.RawIOBase):
        reads = 0

        def readable(self):
            return True

        def readinto(self, buffer):
            Endless.reads += 1
            assert Endless.reads < 10_000, "the download did not stop"
            buffer[:] = b"x" * len(buffer)
            return len(buffer)

    monkeypatch.setitem(manual.SOURCES, "pdf", ("https://example.invalid/m.pdf", "0" * 64, 100_000))
    dest = tmp_path / "out"
    with pytest.raises(ValueError, match="size"):
        manual.fetch("pdf", dest, root=tmp_path / "repo", opener=lambda url, **kw: Endless())
    assert _leftovers(dest) == []
    assert Endless.reads < 100


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="html"):
        manual.fetch("epub", tmp_path / "out", root=tmp_path / "repo")


def _fetch_bad(tmp_path, monkeypatch, entries):
    (tmp_path / "src").mkdir(exist_ok=True)
    monkeypatch.setitem(manual.SOURCES, "html", make_archive(tmp_path / "src" / "bad.tar.bz2", entries))
    dest = tmp_path / "out" / "2.21"
    with pytest.raises(ValueError) as refused:
        manual.fetch("html", dest, root=tmp_path / "repo")
    assert not dest.exists() or not any(dest.rglob("*")), "nothing may be kept"
    assert _leftovers(dest) == []
    return str(refused.value)


def test_member_outside_the_prefix_is_refused(tmp_path, monkeypatch):
    entries = [*good_entries(), _file("CalculiX/ccx_2.21/src/ccx_2.21.c", b"int main;")]
    assert "outside" in _fetch_bad(tmp_path, monkeypatch, entries)


@pytest.mark.parametrize(
    "bad_name",
    [
        "other/page.html",
        "CalculiX/ccx_2.21/doc/ccx",  # the prefix without its slash, as a file
        "CalculiX/ccx_2.21/doc/ccxx/page.html",  # a sibling that merely starts the same
        "/etc/page.html",
        "../page.html",
        "page.html",
    ],
)
def test_other_file_names_are_refused(tmp_path, monkeypatch, bad_name):
    assert _fetch_bad(tmp_path, monkeypatch, [*good_entries(), _file(bad_name)])


def test_a_path_that_climbs_out_below_the_prefix_is_refused(tmp_path, monkeypatch):
    assert _fetch_bad(tmp_path, monkeypatch, [*good_entries(), _file(PREFIX + "../../escape.html")])
    assert not (tmp_path / "out" / "2.21" / "escape.html").exists()
    assert not (tmp_path / "out" / "escape.html").exists()


@pytest.mark.parametrize("bad_dir", ["other", "CalculiX/ccx_2.21/src", "CalculiX/ccx_2.21/doc/other", "."])
def test_a_directory_outside_the_prefix_is_refused(tmp_path, monkeypatch, bad_dir):
    assert _fetch_bad(tmp_path, monkeypatch, [*good_entries(), _dir(bad_dir)])


def test_parent_directory_entries_are_skipped(tmp_path, monkeypatch):
    entries = [
        _dir("CalculiX/"),
        _dir("./CalculiX/ccx_2.21/"),
        _dir("CalculiX/ccx_2.21/doc/"),
        _dir("CalculiX/ccx_2.21/doc/ccx/"),
        _file("./" + PREFIX + "node1.html"),
        _dir("./" + PREFIX + "sub/"),
    ]
    (tmp_path / "src").mkdir()
    monkeypatch.setitem(manual.SOURCES, "html", make_archive(tmp_path / "src" / "dirs.tar.bz2", entries))
    dest = tmp_path / "out"
    assert manual.fetch("html", dest, root=tmp_path / "repo") == dest / "html"
    assert (dest / "html" / "node1.html").is_file()
    assert (dest / "html" / "sub").is_dir()
    assert sorted(p.name for p in (dest / "html").iterdir()) == ["node1.html", "sub"]


@pytest.mark.parametrize(
    "special",
    [
        _special(PREFIX + "link.html", tarfile.SYMTYPE, "node1.html"),
        _special(PREFIX + "escape.html", tarfile.SYMTYPE, "../../../../../etc/passwd"),
        _special("CalculiX/ccx_2.21/elsewhere", tarfile.SYMTYPE, "doc"),
        _special("CalculiX/link", tarfile.SYMTYPE, "ccx_2.21"),
        _special(PREFIX + "pipe", tarfile.FIFOTYPE),
        _special(PREFIX + "tty", tarfile.CHRTYPE),
        _special("outside-device", tarfile.BLKTYPE),
    ],
    ids=["symlink", "symlink-out", "symlink-in-parents", "symlink-parent", "fifo", "chardev", "blockdev"],
)
def test_symlinks_devices_and_pipes_are_refused_anywhere(tmp_path, monkeypatch, special):
    assert "not allowed" in _fetch_bad(tmp_path, monkeypatch, [*good_entries(), special])


def _hard(name: str, target: str) -> tarfile.TarInfo:
    info = _special(name, tarfile.LNKTYPE, target)
    info.mode = 0o644
    return info


def test_a_hard_link_to_a_file_under_the_prefix_is_extracted_as_a_copy(tmp_path, monkeypatch):
    """The real archive has 31 of these (index.html -> ccx.html and 30 duplicate images): same content, own file."""
    image = bytes(range(256)) * 3  # binary, with NUL and 0xFF bytes
    entries = [
        *(_dir(name) for name in PARENTS),
        _file(PREFIX + "ccx.html", b"<p>the manual</p>\n"),
        _dir(PREFIX + "images/"),
        _file(PREFIX + "images/img001.png", image),
        _hard(PREFIX + "index.html", PREFIX + "ccx.html"),  # a link in the same folder
        _hard(PREFIX + "images/img002.png", PREFIX + "images/img001.png"),
        _hard("./" + PREFIX + "other.png", "./" + PREFIX + "images/img001.png"),  # ./ in the name and in the target
        _hard(PREFIX + "copy/of/ccx.html", PREFIX + "ccx.html"),  # a new sub-folder, no directory member
    ]
    (tmp_path / "src").mkdir()
    monkeypatch.setitem(manual.SOURCES, "html", make_archive(tmp_path / "src" / "links.tar.bz2", entries))
    dest = tmp_path / "out" / "2.21"
    html = manual.fetch("html", dest, root=tmp_path / "repo")
    assert (html / "index.html").read_bytes() == b"<p>the manual</p>\n"
    assert (html / "images" / "img002.png").read_bytes() == image
    assert (html / "other.png").read_bytes() == image
    assert (html / "copy" / "of" / "ccx.html").read_bytes() == b"<p>the manual</p>\n"
    for name in ("index.html", "images/img002.png", "other.png"):
        assert (html / name).is_file() and not (html / name).is_symlink()
    (html / "index.html").write_bytes(b"changed")  # a copy: the target does not change with it
    assert (html / "ccx.html").read_bytes() == b"<p>the manual</p>\n"
    assert _leftovers(dest) == []


def test_a_hard_link_copies_the_member_that_came_before_it(tmp_path, monkeypatch):
    """A link names the member that came before it, as tar does: the order of the archive is kept."""
    entries = [
        *(_dir(name) for name in PARENTS),
        _file(PREFIX + "a.html", b"first"),
        _hard(PREFIX + "b.html", PREFIX + "a.html"),
        _file(PREFIX + "a.html", b"second"),  # the same name again, after the link
    ]
    (tmp_path / "src").mkdir()
    monkeypatch.setitem(manual.SOURCES, "html", make_archive(tmp_path / "src" / "order.tar.bz2", entries))
    html = manual.fetch("html", tmp_path / "out", root=tmp_path / "repo")
    assert (html / "b.html").read_bytes() == b"first"
    assert (html / "a.html").read_bytes() == b"second"


@pytest.mark.parametrize(
    "link_name, target, fragment",
    [
        (PREFIX + "x.html", "CalculiX/ccx_2.21/src/ccx_2.21.c", "outside"),  # a target outside the prefix
        (PREFIX + "x.html", "other/node1.html", "outside"),
        (PREFIX + "x.html", "/etc/passwd", "outside"),
        (PREFIX + "x.html", PREFIX + "../../src/ccx_2.21.c", "unsafe"),
        (PREFIX + "x.html", PREFIX + "missing.html", "missing"),  # no such member
        (PREFIX + "x.html", PREFIX + "later.html", "missing"),  # a member that comes after the link
        (PREFIX + "x.html", PREFIX + "sub", "regular file"),  # a directory
        (PREFIX + "x.html", PREFIX + "alias.html", "regular file"),  # a link to a link
        ("other/x.html", PREFIX + "node1.html", "outside"),  # a good target, but the link itself is outside
        (PREFIX + "../x.html", PREFIX + "node1.html", "unsafe"),
    ],
)
def test_a_hard_link_to_anything_else_is_refused(tmp_path, monkeypatch, link_name, target, fragment):
    entries = [*good_entries(), _hard(PREFIX + "alias.html", PREFIX + "node1.html"), _hard(link_name, target), _file(PREFIX + "later.html")]
    assert fragment in _fetch_bad(tmp_path, monkeypatch, entries)


def test_a_hard_link_named_like_a_drive_is_refused(tmp_path, monkeypatch):
    """On Windows "C:/x" below the staging folder would be absolute; the name is refused on every platform."""
    entries = [*good_entries(), _hard(PREFIX + "C:/x/owned.txt", PREFIX + "node1.html")]
    assert "unsafe path" in _fetch_bad(tmp_path, monkeypatch, entries)


def test_a_hard_link_to_itself_is_refused(tmp_path, monkeypatch):
    entries = [*good_entries(), _hard(PREFIX + "node1.html", PREFIX + "node1.html")]
    assert "itself" in _fetch_bad(tmp_path, monkeypatch, entries)


def test_a_hard_link_to_a_symlink_is_refused(tmp_path, monkeypatch):
    entries = [*good_entries(), _special(PREFIX + "sym.html", tarfile.SYMTYPE, "node1.html"), _hard(PREFIX + "x.html", PREFIX + "sym.html")]
    assert "not allowed" in _fetch_bad(tmp_path, monkeypatch, entries)


@pytest.mark.parametrize("dest_parts", [("manual",), ("a", "..", "manual"), ()])
def test_destination_inside_the_repository_is_refused(tmp_path, root, dest_parts):
    calls = []

    def opener(url, **kwargs):
        calls.append(url)
        raise AssertionError("must not download")

    repo = tmp_path / "repo"
    repo.mkdir()
    dest = repo.joinpath(*dest_parts)
    with pytest.raises(ValueError, match="the manual must not go into the repository"):
        manual.fetch("html", dest, opener=opener, root=repo)
    assert calls == []
    assert list(repo.iterdir()) == []  # nothing was created in it
    # the real repository root is refused the same way, without creating anything
    inside = root / "calculix-manual-test-only"
    with pytest.raises(ValueError, match="the manual must not go into the repository"):
        manual.fetch("pdf", inside, opener=opener)
    assert not inside.exists() and calls == []


def test_destination_that_reaches_the_repository_through_a_link_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    link = tmp_path / "alias"
    try:
        link.symlink_to(repo, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    with pytest.raises(ValueError, match="must not go into the repository"):
        manual.fetch("html", link / "manual", opener=lambda *a, **k: pytest.fail("download"), root=repo)


def test_a_destination_whose_output_folder_would_be_the_repository_is_refused(tmp_path):
    repo = tmp_path / "html"  # dest/html would be the repository itself
    repo.mkdir()
    with pytest.raises(ValueError, match="must not go into the repository"):
        manual.fetch("html", tmp_path, opener=lambda *a, **k: pytest.fail("download"), root=repo)


def test_a_sibling_of_the_repository_is_fine(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "src").mkdir()
    monkeypatch.setitem(manual.SOURCES, "html", make_archive(tmp_path / "src" / "m.tar.bz2", good_entries()))
    assert manual.fetch("html", tmp_path / "repo-manual", root=repo) == tmp_path / "repo-manual" / "html"


def test_pinned_sources():
    assert manual.SOURCES == {
        "html": (
            "https://www.dhondt.de/ccx_2.21.htm.tar.bz2",
            "1ed21976ba2188d334fe0b5917cf75b8065b9c0b939e6bd35bd98ed57a725ba2",
            3032254,
        ),
        "pdf": (
            "https://www.dhondt.de/ccx_2.21.pdf",
            "16b6bab5a3f1a40a21fff62379f95c804a58d93758ab2e9a489b18d911dc20c8",
            5306787,
        ),
    }
    assert manual.HTML_PREFIX == "CalculiX/ccx_2.21/doc/ccx/"
    assert manual.DEFAULT_DEST == Path.home() / "calculix-manual" / "2.21"


def test_main_prints_the_url_the_note_and_the_folder(tmp_path, archive, capsys):
    dest = tmp_path / "out"
    assert manual.main(["html", "--dest", str(dest)]) == 0
    out = capsys.readouterr().out
    assert archive[0] in out  # the URL
    assert "The manual comes with CalculiX (GPL). It is for your own use here and is never committed to the repository." in out
    assert f"Folder to give MCP-Anything: {dest / 'html'}" in out
    assert (dest / "html" / "node1.html").is_file()


def test_main_defaults_to_the_html_manual_and_the_default_destination(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(manual, "fetch", lambda kind, dest: seen.append((kind, dest)) or dest / "html")
    assert manual.main([]) == 0
    assert seen == [("html", manual.DEFAULT_DEST)]


def test_main_gives_the_folder_of_the_pdf(tmp_path, monkeypatch, capsys):
    data = b"pdf stand-in"
    (tmp_path / "m.bin").write_bytes(data)
    monkeypatch.setitem(manual.SOURCES, "pdf", ((tmp_path / "m.bin").as_uri(), hashlib.sha256(data).hexdigest(), len(data)))
    assert manual.main(["pdf", "--dest", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path / "out" / "ccx_2.21.pdf") in out
    assert f"Folder to give MCP-Anything: {tmp_path / 'out'}" in out


def test_main_reports_a_failed_check_without_a_traceback(tmp_path, monkeypatch, capsys):
    (tmp_path / "m.bin").write_bytes(b"data")
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "m.bin").as_uri(), "0" * 64, 4))
    assert manual.main(["html", "--dest", str(tmp_path / "out")]) == 1
    assert "checksum" in capsys.readouterr().err


def test_main_reports_a_missing_file_without_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone.bin").as_uri(), "0" * 64, 4))
    assert manual.main(["html", "--dest", str(tmp_path / "out")]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_main_refuses_the_repository(root, capsys):
    assert manual.main(["html", "--dest", str(root / "manual-test-only")]) == 1
    assert "must not go into the repository" in capsys.readouterr().err
    assert not (root / "manual-test-only").exists()


def test_unknown_kind_is_a_usage_error():
    with pytest.raises(SystemExit) as stop:
        manual.main(["epub"])
    assert stop.value.code == 2


# ---- --archive: a copy that the instructor downloaded beforehand ------------------------------------------------------
# It goes through exactly the same size and SHA-256 check and the same extraction as a download, and skips only the
# download itself. The SOURCES url points to a file that does not exist, so any attempt to download fails the test.


def _no_download(*args, **kwargs):
    raise AssertionError("the local archive must not be downloaded")


@pytest.fixture
def handed_out(tmp_path, monkeypatch):
    """A good archive in its own folder; SOURCES['html'] pins its size and SHA-256 but names a url that is gone."""
    folder = tmp_path / "hand-out"
    folder.mkdir()
    path = folder / "ccx_2.21.htm.tar.bz2"
    _, sha256, size = make_archive(path, good_entries())
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone.tar.bz2").as_uri(), sha256, size))
    return path


def test_a_good_local_archive_is_accepted_without_a_download(tmp_path, handed_out):
    dest = tmp_path / "out" / "2.21"
    result = manual.fetch("html", dest, root=tmp_path / "repo", opener=_no_download, archive=handed_out)
    assert result == dest / "html"
    assert (dest / "html" / "node1.html").read_bytes() == b"<p>node one</p>\n"
    assert (dest / "html" / "sub" / "page.html").read_bytes() == b"<p>page</p>\n"
    assert (dest / "html" / "empty").is_dir()
    assert not (dest / "html" / "CalculiX").exists()
    assert handed_out.is_file()  # the instructor's copy is left alone
    assert _leftovers(dest) == []


def test_a_good_local_pdf_is_accepted(tmp_path, monkeypatch):
    data = b"a stand-in for the manual, not a real one"
    local = tmp_path / "hand-out" / "ccx_2.21.pdf"
    local.parent.mkdir()
    local.write_bytes(data)
    monkeypatch.setitem(manual.SOURCES, "pdf", ((tmp_path / "gone.pdf").as_uri(), hashlib.sha256(data).hexdigest(), len(data)))
    dest = tmp_path / "out" / "2.21"
    result = manual.fetch("pdf", dest, root=tmp_path / "repo", opener=_no_download, archive=local)
    assert result == dest / "ccx_2.21.pdf"
    assert result.read_bytes() == data
    assert local.read_bytes() == data
    assert _leftovers(dest) == []


@pytest.mark.parametrize("kind", ["html", "pdf"])
@pytest.mark.parametrize("what", ["checksum", "size-more", "size-less"])
def test_a_local_file_with_a_wrong_hash_or_size_is_refused_and_nothing_is_extracted(tmp_path, monkeypatch, kind, what):
    local = tmp_path / "hand-out" / "copy.bin"
    local.parent.mkdir()
    if kind == "html":
        make_archive(local, good_entries())
    else:
        local.write_bytes(b"not what was promised")
    data = local.read_bytes()
    sha = "0" * 64 if what == "checksum" else hashlib.sha256(data).hexdigest()
    size = len(data) + {"checksum": 0, "size-more": 1, "size-less": -1}[what]
    monkeypatch.setitem(manual.SOURCES, kind, ((tmp_path / "gone").as_uri(), sha, size))
    dest = tmp_path / "out" / "2.21"
    with pytest.raises(ValueError, match="checksum|size") as refused:
        manual.fetch(kind, dest, root=tmp_path / "repo", opener=_no_download, archive=local)
    assert str(local) in str(refused.value)  # it names the file that was refused
    assert not dest.exists() or not any(dest.rglob("*"))
    assert _leftovers(dest) == []
    assert local.read_bytes() == data


def test_the_pdf_is_not_accepted_as_the_html_archive(tmp_path, monkeypatch):
    pdf = tmp_path / "hand-out" / "ccx_2.21.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF a stand-in")
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone.tar.bz2").as_uri(), "1" * 64, 3032254))
    assert manual.main(["html", "--archive", str(pdf), "--dest", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*"))


def test_a_local_archive_is_extracted_with_the_same_safety_checks(tmp_path, monkeypatch):
    """A symbolic link, a name outside the prefix or a drive name is refused even when the hash is the pinned one."""
    bad_members = [
        _special(PREFIX + "link.html", tarfile.SYMTYPE, "node1.html"),
        _file("CalculiX/ccx_2.21/src/ccx_2.21.c", b"int main;"),
        _hard(PREFIX + "C:/x/owned.txt", PREFIX + "node1.html"),
        _hard(PREFIX + "x.html", "CalculiX/ccx_2.21/src/ccx_2.21.c"),
    ]
    for number, bad in enumerate(bad_members):
        local = tmp_path / "hand-out" / f"bad{number}.tar.bz2"
        local.parent.mkdir(exist_ok=True)
        _, sha256, size = make_archive(local, [*good_entries(), bad])
        monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone").as_uri(), sha256, size))
        dest = tmp_path / f"out{number}" / "2.21"
        with pytest.raises(ValueError):
            manual.fetch("html", dest, root=tmp_path / "repo", opener=_no_download, archive=local)
        assert not dest.exists() or not any(dest.rglob("*")), number
        assert _leftovers(dest) == [], number


def test_a_local_archive_extracts_a_hard_link_as_a_copy(tmp_path, monkeypatch):
    entries = [
        *(_dir(name) for name in PARENTS),
        _file(PREFIX + "ccx.html", b"<p>the manual</p>\n"),
        _hard(PREFIX + "index.html", PREFIX + "ccx.html"),
    ]
    local = tmp_path / "hand-out" / "links.tar.bz2"
    local.parent.mkdir()
    _, sha256, size = make_archive(local, entries)
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone").as_uri(), sha256, size))
    html = manual.fetch("html", tmp_path / "out", root=tmp_path / "repo", opener=_no_download, archive=local)
    assert (html / "index.html").read_bytes() == b"<p>the manual</p>\n"
    assert not (html / "index.html").is_symlink()


def test_a_missing_local_file_is_an_error_and_nothing_is_created(tmp_path, handed_out):
    dest = tmp_path / "out" / "2.21"
    with pytest.raises(OSError):
        manual.fetch("html", dest, root=tmp_path / "repo", opener=_no_download, archive=tmp_path / "no-such-file")
    assert not dest.exists() or not any(dest.rglob("*"))
    assert _leftovers(dest) == []


def test_a_local_archive_cannot_be_used_to_write_into_the_repository(tmp_path, handed_out):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="the manual must not go into the repository"):
        manual.fetch("html", repo / "manual", root=repo, opener=_no_download, archive=handed_out)
    assert list(repo.iterdir()) == []


def test_main_with_archive_says_so_and_does_not_download(tmp_path, handed_out, capsys):
    dest = tmp_path / "out"
    assert manual.main(["html", "--archive", str(handed_out), "--dest", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "Downloading" not in out
    assert f"Using your copy {handed_out}" in out
    assert "The manual comes with CalculiX (GPL)" in out
    assert f"Folder to give MCP-Anything: {dest / 'html'}" in out
    assert (dest / "html" / "node1.html").is_file()


def test_main_with_archive_passes_the_file_to_fetch(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(manual, "fetch", lambda kind, dest, **kw: seen.append((kind, dest, kw)) or dest / "html")
    assert manual.main(["pdf", "--archive", str(tmp_path / "m.pdf"), "--dest", str(tmp_path / "out")]) == 0
    assert seen == [("pdf", tmp_path / "out", {"archive": tmp_path / "m.pdf"})]


def test_main_without_archive_still_downloads(tmp_path, monkeypatch):
    """The default is unchanged: fetch gets no archive."""
    seen = []
    monkeypatch.setattr(manual, "fetch", lambda kind, dest, **kw: seen.append((kind, dest, kw)) or dest / "html")
    assert manual.main(["html", "--dest", str(tmp_path / "out")]) == 0
    assert seen == [("html", tmp_path / "out", {})]


def test_main_refuses_a_wrong_local_file_loudly(tmp_path, monkeypatch, capsys):
    local = tmp_path / "hand-out" / "ccx_2.21.htm.tar.bz2"
    local.parent.mkdir()
    local.write_bytes(b"a page that says the site is down")
    monkeypatch.setitem(manual.SOURCES, "html", ((tmp_path / "gone").as_uri(), "0" * 64, 3032254))
    assert manual.main(["html", "--archive", str(local), "--dest", str(tmp_path / "out")]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error:")
    assert str(local) in captured.err
    assert "pinned" in captured.err
    assert "Saved" not in captured.out
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*"))


def test_main_reports_a_missing_local_file_without_a_traceback(tmp_path, handed_out, capsys):
    assert manual.main(["html", "--archive", str(tmp_path / "no-such-file"), "--dest", str(tmp_path / "out")]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_main_help_names_the_archive_option(capsys):
    with pytest.raises(SystemExit) as stop:
        manual.main(["--help"])
    assert stop.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--archive FILE" in help_text
    assert "SHA-256" in help_text  # it says the copy is checked like a download
