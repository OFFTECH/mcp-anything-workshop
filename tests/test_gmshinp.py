"""Gmsh .inp helpers. The meshes are hand-written snippets in the layout Gmsh 4.12.1 writes; Gmsh itself is not run."""

import subprocess
import sys

import pytest

from workshop import gmshinp
from workshop.gmshinp import (
    clockwise_elements,
    dload_text,
    element_types,
    elements,
    node_coordinates,
    node_sets,
    physical_names,
    pressure_faces,
    to_plane_strain,
)

ELEMENT_1 = "1, 1, 2, 3, 5, 6, 7"
ELEMENT_1_CLOCKWISE = "1, 1, 3, 2, 7, 6, 5"  # nodes 2 and 3 swapped, and with them mid-nodes 4 and 6


def clockwise_mesh(text: str) -> str:
    assert text.count(ELEMENT_1) == 1
    return text.replace(ELEMENT_1, ELEMENT_1_CLOCKWISE)


def test_physical_names_reads_every_dimension():
    geo = """
    Physical Point("ANCHOR") = {1};
    Physical Curve( "OUTER" ) = {2, 3};
    Physical Line("RIB") = {4};
    Physical Surface("CABLE", 7) = {1};
    Physical Volume("BLOCK") = {1};
    // Physical Surface("COMMENTED") = {9};
    """
    assert physical_names(geo) == {"ANCHOR": 0, "OUTER": 1, "RIB": 1, "CABLE": 2, "BLOCK": 3}


def test_parsers_read_the_gmsh_layout(gmsh_2d):
    assert element_types(gmsh_2d) == ["CPS6"]
    assert set(node_sets(gmsh_2d)) == {"OUTER", "SYMX", "SYMY"}  # the ELSET is not a node set
    assert node_sets(gmsh_2d)["OUTER"] == {2, 3, 6}  # the empty field after the trailing ", " is ignored
    coordinates = node_coordinates(gmsh_2d)
    assert len(coordinates) == 9
    assert coordinates[6] == (1.0, 0.5, 0.0)
    assert elements(gmsh_2d) == {1: ("CPS6", (1, 2, 3, 5, 6, 7)), 2: ("CPS6", (1, 3, 4, 7, 8, 9))}


def test_parsers_join_wrapped_lines_and_skip_comments():
    # Gmsh wraps an element line after 16 entries and ends the wrapped line with ", " (MElement::writeINP)
    nodes = list(range(1, 21))
    text = "\n".join(
        [
            "*NODE",
            *(f"{n}, {n}, 0, 0" for n in nodes),
            "** a comment",
            "*ELEMENT, type=C3D20, ELSET=Volume1",
            "1, " + ", ".join(str(n) for n in nodes[:15]) + ", ",
            ", ".join(str(n) for n in nodes[15:]),
            "*NSET,NSET=TOP",
            "1, 2, 3, 4, 5, 6, 7, 8, 9, 10, ",
            "11, 12, ",
            "",
        ]
    )
    assert elements(text) == {1: ("C3D20", tuple(nodes))}
    assert node_sets(text) == {"TOP": set(range(1, 13))}


def test_to_plane_strain_renames_cps6(gmsh_2d):
    result = to_plane_strain(gmsh_2d)
    assert "type=CPE6" in result
    assert "CPS6" not in result
    assert result.replace("CPE6", "CPS6") == gmsh_2d  # everything else is unchanged
    assert element_types(result) == ["CPE6"]


def test_to_plane_strain_keeps_line_endings(gmsh_2d):
    crlf = gmsh_2d.replace("\n", "\r\n")
    assert to_plane_strain(crlf) == crlf.replace("CPS6", "CPE6")


@pytest.mark.parametrize("bad", ["CPS3", "CPS8", "T3D3", "C3D10"])
def test_other_element_types_are_refused(bad, gmsh_2d):
    with pytest.raises(ValueError, match=bad) as refusal:
        to_plane_strain(gmsh_2d.replace("type=CPS6", f"type={bad}"))
    assert "Mesh.ElementOrder = 2" in str(refusal.value)  # the way to get second-order triangles from Gmsh


def test_one_other_block_among_cps6_blocks_is_refused(gmsh_2d):
    mixed = gmsh_2d.replace("*ELSET,ELSET=CABLE", "*ELEMENT, type=T3D3, ELSET=Line1\n3, 2, 6, 3\n*ELSET,ELSET=CABLE")
    with pytest.raises(ValueError, match="T3D3"):
        to_plane_strain(mixed)


def test_a_mesh_without_elements_is_refused():
    with pytest.raises(ValueError, match="ELEMENT"):
        to_plane_strain("*Heading\n x.inp\n*NODE\n1, 0, 0, 0\n")


def test_an_element_with_the_wrong_node_count_is_refused(gmsh_2d):
    short = gmsh_2d.replace(ELEMENT_1, "1, 1, 2, 3, 5, 6")
    with pytest.raises(ValueError, match="element 1"):
        elements(short)
    with pytest.raises(ValueError, match="element 1"):
        to_plane_strain(short)


def test_an_unknown_element_type_is_refused_by_the_parser(gmsh_2d):
    with pytest.raises(ValueError, match="XYZ9"):
        elements(gmsh_2d.replace("type=CPS6", "type=XYZ9"))


def test_a_repeated_id_is_refused(gmsh_2d):
    with pytest.raises(ValueError, match="node 2"):
        node_coordinates(gmsh_2d.replace("3, 1, 1, 0", "2, 1, 1, 0"))
    with pytest.raises(ValueError, match="element 1"):
        elements(gmsh_2d.replace("2, 1, 3, 4, 7, 8, 9", "1, 1, 3, 4, 7, 8, 9"))


def test_clockwise_triangles_are_found(gmsh_2d):
    assert clockwise_elements(gmsh_2d) == []
    assert clockwise_elements(clockwise_mesh(gmsh_2d)) == [1]
    assert clockwise_elements(to_plane_strain(clockwise_mesh(gmsh_2d))) == [1]


def test_a_degenerate_triangle_counts_as_clockwise(gmsh_2d):
    flat = gmsh_2d.replace("3, 1, 1, 0", "3, 2, 0, 0")  # node 3 on the x axis: element 1 has no area
    assert 1 in clockwise_elements(flat)


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf"])
def test_a_non_finite_coordinate_is_refused(bad, gmsh_2d):
    with pytest.raises(ValueError, match="finite"):
        node_coordinates(gmsh_2d.replace("3, 1, 1, 0", f"3, 1, {bad}, 0"))
    with pytest.raises(ValueError, match="finite"):
        clockwise_elements(gmsh_2d.replace("3, 1, 1, 0", f"3, 1, {bad}, 0"))


def test_an_area_that_is_not_a_number_counts_as_clockwise(gmsh_2d):
    # nodes 2 and 3 far out: both products of the area overflow to inf and inf - inf is NaN; that is not "positive"
    huge = gmsh_2d.replace("2, 1, 0, 0", "2, 1e308, 1e308, 0").replace("3, 1, 1, 0", "3, 1e308, 1e308, 0")
    assert clockwise_elements(huge) == [1]


def test_an_element_with_a_missing_node_is_refused(gmsh_2d):
    with pytest.raises(ValueError, match="node 3"):
        clockwise_elements(gmsh_2d.replace("3, 1, 1, 0\n", ""))


def test_pressure_faces_and_dload_text(gmsh_2d):
    assert pressure_faces(gmsh_2d, "OUTER") == [(1, 2)]  # element 1, face 2 = nodes 2, 3 and mid-node 5 (=6)
    assert pressure_faces(gmsh_2d, "outer") == [(1, 2)]  # set names are not case sensitive
    assert pressure_faces(gmsh_2d, "SYMY") == [(1, 1)]  # face 1 = nodes 1, 2 and mid-node 4 (=5)
    assert pressure_faces(gmsh_2d, "SYMX") == [(2, 3)]  # face 3 = nodes 3, 1 and mid-node 6 of element 2 (4, 1, 9)
    assert pressure_faces(to_plane_strain(gmsh_2d), "OUTER") == [(1, 2)]
    assert dload_text([(1, 2)], 10.0) == "*DLOAD\n1, P2, 1.000000E+01\n"
    assert dload_text([(1, 2), (3, 1)], -0.5) == "*DLOAD\n1, P2, -5.000000E-01\n3, P1, -5.000000E-01\n"


@pytest.mark.parametrize(
    ("other", "count"), [("CPS3", 3), ("CPE3", 3), ("CPS4", 4), ("CPE4", 4), ("CPS8", 8), ("CPE8", 8)]
)
def test_other_plane_elements_are_refused_not_skipped(other, count, gmsh_2d):
    # their edges would be loaded by the same node set; skipping them would give a partial load
    nodes = ", ".join(str(n) for n in range(1, count + 1))
    block = f"*ELEMENT, type={other}, ELSET=Surface2\n3, {nodes}\n"
    mixed = gmsh_2d.replace("*ELSET,ELSET=CABLE", block + "*ELSET,ELSET=CABLE")
    with pytest.raises(ValueError, match=other) as refusal:
        pressure_faces(mixed, "OUTER")
    assert "partial" in str(refusal.value)


def test_line_elements_next_to_the_triangles_are_not_loaded(gmsh_2d):
    # a physical curve makes Gmsh write T3D3 boundary elements: they carry no pressure face and are left out
    block = "*ELEMENT, type=T3D3, ELSET=Line1\n3, 2, 6, 3\n"
    with_curve = gmsh_2d.replace("*ELSET,ELSET=CABLE", block + "*ELSET,ELSET=CABLE")
    assert pressure_faces(with_curve, "OUTER") == [(1, 2)]


def test_a_face_needs_all_three_nodes_in_the_set(gmsh_2d):
    corners_only = gmsh_2d.replace("2, 6, 3, ", "2, 3, ")  # without the mid-node 6 the edge is not a face
    assert pressure_faces(corners_only, "OUTER") == []


def test_no_faces_is_an_error(gmsh_2d):
    with pytest.raises(ValueError, match="no faces"):
        dload_text([], 10.0)
    assert pressure_faces(gmsh_2d + "*NSET,NSET=TWO\n1, 3, \n", "TWO") == []


def test_an_unknown_node_set_is_an_error(gmsh_2d):
    with pytest.raises(ValueError, match="NOSUCH"):
        pressure_faces(gmsh_2d, "NOSUCH")


def test_command_line(tmp_path, gmsh_2d, capsys):
    mesh = tmp_path / "mesh.inp"
    mesh.write_bytes(gmsh_2d.encode())
    out = tmp_path / "plane_strain.inp"
    assert gmshinp.main(["plane-strain", str(mesh), str(out)]) == 0
    assert out.read_bytes() == gmsh_2d.replace("CPS6", "CPE6").encode()

    load = tmp_path / "load.inc"
    assert gmshinp.main(["dload", str(out), "OUTER", "10", str(load)]) == 0
    assert load.read_bytes() == b"*DLOAD\n1, P2, 1.000000E+01\n"

    bad_mesh = tmp_path / "clockwise.inp"
    bad_mesh.write_bytes(clockwise_mesh(gmsh_2d).encode())
    bad_out = tmp_path / "clockwise_out.inp"
    capsys.readouterr()
    assert gmshinp.main(["plane-strain", str(bad_mesh), str(bad_out)]) == 1
    assert not bad_out.exists()  # a refused mesh leaves no output behind
    assert capsys.readouterr().err.startswith("error: 1 triangle(s) do not run counter-clockwise (element 1): ")


def test_dload_takes_a_negative_exponent_value_after_double_dash(tmp_path, gmsh_2d):
    # Python 3.12 (the codespace's python3) reads "-1e3" as an option unless "--" comes first
    mesh = tmp_path / "mesh.inp"
    mesh.write_bytes(gmsh_2d.encode())
    load = tmp_path / "load.inc"
    assert gmshinp.main(["dload", "--", str(mesh), "OUTER", "-1e3", str(load)]) == 0
    assert load.read_bytes() == b"*DLOAD\n1, P2, -1.000000E+03\n"


def test_dload_help_explains_the_double_dash_and_the_sign(capsys):
    assert gmshinp.main(["dload", "--help"]) == 0
    text = capsys.readouterr().out
    assert "dload -- MESH NSET -1e3 OUT" in text
    assert "exponent form needs `--` before the arguments" in text
    assert "a positive value presses onto the face" in text
    assert "manual section 7.43" in text


def test_command_line_errors_exit_1(tmp_path, gmsh_2d, capsys):
    mesh = tmp_path / "mesh.inp"
    mesh.write_bytes(gmsh_2d.encode())
    out = tmp_path / "out.inc"
    for argv in (
        ["plane-strain", str(tmp_path / "missing.inp"), str(out)],  # no such file
        ["dload", str(mesh), "NOSUCH", "10", str(out)],  # no such node set
        ["dload", str(mesh), "SYMX", "ten", str(out)],  # not a number
        ["dload", str(mesh), "SYMX", "nan", str(out)],  # not finite
    ):
        assert gmshinp.main(argv) == 1, argv
        assert capsys.readouterr().err.startswith("error: "), argv
    assert not out.exists()

    other = tmp_path / "other.inp"
    other.write_bytes(gmsh_2d.replace("type=CPS6", "type=CPS3").encode())
    assert gmshinp.main(["plane-strain", str(other), str(out)]) == 1
    assert "CPS3" in capsys.readouterr().err
    assert not out.exists()


def test_runs_as_a_module(tmp_path, gmsh_2d, root):
    mesh = tmp_path / "mesh.inp"
    mesh.write_bytes(gmsh_2d.encode())
    out = tmp_path / "out.inp"
    load = tmp_path / "load.inc"
    for args in (
        ["plane-strain", str(mesh), str(out)],
        ["dload", "--", str(mesh), "OUTER", "-1e3", str(load)],
    ):
        done = subprocess.run(
            [sys.executable, "-m", "workshop.gmshinp", *args], cwd=root, capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr
    assert "CPE6" in out.read_text()
    assert load.read_bytes() == b"*DLOAD\n1, P2, -1.000000E+03\n"
