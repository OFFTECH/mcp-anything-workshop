"""Multi-layer Lame solution, plane strain (units N, mm, MPa). Checked against exact rational arithmetic done offline."""

import json

import pytest

from workshop import layers
from workshop.compare import load_reference
from workshop.layers import CABLE_LAYERS, CABLE_PRESSURE, Layer, solve_plane_strain


def test_homogeneous_solid_under_pressure():
    # plane strain, solid disc, external pressure p: sigma_r = sigma_theta = -p and u = -(1+nu)(1-2nu) p r / E
    solution = solve_plane_strain([Layer("A", 10.0, 210000.0, 0.3)], 1.0)
    for r in (2.0, 5.0, 10.0):
        assert solution.radial_stress(r) == pytest.approx(-1.0, abs=1e-9)
        assert solution.hoop_stress(r) == pytest.approx(-1.0, abs=1e-9)
    assert solution.radial_displacement(10.0) == pytest.approx(-(1.3 * 0.4) * 10 / 210000)
    assert solution.radial_displacement(0.0) == 0.0  # the centre of a solid core does not move


def test_split_layer_equals_homogeneous():
    one = solve_plane_strain([Layer("A", 10.0, 210000.0, 0.3)], 1.0)
    two = solve_plane_strain([Layer("A", 4.0, 210000.0, 0.3), Layer("B", 10.0, 210000.0, 0.3)], 1.0)
    for r in (4.0, 7.0, 10.0):
        assert two.radial_displacement(r) == pytest.approx(one.radial_displacement(r), rel=1e-12)


def _lame(layer):
    e, nu = layer.young, layer.poisson
    return e * nu / ((1 + nu) * (1 - 2 * nu)), e / (2 * (1 + nu))


def _from_layer(solution, i, r):
    """u and sigma_r from the coefficients of layer i, coded here independently of layers.py."""
    lam, mu = _lame(solution.layers[i])
    return (
        solution.a[i] * r + solution.b[i] / r,
        2 * (lam + mu) * solution.a[i] - 2 * mu * solution.b[i] / r**2,
    )


def test_interface_continuity():
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    for i, radius in enumerate((10.0, 18.0, 20.0)):
        inner_u, inner_s = _from_layer(solution, i, radius)
        outer_u, outer_s = _from_layer(solution, i + 1, radius)
        assert outer_u == pytest.approx(inner_u, rel=1e-9)
        assert outer_s == pytest.approx(inner_s, rel=1e-9)


def test_cable_values():
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    assert solution.radial_displacement(10.0) == pytest.approx(-9.112679587e-05, rel=1e-8)
    assert solution.radial_displacement(18.0) == pytest.approx(-3.895665715e-03, rel=1e-8)
    assert solution.radial_displacement(24.0) == pytest.approx(-3.570570008e-03, rel=1e-8)
    assert solution.radial_stress(10.0) == pytest.approx(-2.3377, rel=1e-4)
    assert solution.radial_stress(18.0) == pytest.approx(-2.1947, rel=1e-4)
    assert solution.radial_stress(20.0) == pytest.approx(-3.7040, rel=1e-4)
    assert solution.radial_stress(24.0) == pytest.approx(-10.0)


def test_cable_layers_and_pressure_are_the_documented_ones():
    assert CABLE_LAYERS == (
        Layer("CORE", 10.0, 110000.0, 0.34),
        Layer("INSULATION", 18.0, 1000.0, 0.45),
        Layer("SHEATH", 20.0, 70000.0, 0.33),
        Layer("ARMOUR", 24.0, 210000.0, 0.30),
    )
    assert CABLE_PRESSURE == 10.0


def test_the_solution_keeps_its_layers_and_one_pair_of_coefficients_per_layer():
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    assert solution.layers == CABLE_LAYERS
    assert len(solution.a) == len(solution.b) == 4
    assert solution.b[0] == 0.0  # a solid core has no 1/r term


def test_hoop_stress_matches_the_equilibrium_relation():
    # radial equilibrium d(r sigma_r)/dr = sigma_theta, checked by a central difference inside the armour
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    r, h = 22.0, 1e-4
    derivative = ((r + h) * solution.radial_stress(r + h) - (r - h) * solution.radial_stress(r - h)) / (2 * h)
    assert solution.hoop_stress(r) == pytest.approx(derivative, rel=1e-6)


def test_layer_at_takes_the_inner_layer_on_an_interface():
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    assert [solution.layer_at(r) for r in (0.0, 5.0, 10.0, 10.5, 18.0, 19.0, 20.0, 22.0, 24.0)] == [0, 0, 0, 1, 1, 2, 2, 3, 3]
    assert solution.layer_at(10.0 * (1 + 1e-13)) == 0  # inside the 1e-12 relative slack
    assert solution.layer_at(24.0 * (1 + 1e-13)) == 3


@pytest.mark.parametrize("r", [-0.001, 24.001, float("nan"), float("inf")])
def test_layer_at_refuses_a_radius_outside_the_cable(r):
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    with pytest.raises(ValueError, match="radius"):
        solution.layer_at(r)
    with pytest.raises(ValueError, match="radius"):
        solution.radial_displacement(r)


@pytest.mark.parametrize(
    "bad_layers",
    [
        (),
        (Layer("A", 10, 1, 0.3), Layer("B", 10, 1, 0.3)),
        (Layer("A", 10, 0, 0.3),),
        (Layer("A", 10, 1, 0.5),),
    ],
)
def test_bad_layers_are_refused(bad_layers):
    with pytest.raises(ValueError):
        solve_plane_strain(bad_layers, 1.0)


@pytest.mark.parametrize(
    "bad_layers, fragment",
    [
        ((), "no layers"),
        ((Layer("A", 10, 1, 0.3), Layer("B", 10, 1, 0.3)), "'B'"),
        ((Layer("A", 10, 1, 0.3), Layer("B", 8, 1, 0.3)), "'B'"),
        ((Layer("A", 0, 1, 0.3),), "'A'"),
        ((Layer("A", 10, 0, 0.3),), "'A'"),
        ((Layer("A", 10, -5, 0.3),), "'A'"),
        ((Layer("A", 10, 1, 0.5),), "'A'"),
        ((Layer("A", 10, 1, -1.0),), "'A'"),
        ((Layer("A", 10, 1, 0.3), Layer("B", 12, 1, 0.75)), "'B'"),
        ((Layer("A", 10, float("nan"), 0.3),), "'A'"),
        ((Layer("A", float("inf"), 1, 0.3),), "'A'"),
    ],
)
def test_the_refusal_names_the_layer(bad_layers, fragment):
    with pytest.raises(ValueError, match=fragment):
        solve_plane_strain(bad_layers, 1.0)


def test_a_negative_poisson_ratio_above_minus_one_is_allowed():
    solution = solve_plane_strain([Layer("A", 10.0, 1000.0, -0.5)], 1.0)
    assert solution.radial_stress(5.0) == pytest.approx(-1.0, abs=1e-9)


def test_a_non_finite_pressure_is_refused():
    with pytest.raises(ValueError, match="pressure"):
        solve_plane_strain(CABLE_LAYERS, float("nan"))


def test_cable_reference_is_in_the_compare_format(tmp_path):
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(layers.cable_reference()), encoding="utf-8")
    ref = load_reference(path)
    assert ref["values"] == {"u_r_core_edge": -9.112679587e-05, "u_r_outer": -0.003570570008}
    assert list(ref["values"]) == ["u_r_core_edge", "u_r_outer"]
    assert ref["tolerance"] == {"rel": 0.02, "abs": 0.0}
    assert "tolerances" not in ref
    assert ref["source"] == (
        "multi-layer Lamé solution, plane strain, bonded layers, external pressure 10 MPa (workshop/layers.py); "
        "TEACHING SIMPLIFICATION; instructor to verify"
    )
    for value in ref["values"].values():
        assert value == float(f"{value:.10g}")
