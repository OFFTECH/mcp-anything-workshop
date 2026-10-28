"""Repository hygiene: no banned names, nothing third-party or binary, LF line endings, one place for the plugin repo.

Content and line-ending checks read what git stores (the index blob), not the working tree: on Windows
`core.autocrlf=true` may leave CRLF in the working tree for a file that git stores with LF.
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import git_output, in_git, repo_files, stored_bytes

from workshop import config

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BANNED_SHA256 = {  # sha256 of lowercased words that must never appear in the repo
    "88e5e0d6f84c712e71f9f089ce6ee14d317037ae21dc0a120a0a2575caf653dc",
    "3861be9df9a94051187cd82feedcdcb0ce9f8d520fff623182979464c410fa3f",
    "7a99293b698889e12401533b2a0feaa89e9c4018c3c25d75e3e918c9514c6236",
    "eabfcb4eb46b05e069778c3f0c4e1a5bb1e8e94f7eff6369c600815111c2dab0",
}
# MCP-Anything's text suffixes, plus the workshop's free-text formats (.inp .geo .conf .inc) and .lock (uv.lock is TOML)
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".tmpl", ".yml", ".yaml", ".sh", ".bat", ".cmd", ".cfg", ".ini"} | {
    ".inp",
    ".geo",
    ".conf",
    ".inc",
    ".lock",
}
EMBEDDED_LENGTHS = (5, 6)  # banned words are also looked for inside longer letter runs (camelCase, concatenations)
BLOCKED_SUFFIXES = {
    ".pdf", ".htm", ".html", ".ps", ".png", ".jpg", ".jpeg", ".gif", ".frd", ".dat", ".sta", ".cvg",
    ".msh", ".vtk", ".vtu", ".exe", ".dll", ".so", ".dylib", ".deb", ".rpm", ".zip", ".tar", ".gz",
    ".bz2", ".xz", ".7z", ".whl",
}  # fmt: skip
MAX_BYTES = 400_000
# Built from pieces so that this file does not contain them; they betray pasted manuals or licence texts.
DOC_MARKERS = ("latex2" + "html", "%PD" + "F-", "<!DOCTYPE " + "HTML", "This program is " + "free software")
THIS_FILE = "tests/test_repo_hygiene.py"


def _sha(word: str) -> str:
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def _banned_hits(text: str, banned=BANNED_SHA256):
    """Letter runs of `text` that match a banned hash as a whole word or through any embedded 5- or 6-letter substring."""
    hits = set()
    for token in set(re.findall(r"[A-Za-z]+", text)):
        low = token.lower()
        candidates = {low}
        for n in EMBEDDED_LENGTHS:
            candidates.update(low[i : i + n] for i in range(len(low) - n + 1))
        if any(_sha(c) in banned for c in candidates):
            hits.add(token)
    return sorted(hits)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _text_files(root: Path):
    """Yield (path, listed): listed is True for a known text suffix, False for suffix-less files (LICENSE, .gitignore ...)."""
    for path in repo_files(root):
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES:
            yield path, True
        elif suffix == "":
            yield path, False


def _scan(root: Path, banned=BANNED_SHA256):
    """Return (number of files scanned, offender descriptions). Never echoes a banned word."""
    scanned = 0
    offenders = []
    for path, listed in _text_files(root):
        rel = _rel(path, root)
        try:
            text = stored_bytes(root, rel).decode("utf-8")
        except UnicodeDecodeError:
            if listed:  # a listed text type that is not UTF-8 would escape the scan: fail loudly
                offenders.append(f"{rel}: not valid UTF-8")
            continue  # suffix-less file that is not text (binary): nothing to scan
        scanned += 1
        if _banned_hits(rel, banned):
            offenders.append(f"path name matches the banned list (sha256 of path {_sha(rel)[:12]})")
        if _banned_hits(text, banned):
            offenders.append(f"{rel}: banned name in content")
    return scanned, offenders


def test_no_banned_names(root):
    scanned, offenders = _scan(root)
    assert scanned > 0, "scanner found no text files: the walk is broken"
    assert offenders == []


def test_every_repo_file_is_scanned(root):
    """A new file type must be added to TEXT_SUFFIXES (and so to the scan) before it can be committed."""
    unscanned = [_rel(p, root) for p in repo_files(root) if p.suffix.lower() not in TEXT_SUFFIXES | {""}]
    assert unscanned == []


def test_banned_scanner_self_check():
    # harmless stand-in words, so that a broken tokeniser cannot pass silently
    banned = {_sha("harmless")}
    assert _banned_hits("a Harmless-word, other", banned) == ["Harmless"]
    assert _banned_hits("nothing to see", banned) == []
    banned = {_sha("widget"), _sha("apple")}  # a 6-letter and a 5-letter harmless word
    assert _banned_hits("myWidgetFactory", banned) == ["myWidgetFactory"]  # camelCase, 6 letters
    assert _banned_hits("pineappleJuice", banned) == ["pineappleJuice"]  # concatenation, 5 letters
    assert _banned_hits("my_widget = 1", banned) == ["widget"]  # whole token still found
    assert _banned_hits("wid get app le", banned) == []  # split words are not a match


def test_scan_fails_on_undecodable_listed_files_and_skips_binary_blobs(tmp_path):
    (tmp_path / "notes.md").write_bytes(b"caf" + bytes([0xE9]))  # cp1252 e-acute: not UTF-8
    (tmp_path / "data.txt").write_bytes("plain".encode("utf-16"))  # not UTF-8
    (tmp_path / "BLOB").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80]))  # suffix-less binary: silently skipped
    (tmp_path / "ok.py").write_text("x = 1", encoding="utf-8")
    scanned, offenders = _scan(tmp_path)
    assert scanned == 1
    assert sorted(offenders) == ["data.txt: not valid UTF-8", "notes.md: not valid UTF-8"]


def test_scan_reports_embedded_banned_word_in_content_and_path(tmp_path):
    banned = {_sha("widget")}
    (tmp_path / "a.md").write_text("see myWidgetFactory", encoding="utf-8")
    (tmp_path / "widgetfile.txt").write_text("clean", encoding="utf-8")
    scanned, offenders = _scan(tmp_path, banned)
    assert scanned == 2
    assert "a.md: banned name in content" in offenders
    assert len(offenders) == 2 and all("widget" not in o.lower() for o in offenders)


def test_no_third_party_or_binary_files(root):
    problems = []
    for path in repo_files(root):
        rel = _rel(path, root)
        data = stored_bytes(root, rel)
        if path.suffix.lower() in BLOCKED_SUFFIXES:
            problems.append(f"{rel}: blocked file type")
        if len(data) > MAX_BYTES:
            problems.append(f"{rel}: {len(data)} bytes is over {MAX_BYTES}")
        if b"\0" in data:
            problems.append(f"{rel}: binary content")
        if rel != THIS_FILE and any(marker in data.decode("utf-8", errors="replace") for marker in DOC_MARKERS):
            problems.append(f"{rel}: looks like pasted third-party documentation")
    assert problems == []


def _eol_problems(root: Path) -> list[str]:
    """With git: what git stores must be LF (index field i/lf, or i/none for an empty file) and every repo file must
    get `text: auto` and `eol: lf` from .gitattributes (untracked files are normalised when they are added).
    Without git: no carriage return in any file."""
    rels = [_rel(p, root) for p in repo_files(root)]
    if not in_git(root):
        return [f"{rel}: carriage return" for rel in rels if b"\r" in stored_bytes(root, rel)]
    problems = []
    listing = git_output(root, "ls-files", "-z", "--eol")
    if listing is None:
        return ["git ls-files --eol failed"]
    for record in listing.decode("utf-8").split("\0"):
        if record:
            info, _, name = record.partition("\t")
            index_eol = info.split()[0]
            if index_eol not in ("i/lf", "i/none"):
                problems.append(f"{name}: git stores {index_eol}")
    attrs = git_output(root, "check-attr", "-z", "--stdin", "text", "eol", stdin="".join(f"{r}\0" for r in rels).encode("utf-8"))
    if attrs is None:
        return problems + ["git check-attr failed"]
    fields = attrs.decode("utf-8").split("\0")
    got = {(fields[i], fields[i + 1]): fields[i + 2] for i in range(0, len(fields) - 2, 3)}
    for rel in rels:
        if (got.get((rel, "text")), got.get((rel, "eol"))) != ("auto", "lf"):
            problems.append(f"{rel}: .gitattributes does not give text=auto eol=lf")
    return problems


def test_text_files_use_lf(root):
    assert _eol_problems(root) == []


def _init_repo(repo: Path, autocrlf: str) -> None:
    repo.mkdir(exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True, timeout=60)
    subprocess.run(["git", "-C", str(repo), "config", "core.autocrlf", autocrlf], check=True, capture_output=True, timeout=60)


def _add(repo: Path, *paths: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", *paths], check=True, capture_output=True, timeout=60)


@needs_git
def test_stored_bytes_reads_the_index_not_the_working_tree(tmp_path):
    _init_repo(tmp_path, "true")
    (tmp_path / ".gitattributes").write_bytes(b"* text=auto eol=lf\n")
    (tmp_path / "tracked.md").write_bytes(b"one\r\ntwo\r\n")  # a CRLF working tree, as on Windows
    (tmp_path / "untracked.md").write_bytes(b"x\r\n")
    _add(tmp_path, ".gitattributes", "tracked.md")
    assert stored_bytes(tmp_path, "tracked.md") == b"one\ntwo\n"  # git normalised it on add
    assert (tmp_path / "tracked.md").read_bytes() == b"one\r\ntwo\r\n"  # the working tree still holds CRLF
    assert stored_bytes(tmp_path, "untracked.md") == b"x\r\n"  # not in the index: the working-tree bytes
    assert _eol_problems(tmp_path) == []  # the index is LF and the attributes are right


@needs_git
def test_eol_check_flags_crlf_in_the_index_and_missing_attributes(tmp_path):
    _init_repo(tmp_path, "false")
    (tmp_path / "bad.sh").write_bytes(b"echo hi\r\n")
    _add(tmp_path, "bad.sh")  # no .gitattributes, no autocrlf: git stores CRLF
    problems = _eol_problems(tmp_path)
    assert "bad.sh: git stores i/crlf" in problems
    assert "bad.sh: .gitattributes does not give text=auto eol=lf" in problems


def test_eol_check_without_git_flags_a_carriage_return(tmp_path):
    (tmp_path / "bad.md").write_bytes(b"a\r\nb\n")
    (tmp_path / "good.md").write_bytes(b"a\nb\n")
    assert not in_git(tmp_path)
    assert _eol_problems(tmp_path) == ["bad.md: carriage return"]


@needs_git
def test_repo_files_lists_what_git_lists_and_skips_ignored_files_and_virtualenvs(tmp_path):
    _init_repo(tmp_path, "false")
    for rel in ("tracked.md", "untracked.md", "ignored/notes.md", "venv-linux/lib/site.py", ".venv/x.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("text", encoding="utf-8")
    (tmp_path / "venv-linux" / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _add(tmp_path, "tracked.md", ".gitignore")
    assert in_git(tmp_path)
    assert [_rel(p, tmp_path) for p in repo_files(tmp_path)] == [".gitignore", "tracked.md", "untracked.md"]


@needs_git
def test_a_folder_inside_another_repository_is_walked(tmp_path):
    """A home folder under version control must not hide the files of a folder below it."""
    _init_repo(tmp_path, "false")
    (tmp_path / ".gitignore").write_text("inner/\n", encoding="utf-8")
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "a.md").write_text("x", encoding="utf-8")
    assert not in_git(inner)
    assert [_rel(p, inner) for p in repo_files(inner)] == ["a.md"]


def test_the_repository_itself_is_listed(root):
    files = {_rel(p, root) for p in repo_files(root)}
    assert {"workshop.conf", "workshop/config.py", THIS_FILE, "tests/conftest.py"} <= files
    assert not [f for f in files if f.startswith(".venv/")]


def test_every_json_file_parses(root):
    unparsable = []
    for path in repo_files(root):
        if path.suffix.lower() == ".json":
            rel = _rel(path, root)
            try:
                json.loads(stored_bytes(root, rel).decode("utf-8"))
            except ValueError as error:  # JSONDecodeError and UnicodeDecodeError are both ValueErrors
                unparsable.append(f"{rel}: {error}")
    assert unparsable == []


def test_the_placeholder_lives_only_in_workshop_conf(root):
    token = "YOUR-GITHUB-" + "OWNER"
    value = config.mcp_anything_repo()
    repo = value.split("#")[0]
    offenders = []
    for path in repo_files(root):
        rel = _rel(path, root)
        if rel in ("workshop.conf", "workshop/config.py"):  # config.py defines PLACEHOLDER
            continue
        text = stored_bytes(root, rel).decode("utf-8", errors="replace")
        if token in text:
            offenders.append(f"{rel}: contains the placeholder text; documents say 'the placeholder'")
        if not config.is_placeholder(value) and repo in text:
            offenders.append(f"{rel}: contains the configured repository; it is set only in workshop.conf")
    assert offenders == []


def test_gitignore_keeps_work_and_downloads_out(root):
    lines = stored_bytes(root, ".gitignore").decode("utf-8").splitlines()
    # the manual's two files, which an instructor may hand out to be given to `workshop.manual --archive`
    for entry in ("work/", "calculix-manual/", "*.tar.bz2", "*.pdf", "*.frd", "*.dat", "*_mesh.inp"):
        assert entry in lines
