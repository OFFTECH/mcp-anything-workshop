"""Analytic beam references, recomputed here from the formulas with plain arithmetic (units N, mm, MPa, t/mm^3)."""

import json

import pytest

from workshop import beam
from workshop.compare import compare, load_reference


def test_defaults_are_the_workshop_steel_and_geometry():
    assert (beam.STEEL_E, beam.STEEL_NU, beam.STEEL_DENSITY, beam.GRAVITY) == (210000.0, 0.3, 7.85e-9, 9810.0)
    c = beam.Cantilever()
    assert (c.length, c.height, c.width, c.young, c.poisson, c.tip_load) == (1000.0, 20.0, 20.0, 210000.0, 0.3, 21.0)
    assert (c.n_length, c.n_height, c.n_width) == (40, 2, 2)


def test_second_moment_is_width_times_height_cubed_over_12():
    assert beam.second_moment(20.0, 20.0) == pytest.approx(20 * 20**3 / 12, rel=1e-14)  # 13333.33 mm^4
    assert beam.second_moment(30.0, 10.0) == pytest.approx(10 * 30**3 / 12, rel=1e-14)  # height is the deep side


def test_cantilever_tip_deflection_is_2_5_mm():
    # P L^3 / (3 E I) = 21 * 1e9 / (3 * 210000 * 13333.33) = 21e9 / 8.4e9
    assert beam.tip_deflection(beam.Cantilever()) == pytest.approx(2.5, rel=1e-12)


def test_tip_deflection_follows_load_and_length():
    base = beam.tip_deflection(beam.Cantilever())
    assert beam.tip_deflection(beam.Cantilever(tip_load=42.0)) == pytest.approx(2 * base, rel=1e-12)
    assert beam.tip_deflection(beam.Cantilever(length=2000.0)) == pytest.approx(8 * base, rel=1e-12)
    assert beam.tip_deflection(beam.Cantilever(young=420000.0)) == pytest.approx(base / 2, rel=1e-12)


def test_selfweight_values():
    # q = 7.85e-9 * 9810 * 20 * 20 = 0.0308034 N/mm; delta = q L^4 / (8 E I) with E I = 210000 * 13333.33 N mm^2
    assert beam.selfweight_tip_deflection(1000.0, 20.0, 20.0) == pytest.approx(1.375151786, rel=1e-9)
    assert beam.selfweight_reaction(1000.0, 20.0, 20.0) == pytest.approx(30.8034, rel=1e-12)
    assert beam.selfweight_tip_deflection(500.0, 20.0, 20.0) == pytest.approx(0.08594698661, rel=1e-9)
    assert beam.selfweight_reaction(500.0, 20.0, 20.0) == pytest.approx(15.4017, rel=1e-12)
    assert beam.selfweight_tip_deflection(750.0, 20.0, 20.0) == pytest.approx(0.4351066197, rel=1e-9)
    assert beam.selfweight_tip_deflection(1500.0, 20.0, 20.0) == pytest.approx(6.961705915, rel=1e-9)


def test_selfweight_scales_with_L4_over_H2():
    base = beam.selfweight_tip_deflection(1000.0, 20.0, 20.0)
    assert beam.selfweight_tip_deflection(2000.0, 20.0, 20.0) == pytest.approx(16 * base, rel=1e-12)
    assert beam.selfweight_tip_deflection(1000.0, 40.0, 20.0) == pytest.approx(base / 4, rel=1e-12)
    # the width cancels: weight and stiffness both grow with it
    assert beam.selfweight_tip_deflection(1000.0, 20.0, 40.0) == pytest.approx(base, rel=1e-12)
    # the reaction is the weight: L * height * width
    reaction = beam.selfweight_reaction(1000.0, 20.0, 20.0)
    assert beam.selfweight_reaction(2000.0, 20.0, 20.0) == pytest.approx(2 * reaction, rel=1e-12)
    assert beam.selfweight_reaction(1000.0, 40.0, 20.0) == pytest.approx(2 * reaction, rel=1e-12)


def _write(tmp_path, name, ref):
    path = tmp_path / name
    path.write_text(json.dumps(ref), encoding="utf-8")
    return path


def test_references_use_the_compare_format(tmp_path):
    ref_01 = load_reference(_write(tmp_path, "01.json", beam.cantilever_reference()))
    ref_02 = load_reference(_write(tmp_path, "02.json", beam.selfweight_reference()))
    assert ref_01["values"] == {"tip_displacement_y": -2.5, "support_reaction_y": 21.0}
    assert ref_02["values"] == {"tip_displacement_y": -1.375151786, "support_reaction_y": 30.8034}
    assert list(ref_01["values"]) == ["tip_displacement_y", "support_reaction_y"]  # the order the golden check reports
    for ref in (ref_01, ref_02):
        assert ref["tolerance"] == {"rel": 0.02, "abs": 0.0}
        # the source is shown to the participant in every comparison: a plain statement of the formula and its values,
        # with no instructor note
        assert "Euler-Bernoulli cantilever" in ref["source"]
        for note in ("workshop/", "scripts/", "instructor"):
            assert note not in ref["source"]
    assert ref_01["tolerances"] == {"support_reaction_y": {"rel": 1e-06, "abs": 0.0001}}
    assert ref_02["tolerances"] == {"support_reaction_y": {"rel": 0.01, "abs": 0.0}}  # see the next test


def test_the_self_weight_reaction_tolerance_allows_the_weight_the_fixed_nodes_carry(tmp_path):
    # ccx prints the total force of FIXED: the reaction PLUS the self-weight (*DLOAD GRAV) carried by those nodes
    # themselves (manual section 7.98), about 0.08 % of q*L. Exercise 01's FIX nodes carry no load: its RF is exact.
    one = load_reference(_write(tmp_path, "01.json", beam.cantilever_reference()))
    two = load_reference(_write(tmp_path, "02.json", beam.selfweight_reference()))
    assert two["tolerances"] == {"support_reaction_y": {"rel": 0.01, "abs": 0.0}}
    assert one["tolerances"] == {"support_reaction_y": {"rel": 1e-06, "abs": 0.0001}}
    assert (
        "the printed total force of FIXED also holds the self-weight that the FIXED nodes carry themselves "
        "(CalculiX manual section 7.98), hence the 1 % tolerance on the reaction"
    ) in two["source"]
    assert "tolerance on the reaction" not in one["source"]
    reaction = two["values"]["support_reaction_y"]
    printed = {"tip_displacement_y": two["values"]["tip_displacement_y"], "support_reaction_y": reaction * 1.0008}
    assert all(row.ok for row in compare(printed, two))
    assert not compare(printed, one)[1].ok  # ... which exercise 01's tight tolerance would refuse
    assert not compare({**printed, "support_reaction_y": reaction * 1.02}, two)[1].ok  # 1 % is not "anything goes"
    assert not compare({**printed, "support_reaction_y": reaction * 0.98}, two)[1].ok


def test_sources_state_the_formula_and_the_inputs():
    one = beam.cantilever_reference()["source"]
    for text in ("P*L^3/(3*E*I)", "P = 21", "L = 1000", "E = 210000", "MPa"):
        assert text in one
    two = beam.selfweight_reference()["source"]
    for text in ("q*L^4/(8*E*I)", "L = 1000", "7.85e-09", "9810", "E = 210000"):
        assert text in two


def test_reference_values_are_rounded_to_ten_significant_digits():
    for ref in (beam.cantilever_reference(), beam.selfweight_reference(), beam.selfweight_reference(750.0, 25.0, 15.0)):
        for value in ref["values"].values():
            assert value == float(f"{value:.10g}")


def test_the_reference_follows_the_inputs():
    ref = beam.cantilever_reference(beam.Cantilever(tip_load=42.0))
    assert ref["values"] == {"tip_displacement_y": -5.0, "support_reaction_y": 42.0}
    assert "P = 42" in ref["source"]
    ref = beam.selfweight_reference(length=750.0)
    assert ref["values"]["tip_displacement_y"] == -0.4351066197
    assert ref["values"]["support_reaction_y"] == 23.10255  # 0.0308034 * 750


def test_a_matching_result_passes_the_golden_check_and_a_wrong_sign_fails(tmp_path):
    reference = load_reference(_write(tmp_path, "01.json", beam.cantilever_reference()))
    good = {"tip_displacement_y": -2.51, "support_reaction_y": 21.0}
    assert all(row.ok for row in compare(good, reference))
    assert not compare({"tip_displacement_y": 2.5, "support_reaction_y": 21.0}, reference)[0].ok  # load is in -y
    assert not compare({"tip_displacement_y": -2.5, "support_reaction_y": 20.9}, reference)[1].ok  # reaction is tight
