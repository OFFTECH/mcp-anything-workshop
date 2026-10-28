"""Generate the committed files that are computed rather than written by hand.

`python3 -m workshop.generate` (or `... write`) writes them; `python3 -m workshop.generate check` exits 1 and lists the
files that differ from what the code computes. Standard library only. Files are UTF-8 with LF line endings.
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from . import beam, layers
from .config import ROOT


def _json_text(obj: object) -> str:
    return json.dumps(obj, indent=2) + "\n"


# repo-relative POSIX path -> function that returns the file's text
RENDERERS: dict[str, Callable[[], str]] = {
    "exercises/01-cantilever/reference.json": lambda: _json_text(beam.cantilever_reference()),
    "exercises/01-cantilever/cantilever.inp": lambda: beam.cantilever_deck(),
    "exercises/01-cantilever/broken/bad_modulus.inp": lambda: beam.broken_cantilever_deck(),
    # the finding code MCP-Anything reports for a field that is not a number
    "exercises/01-cantilever/broken/expected.json": lambda: _json_text({"bad_modulus.inp": ["NOT_NUMERIC"]}),
    "exercises/02-gmsh-beam/reference.json": lambda: _json_text(beam.selfweight_reference()),
    "exercises/04-cable-section/reference.json": lambda: _json_text(layers.cable_reference()),
}


def render_all() -> dict[str, str]:
    """The text of every generated file, by repo-relative POSIX path."""
    return {path: render() for path, render in RENDERERS.items()}


def write_all(root: Path = ROOT) -> list[str]:
    """Write every generated file under `root` (UTF-8, LF), creating folders. Returns the paths written."""
    written = []
    for path, text in render_all().items():
        target = Path(root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))  # bytes: no newline translation on Windows
        written.append(path)
    return written


def stale(root: Path = ROOT) -> list[str]:
    """The generated files under `root` that are missing or differ in a single byte from what the code computes."""
    result = []
    for path, text in render_all().items():
        target = Path(root) / path
        if not target.is_file() or target.read_bytes() != text.encode("utf-8"):
            result.append(path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.generate", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "command",
        nargs="?",
        default="write",
        choices=("write", "check"),
        help="write the generated files (the default), or check that they are current (exit 1 if not)",
    )
    command = parser.parse_args(argv).command
    if command == "check":
        problems = stale(ROOT)
        for path in problems:
            print(f"stale: {path}")
        if problems:
            print("run: python3 -m workshop.generate", file=sys.stderr)
        return 1 if problems else 0
    for path in write_all(ROOT):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
