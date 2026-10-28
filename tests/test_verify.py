"""The deck verification, with fake `ccx` and `gmsh`. Nothing real is run: the fakes write the files a run would write.

The `.dat` texts are in the layout of CalculiX 2.21 `printoutnode.f` (see tests/test_ccxdat.py); they have never been
compared with a real run. That is what `pytest -m solver` (tests/test_solver.py) does, inside the dev container.
"""

import inspect
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from _datfixtures import disp_block, total_block
from conftest import git_output, in_git, stored_bytes
from workshop import beam, config, layers, verify
from workshop.proc import Completed, run_process
from workshop.verify import (
    Check,
    case_broken_deck,
    case_cable,
    case_cantilever,
    case_gmsh_beam,
    case_version,
    solver_problem,
)

VERSION_OUTPUT = "\n  This is Version 2.21\n\n"
BEAM_MESH = "\n".join(
    [
        "*Heading",
        " beam_mesh.inp",
        "*NODE",
        "1, 0, 0, 0",
        "*ELEMENT, type=C3D10, ELSET=Volume1",
        "1, 1, 1, 1, 1, 1, 1, 1, 1, 1",
        "*NSET,NSET=TIP",
        "1, ",
        "",
    ]
)


def cantilever_dat(uy: float = -2.5, fy: float = 21.0) -> str:
    return disp_block("TIPC", [(1211, (1.0e-03, uy, 0.0))]) + total_block("FIX", (0.0, fy, 0.0))


def beam_dat(tip_y: tuple[float, ...], fy: float) -> str:
    rows = [(1200 + i, (0.0, y, 0.0)) for i, y in enumerate(tip_y, start=1)]
    return disp_block("TIP", rows) + total_block("FIXED", (0.0, fy, 0.0))


class Fake:
    """A `Runner`: each handler `(argv, cwd) -> Completed` answers one program; another program is not installed."""

    def __init__(self, ccx=None, gmsh=None):
        self.handlers = {"ccx": ccx, "gmsh": gmsh}
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, cwd, timeout_s):
        assert isinstance(cwd, Path) and cwd.is_dir()
        assert timeout_s == 300, "every run has a 300 s timeout"
        self.calls.append(tuple(argv))
        handler = self.handlers.get(argv[0])
        if handler is None:
            raise FileNotFoundError(argv[0])
        return handler(list(argv), cwd)

    def ran(self, *prefix: str) -> list[tuple[str, ...]]:
        return [call for call in self.calls if call[: len(prefix)] == prefix]


def ccx_writing(job: str, dat: str, output: str = "", code: int = 0):
    """A ccx that expects `ccx -i <job>` and writes <job>.dat."""

    def handler(argv, cwd):
        assert argv == ["ccx", "-i", job]
        (cwd / f"{job}.dat").write_text(dat, encoding="utf-8")
        return Completed(code, output)

    return handler


# ---- solver_problem ---------------------------------------------------------------------------------------------


def test_solver_problem_is_none_for_a_clean_run(tmp_path):
    dat = tmp_path / "job.dat"
    dat.write_text("x", encoding="utf-8")
    assert solver_problem(Completed(0, " Job finished\n"), dat) is None


def test_solver_problem_names_each_failure(tmp_path):
    dat = tmp_path / "job.dat"
    assert "timed out" in solver_problem(Completed(None, "\n[timed out after 300 s]"), dat)
    assert "201" in solver_problem(Completed(201, " *ERROR reading *ELASTIC"), dat)
    assert "*ERROR in calinput" in solver_problem(Completed(0, " *ERROR in calinput. Card image:"), dat)
    assert "job.dat" in solver_problem(Completed(0, ""), dat)  # no .dat
    dat.write_text("", encoding="utf-8")
    assert "empty" in solver_problem(Completed(0, ""), dat)


# ---- 01 cantilever ----------------------------------------------------------------------------------------------


def test_cantilever_passes_with_the_reference_values(tmp_path):
    run = Fake(ccx=ccx_writing("cantilever", cantilever_dat(-2.5, 21.0)))
    checks = case_cantilever(tmp_path, run)
    assert [c.quantity for c in checks] == ["tip_displacement_y", "support_reaction_y"]
    assert all(c.ok for c in checks), checks
    tip, reaction = checks
    assert (tip.expected, tip.actual) == (-2.5, -2.5)
    assert (reaction.expected, reaction.actual) == (21.0, 21.0)
    assert tip.limit == pytest.approx(0.05) and reaction.limit == pytest.approx(1e-4)  # from reference.json
    assert {c.case for c in checks} == {"01 cantilever"}
    assert run.calls == [("ccx", "-i", "cantilever")]
    copied = next(tmp_path.rglob("cantilever.inp"))
    assert copied.read_bytes() == (config.ROOT / "exercises/01-cantilever/cantilever.inp").read_bytes()


def test_cantilever_fails_outside_the_tolerance(tmp_path):
    checks = case_cantilever(tmp_path, Fake(ccx=ccx_writing("cantilever", cantilever_dat(-2.7, 21.0))))
    tip, reaction = checks
    assert not tip.ok and tip.actual == -2.7
    assert reaction.ok


def test_cantilever_reaction_tolerance_stays_tight(tmp_path):
    checks = case_cantilever(tmp_path, Fake(ccx=ccx_writing("cantilever", cantilever_dat(-2.5, 21.01))))
    assert [c.ok for c in checks] == [True, False]


def test_exit_zero_with_error_text_fails(tmp_path):
    run = Fake(ccx=ccx_writing("cantilever", cantilever_dat(), output=" *ERROR in calinput. Card image:"))
    checks = case_cantilever(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert "*ERROR" in " ".join(c.note for c in checks)


def test_missing_dat_fails(tmp_path):
    checks = case_cantilever(tmp_path, Fake(ccx=lambda argv, cwd: Completed(0, " Job finished\n")))
    assert checks and not any(c.ok for c in checks)
    assert "cantilever.dat" in " ".join(c.note for c in checks)


def test_a_timeout_or_a_nonzero_exit_fails(tmp_path):
    for completed in (Completed(None, "\n[timed out after 300 s]"), Completed(1, "")):
        checks = case_cantilever(tmp_path, Fake(ccx=lambda argv, cwd, c=completed: c))
        assert checks and not any(c.ok for c in checks)


def test_a_value_that_cannot_be_read_fails_with_the_reason(tmp_path):
    # the total force of FIX is not in the .dat: that row fails with the reason, the other one is still compared
    checks = case_cantilever(tmp_path, Fake(ccx=ccx_writing("cantilever", disp_block("TIPC", [(1211, (0.0, -2.5, 0.0))]))))
    assert [c.quantity for c in checks] == ["tip_displacement_y", "support_reaction_y"]
    assert [c.ok for c in checks] == [True, False]
    assert "FIX" in checks[1].note and checks[1].actual is None


def test_a_dat_in_another_layout_fails_every_value(tmp_path):
    checks = case_cantilever(tmp_path, Fake(ccx=ccx_writing("cantilever", "something else entirely\n")))
    assert len(checks) == 2 and not any(c.ok for c in checks)
    assert "TIPC" in checks[0].note and "FIX" in checks[1].note


def test_the_tip_must_be_one_node(tmp_path):
    dat = disp_block("TIPC", [(1211, (0.0, -2.5, 0.0)), (1212, (0.0, -2.5, 0.0))]) + total_block("FIX", (0.0, 21.0, 0.0))
    checks = case_cantilever(tmp_path, Fake(ccx=ccx_writing("cantilever", dat)))
    assert [c.ok for c in checks] == [False, True]
    assert "1211" in checks[0].note and "1212" in checks[0].note


def test_a_program_that_cannot_be_started_fails_the_case(tmp_path):
    checks = case_cantilever(tmp_path, Fake())  # no ccx
    assert len(checks) == 1 and not checks[0].ok
    assert "ccx" in checks[0].note


# ---- 01 broken deck ---------------------------------------------------------------------------------------------


def broken_runner(code, output):
    def handler(argv, cwd):
        assert argv == ["ccx", "-i", "bad_modulus"]
        assert (cwd / "bad_modulus.inp").is_file()
        return Completed(code, output)

    return Fake(ccx=handler)


def test_broken_deck_must_be_rejected(tmp_path):
    (rejected,) = case_broken_deck(tmp_path, broken_runner(201, " *ERROR reading *ELASTIC. Card image:\n"))
    assert rejected.ok and "201" in rejected.note
    assert rejected.case == "01 broken deck"
    (accepted,) = case_broken_deck(tmp_path, broken_runner(0, ""))
    assert not accepted.ok
    (other_error,) = case_broken_deck(tmp_path, broken_runner(201, " *ERROR in calinput: something else"))
    assert not other_error.ok and "201" in other_error.note
    (timed_out,) = case_broken_deck(tmp_path, broken_runner(None, " *ERROR reading *ELASTIC\n[timed out after 300 s]"))
    assert not timed_out.ok
    (zero_with_text,) = case_broken_deck(tmp_path, broken_runner(0, " *ERROR reading *ELASTIC. Card image:"))
    assert not zero_with_text.ok  # accepted, whatever the text says


def test_broken_deck_copies_the_broken_file(tmp_path):
    case_broken_deck(tmp_path, broken_runner(201, " *ERROR reading *ELASTIC"))
    copied = next(tmp_path.rglob("bad_modulus.inp"))
    assert copied.read_bytes() == (config.ROOT / "exercises/01-cantilever/broken/bad_modulus.inp").read_bytes()


# ---- ccx -v -----------------------------------------------------------------------------------------------------


def version_runner(code, output):
    def handler(argv, cwd):
        assert argv == ["ccx", "-v"]
        return Completed(code, output)

    return Fake(ccx=handler)


def test_version_case_reports_the_exit_code(tmp_path):
    (good,) = case_version(tmp_path, version_runner(201, VERSION_OUTPUT))
    assert good.ok
    assert "201" in good.note and "version_exit_codes" in good.note
    assert good.note == "exit code 201: MCP-Anything reads this with its version_exit_codes=(0, 201)"
    (zero,) = case_version(tmp_path, version_runner(0, VERSION_OUTPUT))
    assert zero.ok and zero.note.startswith("exit code 0:")
    (no_line,) = case_version(tmp_path, version_runner(201, ""))
    assert not no_line.ok
    (wrong_exit,) = case_version(tmp_path, version_runner(1, VERSION_OUTPUT))
    assert not wrong_exit.ok and "1" in wrong_exit.note
    (other_version,) = case_version(tmp_path, version_runner(201, "\n  This is Version 2.19\n"))
    assert not other_version.ok
    (timed_out,) = case_version(tmp_path, version_runner(None, VERSION_OUTPUT + "[timed out after 300 s]"))
    assert not timed_out.ok


# ---- 02 beam ----------------------------------------------------------------------------------------------------


def gmsh_writing(mesh: str, output_file: str = "beam_mesh.inp", code: int = 0, seen: list | None = None):
    def handler(argv, cwd):
        if seen is not None:
            seen.append(argv)
        (cwd / "beam.geo").stat()  # the geometry has been copied next to the run
        if mesh is not None:
            (cwd / output_file).write_text(mesh, encoding="utf-8")
        return Completed(code, "Info    : Done writing 'beam_mesh.inp'\n")

    return handler


def beam_values(length: float) -> dict:
    return beam.selfweight_reference(length)["values"]


def test_gmsh_beam_uses_the_mean_over_the_tip(tmp_path):
    # the mean of the three tip nodes is the reference (-1.375 against -1.37515); any single node is off by more than 2 %
    dat = beam_dat((-1.0, -1.5, -1.625), 30.9)
    seen: list = []
    run = Fake(gmsh=gmsh_writing(BEAM_MESH, seen=seen), ccx=ccx_writing("beam_selfweight", dat))
    checks = case_gmsh_beam(tmp_path, run)
    assert [c.quantity for c in checks] == ["tip_displacement_y", "support_reaction_y"]
    assert all(c.ok for c in checks), checks
    assert checks[0].actual == pytest.approx(-1.375)
    assert checks[1].actual == 30.9
    assert checks[0].limit == pytest.approx(0.02 * 1.375151786)  # the reference's own tolerances, never hard-coded
    assert checks[1].limit == pytest.approx(0.01 * 30.8034)
    assert seen == [["gmsh", "beam.geo", "-3", "-format", "inp", "-o", "beam_mesh.inp"]]  # no -setnumber at the default L
    assert run.ran("ccx") == [("ccx", "-i", "beam_selfweight")]
    assert {c.case for c in checks} == {"02 beam L=1000"}


def test_gmsh_beam_one_node_is_not_the_mean(tmp_path):
    dat = beam_dat((-1.0, -1.0, -1.0), 30.9)
    checks = case_gmsh_beam(tmp_path, Fake(gmsh=gmsh_writing(BEAM_MESH), ccx=ccx_writing("beam_selfweight", dat)))
    assert [c.ok for c in checks] == [False, True]


def test_gmsh_beam_length_sets_the_number_and_the_reference(tmp_path):
    expected = beam_values(500.0)
    dat = beam_dat((expected["tip_displacement_y"],) * 2, expected["support_reaction_y"])
    seen: list = []
    run = Fake(gmsh=gmsh_writing(BEAM_MESH, seen=seen), ccx=ccx_writing("beam_selfweight", dat))
    checks = case_gmsh_beam(tmp_path, run, 500.0)
    assert all(c.ok for c in checks), checks
    assert seen == [["gmsh", "beam.geo", "-3", "-format", "inp", "-o", "beam_mesh.inp", "-setnumber", "L", "500"]]
    assert {c.case for c in checks} == {"02 beam L=500"}
    # the same results are wrong for the default length: the reference follows the length
    other = case_gmsh_beam(tmp_path, Fake(gmsh=gmsh_writing(BEAM_MESH), ccx=ccx_writing("beam_selfweight", dat)))
    assert not any(c.ok for c in other)


def test_gmsh_beam_runs_each_length_in_its_own_folder(tmp_path):
    run = Fake(gmsh=gmsh_writing(BEAM_MESH), ccx=ccx_writing("beam_selfweight", beam_dat((-1.375,), 30.8)))
    case_gmsh_beam(tmp_path, run)
    case_gmsh_beam(tmp_path, run, 500.0)
    assert len(list(tmp_path.rglob("beam_selfweight.dat"))) == 2


@pytest.mark.parametrize("types", ["C3D4", "CPS6", "C3D10, ELSET=a\n1, 1, 1, 1, 1, 1, 1, 1, 1, 1\n*ELEMENT, type=C3D20"])
def test_gmsh_beam_refuses_other_element_types_and_never_calls_ccx(tmp_path, types):
    mesh = BEAM_MESH.replace("C3D10", types, 1)
    run = Fake(gmsh=gmsh_writing(mesh), ccx=ccx_writing("beam_selfweight", beam_dat((-1.375,), 30.8)))
    checks = case_gmsh_beam(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert "C3D10" in " ".join(c.note for c in checks)
    assert run.ran("ccx") == []


def test_gmsh_beam_fails_when_gmsh_fails_or_writes_no_mesh(tmp_path):
    ccx = ccx_writing("beam_selfweight", beam_dat((-1.375,), 30.8))
    for gmsh in (
        gmsh_writing(BEAM_MESH, code=1),
        gmsh_writing(None),  # exit 0 and no file
        gmsh_writing(""),  # an empty file
        lambda argv, cwd: Completed(None, "[timed out after 300 s]"),
    ):
        run = Fake(gmsh=gmsh, ccx=ccx)
        checks = case_gmsh_beam(tmp_path, run)
        assert checks and not any(c.ok for c in checks)
        assert run.ran("ccx") == []


# ---- 04 cable ---------------------------------------------------------------------------------------------------


@pytest.fixture
def cable_mesh(gmsh_2d) -> str:
    """gmsh_2d (two CPS6 triangles; OUTER is the edge x = 1) with the two probe points as node sets."""
    return gmsh_2d + "*NSET,NSET=P_CORE\n1, \n*NSET,NSET=P_OUTER\n3, \n"


def cable_dat(core_rows, outer_rows) -> str:
    return disp_block("P_CORE", core_rows) + disp_block("P_OUTER", outer_rows)


def cable_ccx(dat: str, seen: dict | None = None):
    def handler(argv, cwd):
        assert argv == ["ccx", "-i", "cable_pressure"]
        if seen is not None:
            seen["mesh"] = (cwd / "cable_mesh.inp").read_text(encoding="utf-8")
            seen["load"] = (cwd / "cable_pressure_load.inc").read_text(encoding="utf-8")
        (cwd / "cable_pressure.dat").write_text(dat, encoding="utf-8")
        return Completed(0, "")

    return handler


def cable_gmsh(mesh: str, seen: list | None = None):
    def handler(argv, cwd):
        if seen is not None:
            seen.append(argv)
        assert (cwd / "cable_quarter.geo").is_file()
        (cwd / "cable_mesh_gmsh.inp").write_text(mesh, encoding="utf-8")
        return Completed(0, "")

    return handler


def reference_row(node: int, name: str, scale: float = 1.0) -> tuple[int, tuple[float, float, float]]:
    return node, (layers.cable_reference()["values"][name] * scale, 0.0, 0.0)


def test_cable_case_reads_the_gmsh_node(tmp_path, cable_mesh):
    # ccx expands the plane elements into 3-D ones and prints a row for every node of the set: the Gmsh node is the one
    # whose id is in the mesh's node set; the other rows are made to be wrong
    core = [reference_row(101, "u_r_core_edge", 5.0), reference_row(1, "u_r_core_edge"), reference_row(201, "u_r_core_edge", 5.0)]
    outer = [reference_row(103, "u_r_outer", 0.1), reference_row(203, "u_r_outer", 0.1), reference_row(3, "u_r_outer")]
    gmsh_seen: list = []
    stored: dict = {}
    run = Fake(gmsh=cable_gmsh(cable_mesh, gmsh_seen), ccx=cable_ccx(cable_dat(core, outer), stored))
    checks = case_cable(tmp_path, run)
    assert [c.quantity for c in checks] == ["u_r_core_edge", "u_r_outer"]
    assert all(c.ok for c in checks), checks
    assert [c.note for c in checks] == ["(3 rows printed)", "(3 rows printed)"]  # what ccx printed: item C6 of the checklist
    assert {c.case for c in checks} == {"04 cable"}
    assert gmsh_seen == [["gmsh", "cable_quarter.geo", "-2", "-format", "inp", "-o", "cable_mesh_gmsh.inp"]]
    assert "type=CPE6" in stored["mesh"] and "CPS6" not in stored["mesh"]  # plane strain
    assert stored["load"] == "*DLOAD\n1, P2, 1.000000E+01\n"  # the one face of OUTER, at +CABLE_PRESSURE
    assert layers.CABLE_PRESSURE == 10.0
    assert run.ran("ccx") == [("ccx", "-i", "cable_pressure")]


def test_cable_case_compares_with_the_cable_reference(tmp_path, cable_mesh):
    core = [reference_row(1, "u_r_core_edge", 1.5)]  # 50 % off
    outer = [reference_row(3, "u_r_outer", 1.01)]  # 1 % off: inside 2 %
    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(cable_mesh), ccx=cable_ccx(cable_dat(core, outer))))
    assert [c.ok for c in checks] == [False, True]
    assert checks[0].expected == layers.cable_reference()["values"]["u_r_core_edge"]
    assert checks[1].limit == pytest.approx(0.02 * abs(layers.cable_reference()["values"]["u_r_outer"]))


def test_cable_case_notes_how_many_rows_ccx_printed(tmp_path, cable_mesh):
    core = [reference_row(1, "u_r_core_edge", 1.5)]  # 50 % off, one row printed
    outer = [reference_row(3, "u_r_outer"), reference_row(103, "u_r_outer"), reference_row(203, "u_r_outer"), reference_row(303, "u_r_outer")]
    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(cable_mesh), ccx=cable_ccx(cable_dat(core, outer))))
    assert [c.ok for c in checks] == [False, True]
    assert checks[0].note.startswith("differs by ") and checks[0].note.endswith(" (1 row printed)")  # singular, after the reason
    assert checks[1].note == "(4 rows printed)"


def test_cable_case_needs_exactly_one_gmsh_node_row(tmp_path, cable_mesh):
    mesh = cable_mesh.replace("*NSET,NSET=P_CORE\n1, \n", "*NSET,NSET=P_CORE\n1, 4, \n")  # two Gmsh nodes in the set
    outer = [reference_row(3, "u_r_outer")]
    two = [reference_row(1, "u_r_core_edge"), reference_row(4, "u_r_core_edge"), reference_row(101, "u_r_core_edge")]
    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(mesh), ccx=cable_ccx(cable_dat(two, outer))))
    assert not checks[0].ok and checks[0].quantity == "u_r_core_edge"
    assert "1" in checks[0].note and "4" in checks[0].note and "101" in checks[0].note  # the rows found are listed
    assert not checks[0].note.endswith("rows printed)")  # the reason already lists the rows: no second count
    assert checks[1].ok  # the other probe is read on its own

    none = [reference_row(101, "u_r_core_edge"), reference_row(201, "u_r_core_edge")]
    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(cable_mesh), ccx=cable_ccx(cable_dat(none, outer))))
    assert not checks[0].ok
    assert "101" in checks[0].note and "201" in checks[0].note
    assert checks[1].ok


def test_cable_case_without_the_probe_block_fails(tmp_path, cable_mesh):
    dat = disp_block("P_CORE", [reference_row(1, "u_r_core_edge")])  # no P_OUTER block
    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(cable_mesh), ccx=cable_ccx(dat)))
    assert [c.ok for c in checks] == [True, False]
    assert "P_OUTER" in checks[1].note


def test_cable_case_without_the_node_set_in_the_mesh_fails(tmp_path, gmsh_2d):
    dat = cable_dat([reference_row(1, "u_r_core_edge")], [reference_row(3, "u_r_outer")])
    run = Fake(gmsh=cable_gmsh(gmsh_2d), ccx=cable_ccx(dat))  # gmsh_2d has no P_CORE and no P_OUTER
    checks = case_cable(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert "P_CORE" in " ".join(c.note for c in checks)


def clockwise(mesh: str) -> str:
    assert mesh.count("1, 1, 2, 3, 5, 6, 7") == 1
    return mesh.replace("1, 1, 2, 3, 5, 6, 7", "1, 1, 3, 2, 7, 6, 5")


@pytest.mark.parametrize(
    "break_mesh, mentions",
    [
        (lambda mesh: mesh.replace("type=CPS6", "type=CPS3"), "CPS3"),  # a plane-stress type that cannot be renamed
        (lambda mesh: mesh.replace("type=CPS6", "type=T3D3"), "T3D3"),
        (clockwise, "counter-clockwise"),
    ],
    ids=["plane-stress-3-node", "line-elements", "clockwise"],
)
def test_cable_case_refuses_plane_stress_or_clockwise_meshes(tmp_path, cable_mesh, break_mesh, mentions):
    dat = cable_dat([reference_row(1, "u_r_core_edge")], [reference_row(3, "u_r_outer")])
    run = Fake(gmsh=cable_gmsh(break_mesh(cable_mesh)), ccx=cable_ccx(dat))
    checks = case_cable(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert mentions in " ".join(c.note for c in checks)
    assert run.ran("ccx") == [], "ccx must never see a plane-stress or clockwise mesh"


def test_cable_case_refuses_a_mesh_without_outer_faces(tmp_path, cable_mesh):
    mesh = cable_mesh.replace("*NSET,NSET=OUTER\n2, 6, 3, \n", "*NSET,NSET=OUTER\n2, \n")
    dat = cable_dat([reference_row(1, "u_r_core_edge")], [reference_row(3, "u_r_outer")])
    run = Fake(gmsh=cable_gmsh(mesh), ccx=cable_ccx(dat))
    checks = case_cable(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert run.ran("ccx") == []


def test_cable_case_fails_when_gmsh_fails(tmp_path):
    run = Fake(gmsh=lambda argv, cwd: Completed(1, "Error   : something\n"), ccx=cable_ccx(""))
    checks = case_cable(tmp_path, run)
    assert checks and not any(c.ok for c in checks)
    assert run.ran("ccx") == []


def test_cable_case_fails_on_a_solver_error(tmp_path, cable_mesh):
    def failing(argv, cwd):
        (cwd / "cable_pressure.dat").write_text("x", encoding="utf-8")
        return Completed(201, " *ERROR in gen3delem")

    checks = case_cable(tmp_path, Fake(gmsh=cable_gmsh(cable_mesh), ccx=failing))
    assert checks and not any(c.ok for c in checks)
    assert "*ERROR" in " ".join(c.note for c in checks)


# ---- main -------------------------------------------------------------------------------------------------------


def good_ccx(cable_mesh_text: str):
    """A ccx that answers every call of the workshop with the reference values."""
    lengths: dict[Path, float] = {}

    def handler(argv, cwd):
        if argv == ["ccx", "-v"]:
            return Completed(201, VERSION_OUTPUT)
        job = argv[2]
        if job == "cantilever":
            return ccx_writing(job, cantilever_dat())(argv, cwd)
        if job == "bad_modulus":
            return Completed(201, " *ERROR reading *ELASTIC. Card image:\n")
        if job == "beam_selfweight":
            values = beam_values(lengths[cwd])
            dat = beam_dat((values["tip_displacement_y"],) * 3, values["support_reaction_y"])
            return ccx_writing(job, dat)(argv, cwd)
        assert job == "cable_pressure", job
        dat = cable_dat([reference_row(1, "u_r_core_edge"), reference_row(101, "u_r_core_edge", 3.0)], [reference_row(3, "u_r_outer")])
        return cable_ccx(dat)(argv, cwd)

    def note_length(argv, cwd):  # the length of a beam run, for the ccx that follows in the same folder
        lengths[cwd] = float(argv[argv.index("-setnumber") + 2]) if "-setnumber" in argv else 1000.0

    return handler, note_length


def good_runner(cable_mesh_text: str, ccx_override=None) -> Fake:
    ccx, note_length = good_ccx(cable_mesh_text)

    def gmsh(argv, cwd):
        if argv[1] == "beam.geo":
            note_length(argv, cwd)
            return gmsh_writing(BEAM_MESH)(argv, cwd)
        return cable_gmsh(cable_mesh_text)(argv, cwd)

    def dispatch(argv, cwd):
        if ccx_override is not None and (answer := ccx_override(argv, cwd)) is not None:
            return answer
        return ccx(argv, cwd)

    return Fake(ccx=dispatch, gmsh=gmsh)


def test_main_passes_and_removes_its_folder(tmp_path, cable_mesh, monkeypatch, capsys):
    created: list[str] = []
    real = tempfile.mkdtemp

    def mkdtemp(prefix=None):
        created.append(prefix)
        return real(prefix=prefix, dir=tmp_path)

    monkeypatch.setattr(verify.tempfile, "mkdtemp", mkdtemp)
    run = good_runner(cable_mesh)
    assert verify.main([], run=run) == 0
    out = capsys.readouterr().out
    assert created == ["workshop-verify-"]
    assert list(tmp_path.iterdir()) == []  # everything passed: the work folder is gone
    assert out.rstrip().splitlines()[-1] == "VERIFY: PASS"
    assert "FAIL" not in out.replace("VERIFY: PASS", "")
    # the whole table: every case and the numbers
    for text in ("01 cantilever", "01 broken deck", "version", "02 beam L=1000", "02 beam L=500", "04 cable", "tip_displacement_y",
                 "support_reaction_y", "u_r_core_edge", "u_r_outer", "PASS"):
        assert text in out
    assert "201" in out  # the broken deck's and the version's exit code
    assert len(run.ran("gmsh")) == 3 and len(run.ran("ccx", "-i")) == 5 and len(run.ran("ccx", "-v")) == 1


def test_main_fails_and_keeps_its_folder(tmp_path, cable_mesh, monkeypatch, capsys):
    real = tempfile.mkdtemp
    monkeypatch.setattr(verify.tempfile, "mkdtemp", lambda prefix=None: real(prefix=prefix, dir=tmp_path))

    def wrong_cantilever(argv, cwd):
        if argv == ["ccx", "-i", "cantilever"]:
            return ccx_writing("cantilever", cantilever_dat(-2.7))(argv, cwd)
        return None

    assert verify.main([], run=good_runner(cable_mesh, wrong_cantilever)) == 1
    out = capsys.readouterr().out
    assert out.rstrip().splitlines()[-1] == "VERIFY: FAIL"
    assert "FAIL" in out
    (kept,) = tmp_path.iterdir()
    assert str(kept) in out  # it says where the run folders are
    assert (kept / "01-cantilever" / "cantilever.dat").is_file()


def test_main_keep_uses_that_folder_and_leaves_it(tmp_path, cable_mesh, capsys):
    keep = tmp_path / "kept" / "deep"
    assert verify.main(["--keep", str(keep)], run=good_runner(cable_mesh)) == 0
    assert (keep / "01-cantilever" / "cantilever.dat").is_file()
    assert (keep / "02-beam-L500").is_dir() and (keep / "04-cable" / "cable_mesh.inp").is_file()
    assert "VERIFY: PASS" in capsys.readouterr().out


def test_main_keep_ignores_a_stale_dat(tmp_path, cable_mesh):
    stale = tmp_path / "01-cantilever" / "cantilever.dat"
    stale.parent.mkdir()
    stale.write_text(cantilever_dat(), encoding="utf-8")  # a good result from an earlier run

    def no_output(argv, cwd):  # this ccx exits 0 and writes nothing
        return Completed(0, "") if argv == ["ccx", "-i", "cantilever"] else None

    assert verify.main(["--keep", str(tmp_path), "--only", "01"], run=good_runner(cable_mesh, no_output)) == 1


def test_main_keep_must_be_a_usable_folder(tmp_path, cable_mesh, capsys):
    a_file = tmp_path / "file"
    a_file.write_text("x", encoding="utf-8")
    run = good_runner(cable_mesh)
    assert verify.main(["--keep", str(a_file)], run=run) == 2
    assert "work folder" in capsys.readouterr().err
    assert run.calls == []


def test_main_reports_a_program_that_cannot_be_started(tmp_path, capsys):
    assert verify.main(["--keep", str(tmp_path)], run=Fake()) == 1  # no ccx, no gmsh
    out = capsys.readouterr().out
    assert "VERIFY: FAIL" in out and "Traceback" not in out


def test_only_selects_the_cases(tmp_path, cable_mesh, capsys):
    run = good_runner(cable_mesh)
    assert verify.main(["--only", "02", "--keep", str(tmp_path)], run=run) == 0
    assert run.ran("ccx", "-i", "cantilever") == [] and run.ran("ccx", "-i", "bad_modulus") == [] and run.ran("ccx", "-v") == []
    assert run.ran("ccx", "-i", "cable_pressure") == []
    assert [call[:2] for call in run.ran("gmsh")] == [("gmsh", "beam.geo")] * 2
    assert run.ran("ccx", "-i", "beam_selfweight") == [("ccx", "-i", "beam_selfweight")] * 2
    out = capsys.readouterr().out
    assert "02 beam L=1000" in out and "02 beam L=500" in out
    assert "04 cable" not in out and "01 cantilever" not in out

    run = good_runner(cable_mesh)
    assert verify.main(["--only", "01", "--keep", str(tmp_path / "a")], run=run) == 0
    assert sorted(call[1:] for call in run.calls) == [("-i", "bad_modulus"), ("-i", "cantilever"), ("-v",)]

    run = good_runner(cable_mesh)
    assert verify.main(["--only", "04", "--keep", str(tmp_path / "b")], run=run) == 0
    assert [call[:2] for call in run.calls] == [("gmsh", "cable_quarter.geo"), ("ccx", "-i")]


def test_only_refuses_an_unknown_case(tmp_path, cable_mesh, capsys):
    assert verify.main(["--only", "03", "--keep", str(tmp_path)], run=good_runner(cable_mesh)) == 2
    assert "03" in capsys.readouterr().err


def test_main_without_solvers_says_where_to_run(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert verify.main([]) == 1
    assert "dev container" in capsys.readouterr().out
    # either program missing is enough
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ccx" if name == "ccx" else None)
    assert verify.main([]) == 1
    assert "CalculiX or Gmsh not found: run this inside the workshop dev container (README.md)" in capsys.readouterr().out


def test_a_given_runner_is_never_checked_with_which(tmp_path, cable_mesh, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert verify.main(["--only", "01", "--keep", str(tmp_path)], run=good_runner(cable_mesh)) == 0


def test_the_default_runner_is_run_process():
    assert inspect.signature(verify.main).parameters["run"].default is run_process


def test_the_check_is_a_frozen_record():
    check = Check("c", "q", 1.0, None, None, False)
    assert check.note == ""
    with pytest.raises(AttributeError):
        check.ok = True  # type: ignore[misc]


def test_the_table_has_one_row_per_check():
    table = verify.format_table(
        [Check("01 cantilever", "tip_displacement_y", -2.5, -2.4999, 0.05, True), Check("version", "ccx -v", None, None, None, False, "no line")]
    )
    lines = table.splitlines()
    assert len(lines) == 3  # the header and two rows
    assert "PASS" in lines[1] and "-2.5" in lines[1] and "0.05" in lines[1]
    assert "FAIL" in lines[2] and "no line" in lines[2]


# ---- the script -------------------------------------------------------------------------------------------------


def test_verify_script_is_executable_in_git(root):
    if not in_git(root):
        pytest.skip("not a git top level")
    listed = git_output(root, "ls-files", "-s", "scripts/verify_decks.sh")
    if not listed:
        pytest.skip("scripts/verify_decks.sh is not tracked yet")
    assert listed.decode("utf-8").startswith("100755 "), listed


def test_verify_script_text():
    text = stored_bytes(config.ROOT, "scripts/verify_decks.sh")
    assert b"\r" not in text, "git must store LF"
    lines = text.decode("utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert "set -euo pipefail" in lines
    assert lines[-1] == 'exec python3 -m workshop.verify "$@"'
    assert 'cd "$(dirname "$0")/.."' in lines
    assert not re.search(r"(^|\s)python\s", text.decode("utf-8")), "never a bare python"
