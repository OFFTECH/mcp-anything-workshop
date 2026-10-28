"""Shared test helpers.

The content and line-ending checks read what git stores (the index blob), never the working tree of a tracked file:
on Windows `core.autocrlf=true` may leave CRLF in the working tree for a file that git stores with LF.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# `uv run pytest` does not put the working directory on sys.path (`python -m pytest` does): make `workshop` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workshop import config  # noqa: E402

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache"}


@pytest.fixture
def root() -> Path:
    return config.ROOT


def git_output(root: Path, *args: str, stdin: bytes | None = None) -> bytes | None:
    """Stdout of `git -C root <args>`, or None when git is missing, times out or exits non-zero."""
    try:
        done = subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def in_git(root: Path) -> bool:
    """True when `root` is its own git top level (not a folder inside another repository, not a `git archive` export)."""
    if not (root / ".git").exists():
        return False
    top = git_output(root, "rev-parse", "--show-toplevel")
    return top is not None and Path(top.decode("utf-8").strip()).resolve() == root.resolve()


def _walked_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        yield from (Path(dirpath) / name for name in filenames)


def _in_skipped_dir(path: Path, root: Path) -> bool:
    """Below a skipped folder (.git, .venv, caches ...) or inside a virtualenv (a folder holding pyvenv.cfg)."""
    parents = path.relative_to(root).parents
    return any(p.name in SKIP_DIRS or (root / p / "pyvenv.cfg").is_file() for p in parents if p.parts)


def repo_files(root: Path) -> list[Path]:
    """The repository's files: tracked ones plus untracked ones that .gitignore does not exclude.

    Without git (or when `root` is not its own repository) a folder walk that skips .git, .venv and the caches.
    """
    files = None
    if in_git(root):
        listed = git_output(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
        if listed is not None:
            files = [root / rel for rel in sorted(set(listed.decode("utf-8").split("\0"))) if rel]
    if files is None:
        files = sorted(_walked_files(root))
    return [p for p in files if not _in_skipped_dir(p, root)]


def stored_bytes(root: Path, rel: str) -> bytes:
    """What git stores for the tracked file `rel` (`git show :<rel>`, the index blob).

    For an untracked file, or without git, the working-tree bytes.
    """
    if in_git(root):
        blob = git_output(root, "show", f":{rel}")
        if blob is not None:
            return blob
    return (root / rel).read_bytes()


@pytest.fixture
def gmsh_2d() -> str:
    """A hand-written mesh in the layout of the .inp export of Gmsh 4.12.1 (`GModelIO_INP.cpp`, `MElement::writeINP`).

    Two counter-clockwise 6-node triangles (`CPS6`) cover the unit square (0,0)-(1,0)-(1,1)-(0,1). Nodes 1-4 are the
    corners, nodes 5-9 the mid-nodes. NSET lines end with ", " as Gmsh writes them. The sets:

        OUTER  the right edge x=1 (nodes 2, 6, 3)      SYMX  the left edge x=0 (nodes 1, 9, 4)
        SYMY   the bottom edge y=0 (nodes 1, 5, 2)     CABLE an ELSET of both elements

    Built from a list of lines so that the trailing blanks of the set lines cannot be lost to an editor.
    """
    return "\n".join(
        [
            "*Heading",
            " square.inp",
            "*NODE",
            "1, 0, 0, 0",
            "2, 1, 0, 0",
            "3, 1, 1, 0",
            "4, 0, 1, 0",
            "5, 0.5, 0, 0",
            "6, 1, 0.5, 0",
            "7, 0.5, 0.5, 0",
            "8, 0.5, 1, 0",
            "9, 0, 0.5, 0",
            "*ELEMENT, type=CPS6, ELSET=Surface1",
            "1, 1, 2, 3, 5, 6, 7",
            "2, 1, 3, 4, 7, 8, 9",
            "*ELSET,ELSET=CABLE",
            "1, 2, ",
            "*NSET,NSET=OUTER",
            "2, 6, 3, ",
            "*NSET,NSET=SYMX",
            "1, 9, 4, ",
            "*NSET,NSET=SYMY",
            "1, 5, 2, ",
            "",
        ]
    )
