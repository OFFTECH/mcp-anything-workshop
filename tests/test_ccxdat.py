"""The .dat reader. The texts are literal, in the layout of CalculiX 2.21 `printoutnode.f` (never from a real run).

    displacements:  ` displacements (vx,vy,vz) for set <SET> and time <e14.7>`, a blank line, rows `(i10,1p,3(1x,e13.6))`
    total force:    ` total force (fx,fy,fz) for set <SET> and time <e14.7>`, a blank line, one row `(6x,1p,3(1x,e13.6))`
"""

import re

import pytest
from _datfixtures import TIME_1, TIME_2, disp_block, disp_row, total_block, total_row

from workshop.ccxdat import node_vectors, total_force

DAT = (
    disp_block("TIPC", [(1211, (1.250000e-02, -2.499000e00, -3.0e-04))])
    + total_block("FIX", (-1.0e-05, 2.1e01, 4.5e-06))
)


def test_reads_displacements_for_a_set():
    assert node_vectors(DAT, "TIPC") == {1211: (1.25e-02, -2.499, -3.0e-04)}
    several = disp_block("TIP", [(1201, (0.0, -2.5, 0.0)), (1202, (1.0e-3, -2.4, 1.0e-4)), (1203, (-1.0e-3, -2.6, 0.0))])
    assert node_vectors(several, "TIP") == {1201: (0.0, -2.5, 0.0), 1202: (1.0e-3, -2.4, 1.0e-4), 1203: (-1.0e-3, -2.6, 0.0)}


def test_set_names_match_case_insensitively():
    assert node_vectors(DAT, "tipc") == node_vectors(DAT, "TIPC")
    assert total_force(DAT, "fix") == total_force(DAT, "FIX")
    assert node_vectors(disp_block("p_core", [(7, (1.0, 2.0, 3.0))]), "P_CORE") == {7: (1.0, 2.0, 3.0)}


def test_reads_the_total_force():
    assert total_force(DAT, "FIX") == (-1.0e-05, 2.1e01, 4.5e-06)


def test_last_block_wins():
    text = disp_block("TIPC", [(1211, (0.0, -1.0, 0.0))], TIME_1) + disp_block("TIPC", [(1211, (0.0, -2.0, 0.0))], TIME_2)
    assert node_vectors(text, "TIPC") == {1211: (0.0, -2.0, 0.0)}
    forces = total_block("FIX", (0.0, 10.0, 0.0), TIME_1) + total_block("FIX", (0.0, 21.0, 0.0), TIME_2)
    assert total_force(forces, "FIX") == (0.0, 21.0, 0.0)


def test_last_block_wins_when_the_sets_alternate():
    text = (
        disp_block("TIPC", [(1211, (0.0, -1.0, 0.0))], TIME_1)
        + disp_block("OTHER", [(5, (9.0, 9.0, 9.0))], TIME_1)
        + disp_block("TIPC", [(1211, (0.0, -2.0, 0.0))], TIME_2)
        + disp_block("OTHER", [(5, (8.0, 8.0, 8.0))], TIME_2)
    )
    assert node_vectors(text, "TIPC") == {1211: (0.0, -2.0, 0.0)}


def test_missing_set_names_what_was_found():
    with pytest.raises(ValueError) as error:
        node_vectors(DAT, "NOSUCH")
    assert "NOSUCH" in str(error.value) and "TIPC" in str(error.value)  # the set asked for, and a set that is there
    with pytest.raises(ValueError) as error:
        total_force(DAT, "NOPE")
    assert "NOPE" in str(error.value) and "FIX" in str(error.value)
    with pytest.raises(ValueError) as error:  # all the sets found are named, whatever their quantity
        node_vectors(disp_block("TIP", [(1, (0.0, 0.0, 0.0))]) + total_block("FIXED", (0.0, 1.0, 0.0)), "TIPC")
    assert "TIPC" in str(error.value)
    assert "displacements: TIP;" in str(error.value) and "total force: FIXED" in str(error.value)


def test_a_set_of_another_quantity_is_not_found():
    # FIX has a total force, not displacements; TIPC has displacements, not a total force
    with pytest.raises(ValueError, match="FIX"):
        node_vectors(DAT, "FIX")
    with pytest.raises(ValueError, match="TIPC"):
        total_force(DAT, "TIPC")


def test_no_blocks_at_all_names_the_set_and_says_none_were_found():
    with pytest.raises(ValueError) as error:
        node_vectors("", "TIPC")
    assert "TIPC" in str(error.value) and "none" in str(error.value)


def test_malformed_row_is_an_error():
    bad_rows = [
        disp_row(1211, 1.0, 2.0),  # two numbers
        disp_row(1211, 1.0, 2.0, 3.0) + "      4.000000E+00",  # four numbers
        "      1211  1.0  2.0  abc",  # not a number
        "       1.5  1.0  2.0  3.0",  # the node id is not an integer
        "  1.0  2.0  3.0",  # no node id at all
    ]
    for row in bad_rows:
        text = f" displacements (vx,vy,vz) for set TIPC and time {TIME_1}\n\n{row}\n"
        with pytest.raises(ValueError) as error:
            node_vectors(text, "TIPC")
        assert "TIPC" in str(error.value), row
    for row in ["      1.0  2.0", "      1.0  2.0  3.0  4.0", "      1.0  2.0  x", "      7  1.0  2.0  3.0"]:
        text = f" total force (fx,fy,fz) for set FIX and time {TIME_1}\n\n{row}\n"
        with pytest.raises(ValueError) as error:
            total_force(text, "FIX")
        assert "FIX" in str(error.value), row


def test_a_malformed_row_names_the_sets_that_were_found():
    text = disp_block("OTHER", [(1, (0.0, 0.0, 0.0))]) + f" displacements (vx,vy,vz) for set TIPC and time {TIME_1}\n\n  1 2\n"
    with pytest.raises(ValueError) as error:
        node_vectors(text, "TIPC")
    assert "OTHER" in str(error.value)


def test_a_block_without_rows_is_an_error():
    text = f" displacements (vx,vy,vz) for set TIPC and time {TIME_1}\n\n" + total_block("FIX", (0.0, 1.0, 0.0))
    with pytest.raises(ValueError, match="TIPC"):
        node_vectors(text, "TIPC")
    text = f" total force (fx,fy,fz) for set FIX and time {TIME_1}\n\n" + disp_block("TIPC", [(1, (0.0, 0.0, 0.0))])
    with pytest.raises(ValueError, match="FIX"):
        total_force(text, "FIX")


def test_a_total_force_block_has_exactly_one_row():
    text = f" total force (fx,fy,fz) for set FIX and time {TIME_1}\n\n{total_row(0.0, 1.0, 0.0)}\n{total_row(0.0, 2.0, 0.0)}\n"
    with pytest.raises(ValueError, match="FIX"):
        total_force(text, "FIX")


def test_a_repeated_node_is_an_error():
    text = disp_block("TIPC", [(5, (0.0, 1.0, 0.0)), (5, (0.0, 2.0, 0.0))]) + total_block("FIX", (0.0, 1.0, 0.0))
    with pytest.raises(ValueError, match="TIPC") as error:
        node_vectors(text, "TIPC")
    assert "node 5" in str(error.value)
    assert "sets found" in str(error.value) and "displacements: TIPC" in str(error.value) and "total force: FIX" in str(error.value)


def test_rows_are_split_on_whitespace():
    assert total_force(total_block("FIX", (0.0, 21.0, 0.0), indent=4), "FIX") == (0.0, 21.0, 0.0)
    assert total_force(total_block("FIX", (0.0, 21.0, 0.0), indent=0), "FIX") == (0.0, 21.0, 0.0)
    # a displacement row with a different node-id width and tab separators
    text = f" displacements (vx,vy,vz) for set TIPC and time {TIME_1}\n\n12\t1.0E+00\t-2.0E+00   3.0E+00\n"
    assert node_vectors(text, "TIPC") == {12: (1.0, -2.0, 3.0)}


def test_other_blocks_and_text_around_are_ignored():
    stresses = (
        f" stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time {TIME_1}\n\n"
        "         1   1  1.000000E+00  2.000000E+00  3.000000E+00  4.000000E+00  5.000000E+00  6.000000E+00\n"
        "         1   2  1.000000E+00  2.000000E+00  3.000000E+00  4.000000E+00  5.000000E+00  6.000000E+00\n"
    )
    text = "some header\n" + stresses + DAT + "\n" + stresses
    assert node_vectors(text, "TIPC") == {1211: (1.25e-02, -2.499, -3.0e-04)}
    assert total_force(text, "FIX") == (-1.0e-05, 2.1e01, 4.5e-06)


def test_crlf_line_ends_read_the_same():
    assert node_vectors(DAT.replace("\n", "\r\n"), "TIPC") == node_vectors(DAT, "TIPC")
    assert total_force(DAT.replace("\n", "\r\n"), "FIX") == total_force(DAT, "FIX")


def test_a_second_quantity_is_refused():
    with pytest.raises(ValueError, match="stresses"):
        node_vectors(DAT, "TIPC", quantity="stresses")

def realistic_dat(per_node_first: bool = True) -> str:
    """Two increments of one step, as a run with `*NODE PRINT` for TIPC (U) and for FIX (RF, TOTALS=YES) could write them.

    Every blank line holds a single space, there are banner lines of the step and the increment, the per-node forces of FIX
    come with their total (in either order), and the text does not end with a newline.
    """

    def increment(number: int, time: str, uy: float, fy: float) -> str:
        banner = f"\n S T E P       1\n\n I N C R E M E N T {number:5d}\n"
        forces = (
            f"\n forces (fx,fy,fz) for set FIX and time {time}\n\n"
            + "\n".join(disp_row(node, 0.0, fy / 3.0, 0.0) for node in (1, 2, 3))
            + "\n"
        )
        total = total_block("FIX", (0.0, fy, 0.0), time)
        return banner + disp_block("TIPC", [(1211, (1.0e-03, uy, 0.0))], time) + (forces + total if per_node_first else total + forces)

    text = increment(1, TIME_1, -1.25, 10.5) + increment(2, TIME_2, -2.5, 21.0)
    return re.sub(r"(?m)^$", " ", text).rstrip("\n ")


@pytest.mark.parametrize("per_node_first", [True, False])
def test_a_whole_realistic_dat(per_node_first):
    text = realistic_dat(per_node_first)
    assert not text.endswith("\n") and "\n \n" in text and "S T E P" in text and "I N C R E M E N T" in text
    assert [line for line in text.splitlines() if not line] == []  # the blank lines hold one space, never nothing
    assert node_vectors(text, "TIPC") == {1211: (1.0e-03, -2.5, 0.0)}  # the last increment
    assert total_force(text, "FIX") == (0.0, 21.0, 0.0)  # the total, not the per-node forces next to it
    with pytest.raises(ValueError) as error:  # the per-node forces are not displacements
        node_vectors(text, "FIX")
    assert "FIX" in str(error.value) and "displacements: TIPC" in str(error.value)
