"""The deck linter: `parse_deck`, the rules of `lint_deck`, and `includes`, on small decks of our own."""

import re

import pytest
from conftest import stored_bytes

from workshop.decklint import KEYWORDS, NODES_PER_ELEMENT, STEP_ONLY, Card, includes, lint_deck, parse_deck

DECK_01 = "exercises/01-cantilever/cantilever.inp"
BROKEN_01 = "exercises/01-cantilever/broken/bad_modulus.inp"

# One ten-node tetrahedron (corner nodes 1-4, then the midside nodes of edges 1-2, 2-3, 3-1, 1-4, 2-4, 3-4).
CLEAN = """\
** Linter test deck: one C3D10 element, fixed at z = 0, pulled at its apex.
*HEADING
One C3D10 element
*NODE, NSET=NALL
1, 0., 0., 0.
2, 1., 0., 0.
3, 0., 1., 0.
4, 0., 0., 1.
5, 0.5, 0., 0.
6, 0.5, 0.5, 0.
7, 0., 0.5, 0.
8, 0., 0., 0.5
9, 0.5, 0., 0.5
10, 0., 0.5, 0.5
*ELEMENT, TYPE=C3D10, ELSET=EALL
1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
*NSET, NSET=BASE
1, 2, 3, 5, 6, 7
*NSET, NSET=APEX
4
*MATERIAL, NAME=STEEL
*ELASTIC
210000., 0.3
*DENSITY
7.85E-9
*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL
*STEP
*STATIC
*BOUNDARY
BASE, 1, 3
*CLOAD
APEX, 2, -1.
*DLOAD
EALL, GRAV, 9810., 0., -1., 0.
*NODE PRINT, NSET=APEX
U
*NODE FILE
U
*EL FILE
S
*END STEP
"""
ELEMENT_C3D10 = "*ELEMENT, TYPE=C3D10, ELSET=EALL\n1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10\n"


def _with(old: str, new: str, text: str = CLEAN) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _line_of(text: str, line: str, start: int = 0) -> int:
    """1-based number of the first line equal to `line` after line `start`."""
    return text.split("\n").index(line, start) + 1


def _c3d20r(*lines: str) -> str:
    return _with(ELEMENT_C3D10, "*ELEMENT, TYPE=C3D20R, ELSET=EALL\n" + "".join(f"{line}\n" for line in lines))


def test_the_clean_deck_is_clean():
    assert lint_deck(CLEAN) == []


def test_exercise_01_deck_is_clean(root):
    assert lint_deck(stored_bytes(root, DECK_01).decode("utf-8")) == []


def test_broken_deck_shows_exactly_the_bad_number(root):
    text = stored_bytes(root, BROKEN_01).decode("utf-8")
    problems = lint_deck(text)
    assert len(problems) == 1
    assert "*ELASTIC" in problems[0] and "'abc'" in problems[0]
    assert problems[0] == f"line {_line_of(text, 'abc, 0.3')}: *ELASTIC: 'abc' is not a number"


def test_lines_longer_than_132_are_reported():
    assert lint_deck(_with("** Linter test deck", "*" * 132 + "\n** Linter test deck")) == []  # 132 is fine
    long_comment = "** " + "x" * 130
    problems = lint_deck(_with("*HEADING\n", "*HEADING\n" + long_comment + "\n"))
    assert problems == [f"line {_line_of(CLEAN, '*HEADING') + 1}: 133 bytes, longer than 132 (manual §5.1)"]


def test_line_length_counts_bytes_as_ccx_does():
    comment = "** density in t/mm³ " + "x" * 111  # 131 characters, 132 bytes: fine
    assert lint_deck(_with("*HEADING\n", "*HEADING\n" + comment + "\n")) == []
    comment = "** density in t/mm³³ " + "x" * 110  # 131 characters, 133 bytes
    problems = lint_deck(_with("*HEADING\n", "*HEADING\n" + comment + "\n"))
    assert problems == [f"line {_line_of(CLEAN, '*HEADING') + 1}: 133 bytes, longer than 132 (manual §5.1)"]


def test_unknown_keyword_is_reported():
    text = _with("*STATIC\n", "*STATICS\n")
    assert lint_deck(text) == [f"line {_line_of(text, '*STATICS')}: unknown keyword *STATICS"]


def test_undefined_set_is_reported_and_external_sets_count():
    text = _with("BASE, 1, 3", "NOPE, 1, 3")
    assert lint_deck(text) == [f"line {_line_of(text, 'NOPE, 1, 3')}: undefined set NOPE"]
    assert lint_deck(text, external_sets={"nope"}) == []  # compared case-insensitively
    assert lint_deck(_with("BASE, 1, 3", "base, 1, 3")) == []
    assert lint_deck(_with("BASE, 1, 3", "7, 1, 3")) == []  # a node id is a target too


def test_set_references_in_parameters_and_load_lines():
    text = _with("*NODE PRINT, NSET=APEX", "*NODE PRINT, NSET=TOP")
    assert lint_deck(text) == [f"line {_line_of(text, '*NODE PRINT, NSET=TOP')}: undefined set TOP"]
    text = _with("ELSET=EALL, MATERIAL", "ELSET=SOLID, MATERIAL")
    assert lint_deck(text) == [f"line {_line_of(text, '*SOLID SECTION, ELSET=SOLID, MATERIAL=STEEL')}: undefined set SOLID"]
    text = _with("APEX, 2, -1.", "TOP, 2, -1.")
    assert lint_deck(text) == [f"line {_line_of(text, 'TOP, 2, -1.')}: undefined set TOP"]
    text = _with("EALL, GRAV", "BODY, GRAV")
    assert lint_deck(text) == [f"line {_line_of(text, 'BODY, GRAV, 9810., 0., -1., 0.')}: undefined set BODY"]
    assert lint_deck(text, external_sets=("Body",)) == []
    # sets defined by *ELSET and by *ELEMENT ELSET= / *NODE NSET= all count
    text = _with("*NSET, NSET=APEX\n", "*ELSET, ELSET=BODY\n1\n*NSET, NSET=APEX\n", _with("EALL, GRAV", "BODY, GRAV"))
    assert lint_deck(text) == []
    assert lint_deck(_with("BASE, 1, 3", "NALL, 1, 3")) == []
    text = _with("*NODE PRINT, NSET=APEX", "*NODE PRINT")
    assert lint_deck(text) == [f"line {_line_of(text, '*NODE PRINT')}: *NODE PRINT needs NSET="]


def test_solid_section_material_must_be_defined():
    text = _with("MATERIAL=STEEL\n", "MATERIAL=ALU\n")
    assert lint_deck(text) == [f"line {_line_of(text, '*SOLID SECTION, ELSET=EALL, MATERIAL=ALU')}: undefined material ALU"]
    assert lint_deck(_with("MATERIAL=STEEL\n", "MATERIAL=steel\n")) == []
    text = _with(", MATERIAL=STEEL\n", "\n")
    assert lint_deck(text) == [f"line {_line_of(text, '*SOLID SECTION, ELSET=EALL')}: *SOLID SECTION needs MATERIAL="]


def test_element_record_with_a_continuation_line():
    two_lines = ("1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,", "16, 17, 18, 19, 20")
    assert lint_deck(_c3d20r(*two_lines)) == []
    text = _c3d20r("1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,", "17, 18, 19, 20")
    problems = lint_deck(text)
    assert len(problems) == 1 and "16 entries" in problems[0]
    assert problems[0].startswith(f"line {_line_of(text, '*ELEMENT, TYPE=C3D20R, ELSET=EALL') + 1}:")


def test_element_records_need_the_id_and_all_nodes():
    text = _c3d20r("1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,", "16, 17, 18, 19")
    record = _line_of(text, "*ELEMENT, TYPE=C3D20R, ELSET=EALL") + 1
    assert lint_deck(text) == [f"line {record}: *ELEMENT record has 20 entries, TYPE=C3D20R needs 21 (id and 20 nodes)"]
    text = _c3d20r("1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,", "16, 17, 18, 19, 20, 21")
    assert lint_deck(text) == [f"line {record}: *ELEMENT record has 22 entries, TYPE=C3D20R needs 21 (id and 20 nodes)"]
    text = _with("1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10\n", "1, 1, 2, 3, 4, 5, 6, 7, 8, 9, x\n")
    assert lint_deck(text) == [f"line {record}: *ELEMENT: 'x' is not an integer"]
    text = _with("TYPE=C3D10", "TYPE=C3D8")
    assert lint_deck(text) == [f"line {record - 1}: *ELEMENT TYPE=C3D8 is not one of C3D20R, C3D20, C3D10, CPE6"]
    text = _with("*ELEMENT, TYPE=C3D10, ELSET=EALL", "*ELEMENT, ELSET=EALL")
    assert lint_deck(text) == [f"line {record - 1}: *ELEMENT needs TYPE=, one of C3D20R, C3D20, C3D10, CPE6"]
    assert lint_deck(_with("TYPE=C3D10", "type = c3d10")) == []


def test_node_lines_need_an_id_and_three_numbers():
    text = _with("2, 1., 0., 0.", "2, 1., 0.")
    assert lint_deck(text) == [f"line {_line_of(text, '2, 1., 0.')}: *NODE needs 4 fields (id, x, y, z), got 3"]
    text = _with("2, 1., 0., 0.", "2, 1., zero, 1.D0")
    assert lint_deck(text) == [f"line {_line_of(text, '2, 1., zero, 1.D0')}: *NODE: 'zero' is not a number"]
    text = _with("2, 1., 0., 0.", "B, 1., 0., 0.")
    assert lint_deck(text) == [f"line {_line_of(text, 'B, 1., 0., 0.')}: *NODE: 'B' is not an integer id"]
    assert lint_deck(_with("2, 1., 0., 0.", "2, 1.E+00, -.0, +0")) == []


def test_set_cards_need_their_name_and_short_lines():
    text = _with("*NSET, NSET=APEX", "*NSET")
    assert lint_deck(text) == [
        f"line {_line_of(text, '*NSET')}: *NSET needs NSET=",
        f"line {_line_of(text, 'APEX, 2, -1.')}: undefined set APEX",
        f"line {_line_of(text, '*NODE PRINT, NSET=APEX')}: undefined set APEX",
    ]
    text = _with("*NSET, NSET=APEX\n", "*ELSET\n1\n*NSET, NSET=APEX\n")
    assert lint_deck(text) == [f"line {_line_of(text, '*ELSET')}: *ELSET needs ELSET="]
    seventeen = ", ".join(["1"] * 17)
    text = _with("1, 2, 3, 5, 6, 7", seventeen)
    assert lint_deck(text) == [f"line {_line_of(text, seventeen)}: *NSET line has 17 entries, at most 16 entries per line (manual §7.100)"]
    text = _with("1, 2, 3, 5, 6, 7", "1, 2, NALL, ELSEWHERE")
    assert lint_deck(text) == [f"line {_line_of(text, '1, 2, NALL, ELSEWHERE')}: undefined set ELSEWHERE"]


def test_material_constants():
    text = _with("210000., 0.3", "210000.")
    assert lint_deck(text) == [f"line {_line_of(text, '210000.')}: *ELASTIC needs 2 numbers, got 1"]
    text = _with("210000., 0.3\n", "210000., 0.3\n210000., 0.3\n")
    assert lint_deck(text) == [f"line {_line_of(text, '*ELASTIC')}: *ELASTIC needs one data line, got 2"]
    text = _with("210000., 0.3\n", "")
    assert lint_deck(text) == [f"line {_line_of(text, '*ELASTIC')}: *ELASTIC needs one data line, got 0"]
    text = _with("7.85E-9", "7.85E-9, 0.")
    assert lint_deck(text) == [f"line {_line_of(text, '7.85E-9, 0.')}: *DENSITY needs 1 number, got 2"]
    text = _with("7.85E-9", "heavy")
    assert lint_deck(text) == [f"line {_line_of(text, 'heavy')}: *DENSITY: 'heavy' is not a number"]


def test_load_and_boundary_fields():
    assert lint_deck(_with("BASE, 1, 3", "BASE, 1")) == []
    assert lint_deck(_with("BASE, 1, 3", "BASE, 1, 3, 0.5")) == []
    text = _with("BASE, 1, 3", "BASE")
    assert lint_deck(text) == [f"line {_line_of(text, 'BASE', 20)}: *BOUNDARY needs 2 to 4 fields, got 1"]
    text = _with("BASE, 1, 3", "BASE, 1, 3, 0., 1.")
    assert lint_deck(text) == [f"line {_line_of(text, 'BASE, 1, 3, 0., 1.')}: *BOUNDARY needs 2 to 4 fields, got 5"]
    text = _with("BASE, 1, 3", "BASE, 1, 0.5")
    assert lint_deck(text) == [f"line {_line_of(text, 'BASE, 1, 0.5')}: *BOUNDARY: '0.5' is not an integer degree of freedom"]
    text = _with("BASE, 1, 3", "BASE, 1, 3, free")
    assert lint_deck(text) == [f"line {_line_of(text, 'BASE, 1, 3, free')}: *BOUNDARY: 'free' is not a number"]
    text = _with("APEX, 2, -1.", "APEX, 2")
    assert lint_deck(text) == [f"line {_line_of(text, 'APEX, 2')}: *CLOAD needs 3 fields, got 2"]
    text = _with("APEX, 2, -1.", "APEX, y, -1.")
    assert lint_deck(text) == [f"line {_line_of(text, 'APEX, y, -1.')}: *CLOAD: 'y' is not an integer degree of freedom"]
    text = _with("APEX, 2, -1.", "APEX, 2, -1 N")
    assert lint_deck(text) == [f"line {_line_of(text, 'APEX, 2, -1 N')}: *CLOAD: '-1 N' is not a number"]


def test_step_structure():
    text = _with("*STEP\n", "", _with("*SOLID SECTION", "*CLOAD\nAPEX, 2, -1.\n*SOLID SECTION"))
    problems = lint_deck(text)
    assert f"line {_line_of(text, '*CLOAD')}: *CLOAD outside *STEP ... *END STEP" in problems
    assert "no *STEP (a deck needs exactly one)" in problems
    text = _with("*SOLID SECTION", "*CLOAD\nAPEX, 2, -1.\n*SOLID SECTION")
    assert lint_deck(text) == [f"line {_line_of(text, '*CLOAD')}: *CLOAD outside *STEP ... *END STEP"]
    text = CLEAN + "*STEP\n*STATIC\n*END STEP\n"
    second_step = _line_of(text, "*STEP", _line_of(text, "*STEP"))
    assert lint_deck(text) == [
        f"line {second_step}: another *STEP (a deck needs exactly one)",
        f"line {second_step + 2}: another *END STEP (a deck needs exactly one)",
    ]
    text = _with("*END STEP\n", "")
    assert lint_deck(text) == ["no *END STEP (a deck needs exactly one)"]
    text = _with("*STEP\n", "*END STEP\n*STEP\n", _with("*END STEP\n", ""))
    problems = lint_deck(text)
    assert f"line {_line_of(text, '*END STEP')}: *END STEP before *STEP" in problems
    for keyword in STEP_ONLY:
        assert keyword in KEYWORDS


def test_data_lines_only_where_allowed():
    text = _with("*STATIC\n", "*STATIC\n0.1, 1.\n")
    assert lint_deck(text) == [f"line {_line_of(text, '0.1, 1.')}: *STATIC: these exercises give it no data lines"]
    text = _with("*MATERIAL, NAME=STEEL\n", "*MATERIAL, NAME=STEEL\nsteel\n")
    assert lint_deck(text) == [f"line {_line_of(text, 'steel')}: *MATERIAL: these exercises give it no data lines"]
    assert lint_deck(_with("One C3D10 element", "One C3D10 element, any text: 1 2 3")) == []


def test_every_keyword_cites_a_manual_section():
    assert len(KEYWORDS) == 19
    for keyword, section in KEYWORDS.items():
        assert re.fullmatch(r"§\d+(\.\d+)*", section), keyword
        assert keyword == " ".join(keyword.split()).upper()
    assert (KEYWORDS["ELEMENT"], KEYWORDS["NODE PRINT"], KEYWORDS["INCLUDE"]) == ("§7.49", "§7.98", "§7.75")
    assert NODES_PER_ELEMENT == {"C3D20R": 20, "C3D20": 20, "C3D10": 10, "CPE6": 6}


def test_includes_are_listed():
    text = "*HEADING\nmain deck\n*INCLUDE, INPUT=beam_mesh.inp\n*include ,input = Loads.inc\n*NODE\n1, 0., 0., 0.\n"
    assert includes(text) == ["beam_mesh.inp", "Loads.inc"]
    assert includes(CLEAN) == []
    assert lint_deck(_with("*MATERIAL", "*INCLUDE, INPUT=extra.inp\n*MATERIAL")) == []


def test_parse_deck_reads_cards_comments_and_data():
    text = "** comment\n*Node Print,  nset = Tip ,totals=ONLY,\nU, RF,\n\n  **indented comment\n*end   step\n"
    assert parse_deck(text) == [
        Card(keyword="NODE PRINT", params={"NSET": "Tip", "TOTALS": "ONLY"}, lines=((3, ("U", "RF")),), line_no=2),
        Card(keyword="END STEP", params={}, lines=(), line_no=6),
    ]
    (card,) = parse_deck("*ELEMENT, TYPE=C3D20R\n1, 2,,\n *NSET , GENERATE\n")[:1]
    assert card.lines == ((2, ("1", "2", "")),)  # only one trailing empty field is dropped
    assert parse_deck("*STATIC\r\n*END STEP\r\n")[1] == Card("END STEP", {}, (), 2)


def test_data_before_the_first_keyword_is_an_error():
    with pytest.raises(ValueError, match="line 2"):
        parse_deck("** comment\n1, 0., 0., 0.\n*NODE\n")
    assert lint_deck("** comment\n1, 0., 0., 0.\n" + CLEAN) == ["line 2: data line before the first keyword"]
