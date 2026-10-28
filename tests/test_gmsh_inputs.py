"""The Gmsh geometry and the decks of exercises 02 and 04, checked statically (neither Gmsh nor ccx runs here).

The geometry names the sets that the decks use; the decks and the geometry agree with the reference solutions.
"""

import re

from conftest import stored_bytes

from workshop import beam, layers
from workshop.decklint import includes, lint_deck, parse_deck
from workshop.gmshinp import physical_names

BEAM_GEO = "exercises/02-gmsh-beam/beam.geo"
BEAM_DECK = "exercises/02-gmsh-beam/beam_selfweight.inp"
CABLE_GEO = "exercises/04-cable-section/cable_quarter.geo"
CABLE_DECK = "exercises/04-cable-section/cable_pressure.inp"

_OPTION = re.compile(r"^Mesh\.(\w+)\s*=\s*([^;]+);", re.MULTILINE)
_CONSTANT = re.compile(r"DefineConstant\[\s*(\w+)\s*=\s*\{\s*([^,\s]+)\s*,")


def _text(root, rel: str) -> str:
    """What git stores for `rel`, as text: UTF-8, LF line ends, exactly one newline at the end."""
    text = stored_bytes(root, rel).decode("utf-8")
    assert "\r" not in text, rel
    assert text.endswith("\n") and not text.endswith("\n\n"), rel
    return text


def _options(geo: str) -> dict[str, str]:
    return dict(_OPTION.findall(geo))


def _defaults(geo: str) -> dict[str, float]:
    return {name: float(value) for name, value in _CONSTANT.findall(geo)}


def test_beam_geo_names_the_sets_the_deck_uses(root):
    names = physical_names(_text(root, BEAM_GEO))
    assert names == {"BEAM": 3, "FIXED": 2, "TIP": 2}
    deck = _text(root, BEAM_DECK)
    assert lint_deck(deck, external_sets=names) == []
    assert includes(deck) == ["beam_mesh.inp"]


def test_cable_geo_names_the_sets_the_deck_uses(root):
    names = physical_names(_text(root, CABLE_GEO))
    surfaces = dict.fromkeys(["CORE", "INSULATION", "SHEATH", "ARMOUR", "CABLE"], 2)
    curves = dict.fromkeys(["SYMX", "SYMY", "OUTER"], 1)
    points = dict.fromkeys(["P_CORE", "P_OUTER"], 0)
    assert names == surfaces | curves | points
    deck = _text(root, CABLE_DECK)
    assert lint_deck(deck, external_sets=names) == []
    assert includes(deck) == ["cable_mesh.inp", "cable_pressure_load.inc"]


def test_geo_files_set_the_export_options(root):
    # second-order elements; Gmsh writes only the groups the deck uses (README of the exercises, from GModelIO_INP.cpp)
    assert _options(_text(root, BEAM_GEO)) == {
        "ElementOrder": "2",
        "SaveGroupsOfElements": "-1000",  # physical volumes only: the ELSET BEAM
        "SaveGroupsOfNodes": "-100",  # physical surfaces only: the NSETs FIXED and TIP
    }
    assert _options(_text(root, CABLE_GEO)) == {
        "ElementOrder": "2",
        "SaveGroupsOfElements": "-100",  # physical surfaces: the ELSETs of the four layers and CABLE
        "SaveGroupsOfNodes": "-111",  # points, curves and surfaces: P_CORE, P_OUTER, SYMX, SYMY, OUTER
    }


def test_geo_defaults_match_the_references(root):
    beam_defaults = _defaults(_text(root, BEAM_GEO))
    assert set(beam_defaults) == {"L", "H", "B", "LC"}
    assert (beam_defaults["L"], beam_defaults["H"], beam_defaults["B"]) == (1000.0, 20.0, 20.0)
    reference = beam.Cantilever()  # the beam of exercise 01, which the reference of exercise 02 shares
    assert (reference.length, reference.height, reference.width) == (1000.0, 20.0, 20.0)
    cable_defaults = _defaults(_text(root, CABLE_GEO))
    assert set(cable_defaults) == {"R1", "R2", "R3", "R4", "LC"}
    radii = [cable_defaults[f"R{i}"] for i in (1, 2, 3, 4)]
    assert radii == [layer.outer_radius for layer in layers.CABLE_LAYERS]


def test_cable_materials_match_the_reference_layers(root):
    cards = parse_deck(_text(root, CABLE_DECK))
    elastic: dict[str, tuple[float, float]] = {}  # material name -> (E, nu)
    current = None
    for card in cards:
        if card.keyword == "MATERIAL":
            current = card.params["NAME"]
        elif card.keyword == "ELASTIC":
            assert current is not None and current not in elastic
            ((_, (young, poisson)),) = card.lines
            elastic[current] = (float(young), float(poisson))
    material_of = {card.params["ELSET"]: card.params["MATERIAL"] for card in cards if card.keyword == "SOLID SECTION"}
    assert list(material_of) == [layer.name for layer in layers.CABLE_LAYERS]
    assert len(set(material_of.values())) == len(material_of) == len(elastic)  # one material for each layer
    for layer in layers.CABLE_LAYERS:
        assert elastic[material_of[layer.name]] == (layer.young, layer.poisson), layer.name


def test_beam_deck_material_and_gravity_match_the_beam_constants(root):
    cards = parse_deck(_text(root, BEAM_DECK))

    def data_line(keyword):
        (card,) = [card for card in cards if card.keyword == keyword]
        ((_, fields),) = card.lines
        return fields

    (material,) = [card for card in cards if card.keyword == "MATERIAL"]
    assert tuple(float(value) for value in data_line("ELASTIC")) == (beam.STEEL_E, beam.STEEL_NU)
    assert tuple(float(value) for value in data_line("DENSITY")) == (beam.STEEL_DENSITY,)
    (section,) = [card for card in cards if card.keyword == "SOLID SECTION"]
    assert section.params == {"ELSET": "BEAM", "MATERIAL": material.params["NAME"]}
    target, kind, magnitude, *direction = data_line("DLOAD")  # self-weight of the ELSET BEAM, gravity in -y
    assert (target, kind) == ("BEAM", "GRAV")
    assert float(magnitude) == beam.GRAVITY
    assert [float(value) for value in direction] == [0.0, -1.0, 0.0]
    assert not [card for card in cards if card.keyword == "CLOAD"]  # no other load


SECTION_DECK = """\
*MATERIAL, NAME=STEEL
*ELASTIC
210000., 0.3
*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL
{data}*STEP
*STATIC
*END STEP
"""


def _section_problems(data: str) -> list[str]:
    return lint_deck(SECTION_DECK.format(data=data), external_sets=["EALL"])


def test_solid_section_thickness_line_is_allowed():
    # the plane-strain thickness (manual section 7.118): at most one data line, holding one number
    assert _section_problems("") == []
    assert _section_problems("1.\n") == []
    assert _section_problems("0.5\n") == []
    assert _section_problems("** thickness\n\n1.\n") == []
    assert _section_problems("1.\n2.\n") == [
        "line 6: *SOLID SECTION: these exercises give it at most one data line (the plane-strain thickness, manual §7.118)"
    ]
    assert _section_problems("1., 2.\n") == [
        "line 5: *SOLID SECTION needs 1 number (the plane-strain thickness, manual §7.118), got 2"
    ]
    assert _section_problems("abc\n") == ["line 5: *SOLID SECTION: 'abc' is not a number"]


def test_solid_section_thickness_must_be_positive():
    assert _section_problems("1.D-3\n") == []  # a Fortran exponent is a number too
    for text in ("0.", "-1.", "0.D0", "-0.5E+1"):
        assert _section_problems(f"{text}\n") == [
            f"line 5: *SOLID SECTION: thickness '{text}' must be above 0 (manual §7.118)"
        ]
