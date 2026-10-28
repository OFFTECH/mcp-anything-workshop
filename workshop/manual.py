"""Download the CalculiX 2.21 manual, only when a participant asks for it, and check it against pinned checksums.

    python3 -m workshop.manual [html|pdf] [--dest DIR] [--archive FILE]

The manual comes with CalculiX (GPL). It goes into the participant's own folder (default `~/calculix-manual/2.21`),
never into this repository. With `--archive FILE` the download is skipped: FILE is a copy that the instructor fetched
beforehand, and it is checked and extracted exactly like a download. Standard library only.
"""

import argparse
import errno
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from workshop.config import ROOT

SOURCES = {
    "html": ("https://www.dhondt.de/ccx_2.21.htm.tar.bz2", "1ed21976ba2188d334fe0b5917cf75b8065b9c0b939e6bd35bd98ed57a725ba2", 3032254),
    "pdf": ("https://www.dhondt.de/ccx_2.21.pdf", "16b6bab5a3f1a40a21fff62379f95c804a58d93758ab2e9a489b18d911dc20c8", 5306787),
}
HTML_PREFIX = "CalculiX/ccx_2.21/doc/ccx/"
DEFAULT_DEST = Path.home() / "calculix-manual" / "2.21"
PDF_NAME = "ccx_2.21.pdf"
HTML_DIR = "html"
NOTE = "The manual comes with CalculiX (GPL). It is for your own use here and is never committed to the repository."

CHUNK = 64 * 1024
TIMEOUT_S = 60.0  # per read of the connection, not for the whole download

# archive directories that hold the prefix: they carry nothing and are skipped
_PARENT_DIRS = {HTML_PREFIX.rstrip("/"), *(str(p) for p in PurePosixPath(HTML_PREFIX.rstrip("/")).parents if p.parts)}


def _inside(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def _check_destination(dest: Path, target: Path, root: Path) -> None:
    """Refuse a destination in the repository, or one whose output would be, or would contain, the repository."""
    root = root.resolve()
    if _inside(dest.resolve(), root) or _inside(target.resolve(), root) or _inside(root, target.resolve()):
        raise ValueError("the manual must not go into the repository")


def _checked_copy(kind: str, workdir: Path, open_source: Callable, label: str, hint: str = "") -> Path:
    """Copy a source of `kind` into a temporary file in `workdir`; it must match the pinned size and SHA-256.

    `open_source()` gives the readable source, a download or a local file. It is the one check for both: the temporary
    copy is what gets extracted, so a file cannot change between the check and the extraction. `label` names the source
    in the messages, and `hint` ends each of them.
    """
    _, sha256, size = SOURCES[kind]
    fd, name = tempfile.mkstemp(prefix=".ccx-manual-", suffix=".part", dir=workdir)
    path = Path(name)
    try:
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(fd, "wb") as out, open_source() as response:
            while chunk := response.read(CHUNK):
                total += len(chunk)
                if total > size:  # more than was pinned: stop here, do not fill the disk
                    raise ValueError(f"{label}: size is more than the pinned {size} bytes{hint}")
                digest.update(chunk)
                out.write(chunk)
        if total != size:
            raise ValueError(f"{label}: size is {total} bytes, the pinned size is {size}{hint}")
        if digest.hexdigest() != sha256:
            raise ValueError(f"{label}: checksum {digest.hexdigest()} does not match the pinned {sha256}{hint}")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _download(kind: str, workdir: Path, opener: Callable) -> Path:
    """Download the source of `kind` into a temporary file in `workdir`, checked against the pinned size and SHA-256."""
    url = SOURCES[kind][0]
    return _checked_copy(kind, workdir, lambda: opener(url, timeout=TIMEOUT_S), url)


def _local_copy(kind: str, workdir: Path, archive: Path) -> Path:
    """The same as `_download`, from the file `archive` that the instructor fetched beforehand."""
    hint = f" (it must be an unmodified copy of {SOURCES[kind][0]})"
    return _checked_copy(kind, workdir, lambda: open(archive, "rb"), str(archive), hint)


def _normal(name: str) -> str:
    """An archive name without leading `./` parts."""
    while name.startswith("./"):
        name = name[2:]
    return name


def _below_prefix(subject: str, name: str, *, directory: bool = False) -> str:
    """The path of `name` below HTML_PREFIX, or ValueError (`subject` says what is being checked)."""
    if not (name + "/" if directory else name).startswith(HTML_PREFIX):
        raise ValueError(f"{subject} is outside {HTML_PREFIX}")
    relative = name[len(HTML_PREFIX) :]
    # ":" too: on Windows a name that starts with a drive letter and a colon is an absolute path, which a hard-link copy
    # would write outside the staging folder. The manual has no such names.
    if any(ch in relative for ch in "\\\0:") or any(part in ("", ".", "..") for part in relative.split("/")):
        raise ValueError(f"{subject} has an unsafe path")
    return relative


def _plan(members: list[tarfile.TarInfo]) -> tuple[list[tuple[tarfile.TarInfo, str, str | None]], list[str]]:
    """Check every member before anything is extracted.

    Returns, in archive order, the files to write as (member, path relative to HTML_PREFIX, hard-link target or None),
    and the directories to create. A regular file is extracted; a hard link is written as a copy of its target. The
    target must be an earlier regular file below the prefix (as in tar), and the manual's archive has 31 such links.
    A symbolic link, device or FIFO anywhere, a hard link to anything else, and any other member outside the prefix
    raise ValueError.
    """
    entries: list[tuple[tarfile.TarInfo, str, str | None]] = []
    dirs: list[str] = []
    kinds: dict[str, str] = {}  # relative path -> "file", "link" or "dir", as planned so far
    for member in members:
        name = _normal(member.name)
        subject = f"archive member {member.name!r}"
        if member.isdir():
            name = name.rstrip("/")
            if name in _PARENT_DIRS:  # the prefix itself and the folders above it
                continue
            relative = _below_prefix(subject, name, directory=True)
            dirs.append(relative)
            kinds[relative] = "dir"
        elif member.isreg():
            relative = _below_prefix(subject, name)
            entries.append((member, relative, None))
            kinds[relative] = "file"
        elif member.islnk():
            relative = _below_prefix(subject, name)
            target = _below_prefix(f"the target {member.linkname!r} of hard link {member.name!r}", _normal(member.linkname))
            if target == relative:
                raise ValueError(f"hard link {member.name!r} points to itself")
            if target not in kinds:
                raise ValueError(f"hard link {member.name!r}: its target {member.linkname!r} is missing (not an earlier member)")
            if kinds[target] != "file":
                raise ValueError(f"hard link {member.name!r}: its target {member.linkname!r} is not a regular file")
            entries.append((member, relative, target))
            kinds[relative] = "link"
        else:  # a symbolic link, device, FIFO ...
            raise ValueError(f"{subject}: symbolic links, devices and pipes are not allowed")
    return entries, dirs


def _extract_html(archive: Path, staging: Path) -> None:
    """Extract the files below HTML_PREFIX into `staging`, without the prefix; a hard link becomes a copy."""
    try:
        with tarfile.open(archive, "r:bz2") as tar:
            entries, dirs = _plan(tar.getmembers())
            for relative in dirs:
                (staging / relative).mkdir(parents=True, exist_ok=True)
            for member, relative, target in entries:  # in archive order: the target of a link has been written already
                if target is None:
                    tar.extract(member.replace(name=relative, deep=False), staging, filter="data")
                else:
                    (staging / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(staging / target, staging / relative)
    except tarfile.TarError as error:  # a bad archive, or a member that the "data" filter refuses
        raise ValueError(f"the manual archive cannot be extracted: {error}") from error


def _replace(source: Path, destination: Path) -> None:
    """Rename `source` to `destination` (replacing a file); copy and delete when they are on different file systems."""
    try:
        os.replace(source, destination)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        shutil.move(str(source), str(destination))


def _move_tree(staging: Path, target: Path) -> None:
    """Put the staged tree at `target`; where `target` exists already, replace same-named files and keep the rest."""
    if not target.exists():
        _replace(staging, target)
        return
    for source in sorted(staging.rglob("*")):
        destination = target / source.relative_to(staging)
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            _replace(source, destination)


def fetch(kind: str, dest: Path = DEFAULT_DEST, *, opener=urllib.request.urlopen, root: Path = ROOT, archive: Path | None = None) -> Path:
    """Download the manual of `kind` ("html" or "pdf") into `dest`, check size and SHA-256, and return where it is.

    html: the files below HTML_PREFIX go to `dest/html` without the prefix; returns that folder.
    pdf: `dest/ccx_2.21.pdf`; returns that file.
    With `archive`, nothing is downloaded: that local file takes the place of the download, and goes through the same
    size and SHA-256 check and the same extraction (`opener` is not used).
    Raises ValueError for a destination inside the repository, a size or checksum mismatch, or an unsafe archive, and
    OSError for a file that cannot be read; in each case nothing is kept.
    """
    if kind not in SOURCES:
        raise ValueError(f"the manual comes as {' or '.join(SOURCES)}, not {kind!r}")
    dest = Path(dest)
    target = dest / (HTML_DIR if kind == "html" else PDF_NAME)
    _check_destination(dest, target, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    download = _download(kind, dest.parent, opener) if archive is None else _local_copy(kind, dest.parent, Path(archive))
    staging = None
    try:
        if kind == "pdf":
            dest.mkdir(parents=True, exist_ok=True)
            _replace(download, target)
        else:
            staging = Path(tempfile.mkdtemp(prefix=".ccx-manual-", suffix=".dir", dir=dest.parent))
            _extract_html(download, staging)
            dest.mkdir(parents=True, exist_ok=True)
            _move_tree(staging, target)
    finally:
        download.unlink(missing_ok=True)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.manual", description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", nargs="?", default="html", choices=sorted(SOURCES), help="html (the default) or pdf")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"where to put it (default: {DEFAULT_DEST})")
    parser.add_argument(
        "--archive",
        type=Path,
        metavar="FILE",
        help="use this copy that the instructor downloaded beforehand, and do not download. It is checked against the same "
        "pinned size and SHA-256 as a download and refused if it differs, so it must be the unmodified file",
    )
    args = parser.parse_args(argv)
    local = {} if args.archive is None else {"archive": args.archive.expanduser()}
    print(f"Downloading {SOURCES[args.kind][0]}" if not local else f"Using your copy {local['archive']} (no download)")
    print(NOTE)
    try:
        result = fetch(args.kind, args.dest.expanduser(), **local)
    except (ValueError, OSError) as error:  # OSError includes URLError
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Saved: {result}")
    print(f"Folder to give MCP-Anything: {result if result.is_dir() else result.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
