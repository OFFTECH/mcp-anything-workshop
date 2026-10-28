"""Check that every tool of the workshop is present, with the versions the dev container pins. Standard library only.

    python3 -m workshop.check_tools [--ready]

OK means the expected version; WARN another version (or the plugin not installed); FAIL a program that is missing or
does not answer. Exit 1 if any row is FAIL. `--ready` is the instructor's check before participants arrive: it also
FAILs while workshop.conf holds the placeholder and while the plugin is not installed.
"""

import argparse
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from workshop.config import CONF_PATH, ROOT, is_placeholder, mcp_anything_repo
from workshop.plugin import installed
from workshop.proc import Completed, Runner, run_process

EXPECTED = {"calculix-ccx": "2.21-1", "gmsh": "4.12.1", "python3": "3.12.", "uv": "0.13.5", "node": "v24.", "claude": "2.1.308"}

OK, WARN, FAIL = "OK", "WARN", "FAIL"
PROBE_TIMEOUT_S = 30.0
PLUGIN_ROW = "mcp-anything plugin"
CONF_ROW = "workshop.conf"
CCX_VERSION = EXPECTED["calculix-ccx"].rsplit("-", 1)[0]  # the Debian revision is not part of what `ccx -v` prints
CCX_EXIT_NOTE = "exits 201 after printing its version; MCP-Anything needs version_exit_codes=(0, 201) (exercise 01)"
_CCX_VERSION_LINE = re.compile(r"This is Version[ \t]+(\S+)")


@dataclass(frozen=True)
class Row:
    tool: str
    status: str  # OK, WARN or FAIL
    found: str  # what the probe answered
    note: str


def _first_line(text: str, limit: int = 60) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


@dataclass(frozen=True)
class _Unavailable:
    """A program that could not be started: the note of its FAIL row."""

    reason: str


def _probe(run: Runner, argv: Sequence[str]) -> Completed | _Unavailable:
    """The answer of `argv`, or why the program could not be started."""
    try:
        return run(argv, ROOT, PROBE_TIMEOUT_S)
    except FileNotFoundError:
        return _Unavailable("not installed")
    except PermissionError:
        return _Unavailable(f"permission denied: {argv[0]} cannot be run (not executable?)")
    except OSError as error:  # for example "Exec format error"
        return _Unavailable(f"{argv[0]} cannot be run: {error.strerror or error}")


def _not_installed(tool: str, done: Completed | _Unavailable) -> Row | None:
    """The FAIL row for a program that cannot be run, a timeout or a non-zero exit; None when it answered with exit 0."""
    if isinstance(done, _Unavailable):
        return Row(tool, FAIL, "-", done.reason)
    if done.returncode is None:
        return Row(tool, FAIL, "timed out", f"no answer within {PROBE_TIMEOUT_S:g} s")
    if done.returncode != 0:
        return Row(tool, FAIL, f"exit {done.returncode}", "not installed")
    return None


def _versioned(run: Runner, tool: str, argv: Sequence[str], expected: str, matches: Callable[[str], bool]) -> Row:
    done = _probe(run, argv)
    failed = _not_installed(tool, done)
    if failed is not None:
        return failed
    assert isinstance(done, Completed)
    found = _first_line(done.output)
    if matches(done.output):
        return Row(tool, OK, found, "")
    return Row(tool, WARN, found, f"the workshop is built for {expected}")


def _unversioned(run: Runner, tool: str, argv: Sequence[str]) -> Row:
    done = _probe(run, argv)
    failed = _not_installed(tool, done)
    if failed is not None:
        return failed
    assert isinstance(done, Completed)
    return Row(tool, OK, _first_line(done.output), "")


def _ccx_row(run: Runner) -> Row:
    """`ccx -v` prints `This is Version 2.21` and then exits 201 (stop.f), so the exit code alone says nothing."""
    done = _probe(run, ["ccx", "-v"])
    if isinstance(done, _Unavailable):
        return Row("ccx", FAIL, "-", done.reason)
    match = _CCX_VERSION_LINE.search(done.output)
    if done.returncode is None or match is None:
        found = "timed out" if done.returncode is None else (_first_line(done.output) or f"exit {done.returncode}")
        return Row("ccx", FAIL, found, "ccx -v did not print a 'This is Version' line")
    version = match.group(1)
    found = f"{version} (exit {done.returncode})"
    if version != CCX_VERSION and not version.startswith(CCX_VERSION + "."):
        return Row("ccx", WARN, found, f"the workshop is built for {CCX_VERSION}")
    if done.returncode == 201:
        return Row("ccx", OK, found, CCX_EXIT_NOTE)
    if done.returncode == 0:
        return Row("ccx", OK, found, "")
    return Row("ccx", WARN, found, "expected exit 201 (or 0) after the version line")


def _plugin_row(run: Runner) -> Row:
    try:
        ok = installed(run)
    except OSError:  # no claude (the claude row is the FAIL), or one that cannot be run
        ok = False
    if ok:
        return Row(PLUGIN_ROW, OK, "installed", "")
    return Row(PLUGIN_ROW, WARN, "not installed", "run: python3 -m workshop.plugin (or the two /plugin lines in the README)")


def check(run: Runner = run_process) -> list[Row]:
    """Probe every tool, in the order of the table."""
    return [
        _versioned(
            run,
            "calculix-ccx",
            ["dpkg-query", "-W", "-f=${Version}", "calculix-ccx"],
            EXPECTED["calculix-ccx"],
            lambda out: out.strip() == EXPECTED["calculix-ccx"],
        ),
        _ccx_row(run),
        _versioned(run, "gmsh", ["gmsh", "--version"], EXPECTED["gmsh"], lambda out: _first_line(out, 200).startswith(EXPECTED["gmsh"])),
        _versioned(run, "python3", ["python3", "--version"], EXPECTED["python3"], lambda out: EXPECTED["python3"] in out),
        _versioned(run, "uv", ["uv", "--version"], EXPECTED["uv"], lambda out: EXPECTED["uv"] in out),
        _versioned(run, "node", ["node", "--version"], EXPECTED["node"], lambda out: out.strip().startswith(EXPECTED["node"])),
        _unversioned(run, "npm", ["npm", "--version"]),
        _versioned(run, "claude", ["claude", "--version"], EXPECTED["claude"], lambda out: EXPECTED["claude"] in out),
        _unversioned(run, "git", ["git", "--version"]),
        _plugin_row(run),
    ]


def _conf_row(conf: Path) -> Row:
    try:
        repo = mcp_anything_repo(conf)
    except (OSError, ValueError) as error:
        return Row(CONF_ROW, FAIL, "unreadable", str(error))
    if is_placeholder(repo):
        return Row(CONF_ROW, FAIL, "not set", "set MCP_ANYTHING_REPO in workshop.conf (INSTRUCTOR.md, step 3)")
    return Row(CONF_ROW, OK, "set", "")


def _ready(rows: list[Row], conf: Path) -> list[Row]:
    """The rows for `--ready`: the plugin must be installed (a WARN becomes a FAIL) and workshop.conf must be set."""
    strict = [replace(row, status=FAIL) if row.tool == PLUGIN_ROW and row.status != OK else row for row in rows]
    return [*strict, _conf_row(conf)]


def format_table(rows: Sequence[Row]) -> str:
    header = Row("Tool", "Status", "Found", "Note")
    table = [header, *rows]
    widths = [max(len(getattr(r, field)) for r in table) for field in ("tool", "status", "found")]
    lines = []
    for r in table:
        cells = [r.tool.ljust(widths[0]), r.status.ljust(widths[1]), r.found.ljust(widths[2]), r.note]
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def main(argv: list[str] | None = None, run: Runner = run_process, conf: Path = CONF_PATH) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.check_tools", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--ready", action="store_true", help="also FAIL while workshop.conf holds the placeholder or the plugin is not installed"
    )
    args = parser.parse_args(argv)
    rows = check(run)
    if args.ready:
        rows = _ready(rows, conf)
    print(format_table(rows))
    print()
    print("WORKSHOP_ROOT: " + (os.environ.get("WORKSHOP_ROOT") or "(not set: open a new terminal)"))
    failed = [row.tool for row in rows if row.status == FAIL]
    if failed:
        print("FAIL: " + ", ".join(failed))
        return 1
    print("All tools are present." if all(row.status == OK for row in rows) else "No tool is missing (see the WARN rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
