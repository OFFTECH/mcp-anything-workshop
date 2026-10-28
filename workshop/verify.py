"""Run every exercise deck through the real CalculiX and Gmsh and compare the results with the references.

    python3 -m workshop.verify [--keep DIR] [--only 01|02|04]      (or scripts/verify_decks.sh)

The instructor's check, inside the workshop dev container only: this repository's tests never start a solver. It prints one
table row per check, then `VERIFY: PASS` or `VERIFY: FAIL`, and exits 0 only when every check passed.

    01  the cantilever (tip displacement and support reaction against exercise 01's reference.json), the broken deck
        (ccx must reject it) and `ccx -v` (it prints the version and exits 201, which MCP-Anything reads with its
        `version_exit_codes`)
    02  the Gmsh beam under its own weight, for L = 1000 and L = 500 (`beam.selfweight_reference`)
    04  the cable section: Gmsh, CPS6 renamed to CPE6, the pressure load, ccx, against `layers.cable_reference`

Every case runs in its own folder of the work folder, with a timeout of 300 s per program. The tolerances are the
references' own; nothing is loosened here. The `.dat` layouts that `workshop/ccxdat.py` reads come from the ccx 2.21 source
and have never been checked against a run: a first failure may be a layout surprise rather than a wrong result (the
table's note says which program or file the check stopped at).
"""

import argparse
import math
import re
import shutil
import statistics
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from workshop import beam, compare, gmshinp, layers
from workshop.ccxdat import node_vectors, total_force
from workshop.check_tools import CCX_VERSION
from workshop.config import ROOT
from workshop.proc import Completed, Runner, run_process

TIMEOUT_S = 300.0
EXERCISES = ROOT / "exercises"
CCX_VERSION_EXIT_CODES = (0, 201)  # what `ccx -v` may exit with: 201 is stop.f's `call exit(201)`
DEFAULT_BEAM_LENGTH = 1000.0  # mm: the L that beam.geo defines when -setnumber is not given
BEAM_ELEMENT_TYPES = ["C3D10"]
NOT_FOUND = "CalculiX or Gmsh not found: run this inside the workshop dev container (README.md)"

CANTILEVER, BROKEN, VERSION, CABLE = "01 cantilever", "01 broken deck", "version", "04 cable"
_VERSION_LINE = re.compile(rf"This is Version[ \t]+{re.escape(CCX_VERSION)}(?![0-9])")


@dataclass(frozen=True)
class Check:
    """One row of the table. `expected`, `actual` and `limit` are None for a check that is not a number against a reference."""

    case: str
    quantity: str
    expected: float | None
    actual: float | None
    limit: float | None
    ok: bool
    note: str = ""


class _Stop(Exception):
    """Ends a case early with one failing check: the program or file it stopped at, and why."""

    def __init__(self, quantity: str, note: str):
        super().__init__(note)
        self.quantity = quantity
        self.note = note


def _failed(case: str, quantity: str, note: str) -> Check:
    return Check(case, quantity, None, None, None, False, note)


def _guarded(case: str, body: Callable[[], list[Check]]) -> list[Check]:
    """The checks of `body`; a program or file that cannot be used becomes a failing check instead of a traceback."""
    try:
        return body()
    except _Stop as stop:
        return [_failed(case, stop.quantity, stop.note)]
    except (OSError, ValueError) as error:
        return [_failed(case, "case", f"{type(error).__name__}: {error}")]


def _folder(work: Path, name: str, *outputs: str) -> Path:
    """The case's own folder under `work`, made if needed. The files the case writes are deleted first, so that a result
    left by an earlier run (with `--keep`) can never pass for this run's."""
    folder = work / name
    folder.mkdir(parents=True, exist_ok=True)
    for output in outputs:
        (folder / output).unlink(missing_ok=True)
    return folder


def _copy(source: Path, folder: Path) -> None:
    shutil.copyfile(source, folder / source.name)


def _execute(run: Runner, argv: list[str], folder: Path) -> Completed:
    try:
        return run(argv, folder, TIMEOUT_S)
    except OSError as error:  # the program is not installed or cannot be run
        raise _Stop(argv[0], f"cannot run {argv[0]}: {error}") from None


def _first_error(output: str) -> str:
    for line in output.splitlines():
        if "*ERROR" in line:
            return line.strip()[:100]
    return ""


def solver_problem(result: Completed, dat: Path) -> str | None:
    """Why a ccx run cannot be trusted, or None. A timeout, a non-zero exit, `*ERROR` in the output (ccx can print it and
    still exit 0) and a missing or empty `.dat` are problems."""
    if result.returncode is None:
        return f"timed out after {TIMEOUT_S:g} s"
    error = _first_error(result.output)
    if result.returncode != 0:
        return f"exit code {result.returncode}" + (f": {error}" if error else "")
    if error:
        return f"{error} (the exit code is 0)"
    if not dat.is_file():
        return f"{dat.name} was not written"
    if dat.stat().st_size == 0:
        return f"{dat.name} is empty"
    return None


def _tool_problem(program: str, result: Completed, output: Path) -> str | None:
    """Why a Gmsh run left no usable file, or None."""
    if result.returncode is None:
        return f"{program} timed out after {TIMEOUT_S:g} s"
    if result.returncode != 0:
        return f"{program} exited with code {result.returncode}"
    if not output.is_file():
        return f"{program} wrote no {output.name}"
    if output.stat().st_size == 0:
        return f"{output.name} is empty"
    return None


def _solve(run: Runner, folder: Path, job: str) -> str:
    """Run `ccx -i <job>` in the folder and return the text of <job>.dat; raises _Stop if the run cannot be trusted."""
    dat = folder / f"{job}.dat"
    result = _execute(run, ["ccx", "-i", job], folder)
    if problem := solver_problem(result, dat):
        raise _Stop("ccx run", problem)
    return dat.read_text(encoding="utf-8", errors="replace")


def _mesh(run: Runner, folder: Path, argv: list[str], output: str) -> str:
    """Run Gmsh in the folder and return the text of the mesh it wrote; raises _Stop if it failed."""
    path = folder / output
    result = _execute(run, argv, folder)
    if problem := _tool_problem("gmsh", result, path):
        raise _Stop("gmsh run", problem)
    return path.read_bytes().decode("utf-8", errors="replace")  # bytes: the line ends stay as Gmsh wrote them


def _compared(case: str, readers: dict[str, Callable[[], float]], reference: dict) -> list[Check]:
    """Read each value; compare them with the reference. A value that cannot be read is a failing check with the reason."""
    values: dict[str, float] = {}
    problems: dict[str, str] = {}
    for name, read in readers.items():
        try:
            values[name] = read()
        except ValueError as error:
            problems[name] = str(error)
    checks = []
    for row in compare.compare(values, reference):
        if row.name in problems:
            note = problems[row.name]
        elif row.actual is None:
            note = "missing"
        else:
            note = "" if row.ok else f"differs by {abs(row.actual - row.expected):.3g}"
        checks.append(Check(case, row.name, row.expected, row.actual, row.limit, row.ok, note))
    return checks


def _only(vectors: dict[int, tuple[float, float, float]], set_name: str) -> tuple[float, float, float]:
    if len(vectors) != 1:
        raise ValueError(f"set {set_name} has {len(vectors)} rows, expected 1 (nodes {', '.join(map(str, sorted(vectors)))})")
    return next(iter(vectors.values()))


def case_cantilever(work: Path, run: Runner) -> list[Check]:
    """Exercise 01: the cantilever deck against `01-cantilever/reference.json`."""

    def body() -> list[Check]:
        source = EXERCISES / "01-cantilever"
        folder = _folder(work, "01-cantilever", "cantilever.dat")
        _copy(source / "cantilever.inp", folder)
        dat = _solve(run, folder, "cantilever")
        readers = {
            "tip_displacement_y": lambda: _only(node_vectors(dat, "TIPC"), "TIPC")[1],
            "support_reaction_y": lambda: total_force(dat, "FIX")[1],
        }
        return _compared(CANTILEVER, readers, compare.load_reference(source / "reference.json"))

    return _guarded(CANTILEVER, body)


def case_broken_deck(work: Path, run: Runner) -> list[Check]:
    """Exercise 01's broken deck (Young's modulus `abc`): ccx must stop with `*ERROR reading *ELASTIC`."""

    def body() -> list[Check]:
        folder = _folder(work, "01-broken-deck", "bad_modulus.dat")
        _copy(EXERCISES / "01-cantilever" / "broken" / "bad_modulus.inp", folder)
        result = _execute(run, ["ccx", "-i", "bad_modulus"], folder)
        code = result.returncode
        quantity = "rejected: *ERROR reading *ELASTIC"
        if code is None:
            return [_failed(BROKEN, quantity, f"timed out after {TIMEOUT_S:g} s")]
        if code == 0:
            return [_failed(BROKEN, quantity, "ccx accepted the deck: exit code 0 (expected 201)")]
        if "*ERROR reading *ELASTIC" not in result.output:
            return [_failed(BROKEN, quantity, f"exit code {code}, but no '*ERROR reading *ELASTIC' in the output")]
        return [Check(BROKEN, quantity, None, None, None, True, f"exit code {code} (expected 201)")]

    return _guarded(BROKEN, body)


def case_version(work: Path, run: Runner) -> list[Check]:
    """`ccx -v` prints `This is Version 2.21` and exits 201 (stop.f): MCP-Anything needs `version_exit_codes=(0, 201)`."""

    def body() -> list[Check]:
        folder = _folder(work, "version")
        result = _execute(run, ["ccx", "-v"], folder)
        code = result.returncode
        if code is None:
            return [_failed(VERSION, "ccx -v", f"timed out after {TIMEOUT_S:g} s")]
        problems = []
        if code not in CCX_VERSION_EXIT_CODES:
            problems.append("expected exit code 0 or 201")
        if not _VERSION_LINE.search(result.output):
            problems.append(f"no 'This is Version {CCX_VERSION}' line in the output")
        if problems:
            return [_failed(VERSION, "ccx -v", f"exit code {code}: " + "; ".join(problems))]
        note = f"exit code {code}: MCP-Anything reads this with its version_exit_codes={CCX_VERSION_EXIT_CODES}"
        return [Check(VERSION, "ccx -v", None, None, None, True, note)]

    return _guarded(VERSION, body)


def case_gmsh_beam(work: Path, run: Runner, length: float | None = None) -> list[Check]:
    """Exercise 02: Gmsh meshes the beam (`-setnumber L <length>` unless `length` is None, which keeps beam.geo's 1000 mm),
    ccx solves the self-weight deck, and the results are compared with `beam.selfweight_reference(length)`."""
    if length is not None and not (math.isfinite(length) and length > 0):
        raise ValueError(f"the length must be a number above 0, got {length!r}")
    effective = DEFAULT_BEAM_LENGTH if length is None else length
    case = f"02 beam L={effective:g}"

    def body() -> list[Check]:
        source = EXERCISES / "02-gmsh-beam"
        folder = _folder(work, f"02-beam-L{effective:g}", "beam_mesh.inp", "beam_selfweight.dat")
        _copy(source / "beam.geo", folder)
        _copy(source / "beam_selfweight.inp", folder)
        argv = ["gmsh", "beam.geo", "-3", "-format", "inp", "-o", "beam_mesh.inp"]
        if length is not None:
            argv += ["-setnumber", "L", f"{length:g}"]
        types = gmshinp.element_types(_mesh(run, folder, argv, "beam_mesh.inp"))
        if types != BEAM_ELEMENT_TYPES:
            return [_failed(case, "mesh", f"element types {types}, expected {BEAM_ELEMENT_TYPES}: ccx was not run")]
        dat = _solve(run, folder, "beam_selfweight")
        readers = {
            "tip_displacement_y": lambda: statistics.fmean(v[1] for v in node_vectors(dat, "TIP").values()),
            "support_reaction_y": lambda: total_force(dat, "FIXED")[1],
        }
        return _compared(case, readers, beam.selfweight_reference(effective))

    return _guarded(case, body)


def _gmsh_node_x(dat: str, set_name: str, gmsh_sets: dict[str, set[int]]) -> float:
    """The x-component of the one printed row of `set_name` whose node is a node of Gmsh's set of that name.

    ccx expands the plane elements into 3-D ones, so the set may be printed with more nodes than Gmsh wrote.
    """
    members = gmsh_sets.get(set_name)
    if members is None:
        raise ValueError(f"the Gmsh mesh has no node set {set_name} (it has: {', '.join(sorted(gmsh_sets)) or 'none'})")
    rows = node_vectors(dat, set_name)
    hits = [node for node in rows if node in members]
    if len(hits) != 1:
        shown = sorted(rows)
        listed = ", ".join(f"{node}: {rows[node][0]:.4g}" for node in shown[:12]) + (", ..." if len(shown) > 12 else "")
        raise ValueError(
            f"{len(hits)} rows of {set_name} are nodes of the Gmsh set (nodes {', '.join(map(str, sorted(members)))}), "
            f"expected 1; rows printed (node: x): {listed}"
        )
    return rows[hits[0]][0]


def _with_rows_printed(check: Check, dat: str, set_name: str) -> Check:
    """The check with "(N rows printed)" added to its note when its value was read (a failed read already lists the rows)."""
    if check.actual is None:
        return check
    count = len(node_vectors(dat, set_name))  # it was read from this block a moment ago
    printed = f"({count} row{'' if count == 1 else 's'} printed)"
    return replace(check, note=f"{check.note} {printed}".strip())


def case_cable(work: Path, run: Runner) -> list[Check]:
    """Exercise 04: Gmsh meshes the quarter section, CPS6 becomes CPE6 (plane strain), the outer faces get the pressure,
    ccx solves, and the radial displacements are compared with `layers.cable_reference()`. A mesh that is not plane
    strain, or has a clockwise triangle, stops the case before ccx."""

    def body() -> list[Check]:
        source = EXERCISES / "04-cable-section"
        outputs = ("cable_mesh_gmsh.inp", "cable_mesh.inp", "cable_pressure_load.inc", "cable_pressure.dat")
        folder = _folder(work, "04-cable", *outputs)
        _copy(source / "cable_quarter.geo", folder)
        _copy(source / "cable_pressure.inp", folder)
        raw = _mesh(run, folder, ["gmsh", "cable_quarter.geo", "-2", "-format", "inp", "-o", "cable_mesh_gmsh.inp"], "cable_mesh_gmsh.inp")
        try:
            mesh = gmshinp.to_plane_strain(raw)
            clockwise = gmshinp.clockwise_elements(mesh)
        except ValueError as error:
            raise _Stop("mesh", f"{error}: ccx was not run") from None
        if clockwise:
            shown = ", ".join(map(str, clockwise[:10])) + (", ..." if len(clockwise) > 10 else "")
            raise _Stop("mesh", f"{len(clockwise)} triangle(s) are not counter-clockwise (elements {shown}): ccx was not run")
        (folder / "cable_mesh.inp").write_bytes(mesh.encode("utf-8"))
        try:
            load = gmshinp.dload_text(gmshinp.pressure_faces(mesh, "OUTER"), layers.CABLE_PRESSURE)
        except ValueError as error:
            raise _Stop("load", f"{error}: ccx was not run") from None
        (folder / "cable_pressure_load.inc").write_bytes(load.encode("utf-8"))
        dat = _solve(run, folder, "cable_pressure")
        gmsh_sets = gmshinp.node_sets(mesh)
        probes = {"u_r_core_edge": "P_CORE", "u_r_outer": "P_OUTER"}  # value name -> node set printed by ccx
        readers = {name: lambda set_name=set_name: _gmsh_node_x(dat, set_name, gmsh_sets) for name, set_name in probes.items()}
        checks = _compared(CABLE, readers, layers.cable_reference())
        # what ccx really prints for these sets (it expands the plane elements into 3-D ones): checklist item C6
        return [_with_rows_printed(check, dat, probes[check.quantity]) for check in checks]

    return _guarded(CABLE, body)


CASES: dict[str, list[tuple[str, Callable[[Path, Runner], list[Check]]]]] = {
    "01": [(CANTILEVER, case_cantilever), (BROKEN, case_broken_deck), (VERSION, case_version)],
    "02": [
        (f"02 beam L={DEFAULT_BEAM_LENGTH:g}", lambda work, run: case_gmsh_beam(work, run)),
        ("02 beam L=500", lambda work, run: case_gmsh_beam(work, run, 500.0)),
    ],
    "04": [(CABLE, case_cable)],
}


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.6g}"


def format_table(checks: list[Check]) -> str:
    """One row per check: case, quantity, expected, FE, limit, PASS or FAIL, note."""
    header = ("Case", "Quantity", "Expected", "FE", "Limit", "Result", "Note")
    rows = [
        (c.case, c.quantity, _number(c.expected), _number(c.actual), _number(c.limit), "PASS" if c.ok else "FAIL", c.note)
        for c in checks
    ]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(6)]
    lines = ["  ".join([*(cell.ljust(widths[i]) for i, cell in enumerate(row[:6])), row[6]]).rstrip() for row in [header, *rows]]
    return "\n".join(lines)


def main(argv: list[str] | None = None, run: Runner = run_process) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.verify", description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", metavar="DIR", help="run in this folder and keep it (the default is a temporary folder, removed when everything passed)")
    parser.add_argument("--only", choices=sorted(CASES), help="01: cantilever, broken deck and ccx -v; 02: the Gmsh beam; 04: the cable")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:  # argparse has printed its message
        return stop.code if isinstance(stop.code, int) else 2
    if run is run_process and (shutil.which("ccx") is None or shutil.which("gmsh") is None):
        print(NOT_FOUND)
        return 1

    keep = args.keep is not None
    try:
        work = Path(args.keep) if keep else Path(tempfile.mkdtemp(prefix="workshop-verify-"))
        work.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"error: cannot use the work folder: {error}", file=sys.stderr)
        return 2
    checks: list[Check] = []
    for group in [args.only] if args.only else sorted(CASES):
        for name, case in CASES[group]:
            print(f"running {name} ...", flush=True)
            checks += case(work, run)
    print()
    print(format_table(checks))
    print()
    passed = all(check.ok for check in checks)
    if keep or not passed:
        print(f"Run folders: {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)
    print("VERIFY: PASS" if passed else "VERIFY: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
