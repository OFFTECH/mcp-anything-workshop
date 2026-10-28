"""Multi-layer Lamé solution of a round cable cross-section in plane strain: the analytic reference of exercise 04.

Standard library only. Units: N, mm, MPa (= N/mm^2). Radii are in mm, moduli in MPa, the pressure in MPa, the radial
displacement in mm and the stresses in MPa; a compressive stress is negative.

TEACHING SIMPLIFICATION. The cross-section is a set of concentric, homogeneous, linear-elastic layers, bonded at their
interfaces, under a uniform external pressure and in plane strain (no strain along the cable axis). A real cable is
stranded, not axisymmetric, and does not behave like this; the model exists to give the exercise a reference to compare
with.

Theory. In a layer with Lamé constants lambda = E*nu / ((1 + nu) * (1 - 2*nu)) and mu = E / (2 * (1 + nu)) the
axisymmetric plane-strain field is, with two constants a and b per layer::

    u       = a*r + b/r
    sigma_r = 2*(lambda + mu)*a - 2*mu*b/r^2
    sigma_t = 2*(lambda + mu)*a + 2*mu*b/r^2

(`sigma_t` is the hoop stress.) The core is solid, so its b is 0. At every interface the displacement u and the radial
stress sigma_r are continuous, and at the outer radius sigma_r = -pressure. That is 2*n - 1 linear equations for the
2*n - 1 unknowns of n layers, solved by Gaussian elimination with partial pivoting.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Layer:
    """One homogeneous layer: it reaches from the previous layer's outer radius to `outer_radius` (mm)."""

    name: str
    outer_radius: float  # mm
    young: float  # MPa
    poisson: float


def _lame(layer: Layer) -> tuple[float, float]:
    """(lambda, mu) of a layer for plane strain, in MPa."""
    e, nu = layer.young, layer.poisson
    return e * nu / ((1.0 + nu) * (1.0 - 2.0 * nu)), e / (2.0 * (1.0 + nu))


_RADIUS_SLACK = 1e-12  # relative slack of `layer_at`, so that a radius computed on an interface still finds its layer


@dataclass(frozen=True)
class Solution:
    """The solved field: layer i has u = a[i]*r + b[i]/r (b[0] is 0). Radii in mm, stresses in MPa, u in mm."""

    layers: tuple[Layer, ...]
    a: tuple[float, ...]
    b: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.layers or not len(self.layers) == len(self.a) == len(self.b):
            raise ValueError("a solution needs one pair of coefficients (a, b) for each of its layers")

    def layer_at(self, r: float) -> int:
        """Index of the first layer with r <= outer_radius * (1 + 1e-12): a radius on an interface is in the inner layer.

        Raises ValueError for a radius below 0, above the last layer's outer radius, or not a number.
        """
        if r >= 0:
            for i, layer in enumerate(self.layers):
                if r <= layer.outer_radius * (1.0 + _RADIUS_SLACK):
                    return i
        raise ValueError(f"radius {r!r} is outside the cable (0 to {self.layers[-1].outer_radius:g} mm)")

    def _field(self, r: float) -> tuple[float, float, float]:
        """(u, sigma_r, sigma_t) at radius r, from the layer that `layer_at` picks."""
        i = self.layer_at(r)
        lam, mu = _lame(self.layers[i])
        a, b = self.a[i], self.b[i]
        b_over_r = b / r if b != 0.0 else 0.0  # the solid core has b = 0, which keeps r = 0 usable
        b_over_r2 = b_over_r / r if b != 0.0 else 0.0
        stretch = 2.0 * (lam + mu) * a
        return a * r + b_over_r, stretch - 2.0 * mu * b_over_r2, stretch + 2.0 * mu * b_over_r2

    def radial_displacement(self, r: float) -> float:
        """Radial displacement u(r) in mm (negative: towards the axis)."""
        return self._field(r)[0]

    def radial_stress(self, r: float) -> float:
        """Radial stress sigma_r(r) in MPa."""
        return self._field(r)[1]

    def hoop_stress(self, r: float) -> float:
        """Hoop (circumferential) stress sigma_t(r) in MPa."""
        return self._field(r)[2]


def _validate(layers: Sequence[Layer], pressure: float) -> None:
    if not layers:
        raise ValueError("no layers: a cable needs at least a core")
    if not math.isfinite(pressure):
        raise ValueError(f"pressure must be a finite number, got {pressure!r}")
    previous = 0.0
    for layer in layers:
        label = f"layer {layer.name!r}"
        if not math.isfinite(layer.outer_radius) or layer.outer_radius <= previous:
            raise ValueError(f"{label}: outer_radius must be a finite number above {previous:g}, got {layer.outer_radius!r}")
        if not math.isfinite(layer.young) or layer.young <= 0:
            raise ValueError(f"{label}: young must be a finite number > 0, got {layer.young!r}")
        if not math.isfinite(layer.poisson) or not -1.0 < layer.poisson < 0.5:
            raise ValueError(f"{label}: poisson must be above -1 and below 0.5, got {layer.poisson!r}")
        previous = layer.outer_radius


def _gauss(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve matrix * x = rhs by Gaussian elimination with partial pivoting, after scaling every row and column to a
    largest entry of 1 (the stiffnesses of the layers differ by orders of magnitude). Raises ValueError if singular."""
    n = len(rhs)
    rows = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for row in rows:
        scale = max(abs(x) for x in row[:n])
        if scale == 0.0:
            raise ValueError("the layer equations are singular")
        row[:] = [x / scale for x in row]
    column_scale = [max(abs(rows[i][j]) for i in range(n)) or 1.0 for j in range(n)]
    for row in rows:
        for j in range(n):
            row[j] /= column_scale[j]
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(rows[i][col]))
        if abs(rows[pivot][col]) < 1e-13:
            raise ValueError("the layer equations are singular")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for i in range(col + 1, n):
            factor = rows[i][col] / rows[col][col]
            if factor:
                rows[i] = [x - factor * y for x, y in zip(rows[i], rows[col])]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (rows[i][n] - sum(rows[i][j] * x[j] for j in range(i + 1, n))) / rows[i][i]
    return [x[j] / column_scale[j] for j in range(n)]


def solve_plane_strain(layers: Sequence[Layer], pressure: float) -> Solution:
    """Solve the bonded multi-layer cylinder under the external `pressure` (MPa, positive = compression) in plane strain.

    Raises ValueError for no layers, outer radii that do not increase (the first must be above 0), a Young's modulus
    <= 0, a Poisson's ratio outside (-1, 0.5), or a pressure that is not finite.
    """
    layers = tuple(layers)
    _validate(layers, pressure)
    n = len(layers)
    size = 2 * n - 1  # unknowns: a0, then (a_i, b_i) for i >= 1

    def a_col(i: int) -> int:
        return 0 if i == 0 else 2 * i - 1

    def b_col(i: int) -> int | None:  # the core has no b
        return None if i == 0 else 2 * i

    def stress_row(i: int, r: float, sign: float, row: list[float]) -> None:
        """Add sign * sigma_r(r) of layer i to the equation row."""
        lam, mu = _lame(layers[i])
        row[a_col(i)] += sign * 2.0 * (lam + mu)
        if (j := b_col(i)) is not None:
            row[j] -= sign * 2.0 * mu / r**2

    def displacement_row(i: int, r: float, sign: float, row: list[float]) -> None:
        """Add sign * u(r) of layer i to the equation row."""
        row[a_col(i)] += sign * r
        if (j := b_col(i)) is not None:
            row[j] += sign / r

    matrix: list[list[float]] = []
    rhs: list[float] = []
    for i in range(n - 1):  # continuity of u and sigma_r between layer i and layer i + 1
        r = float(layers[i].outer_radius)
        row = [0.0] * size
        displacement_row(i, r, 1.0, row)
        displacement_row(i + 1, r, -1.0, row)
        matrix.append(row)
        rhs.append(0.0)
        row = [0.0] * size
        stress_row(i, r, 1.0, row)
        stress_row(i + 1, r, -1.0, row)
        matrix.append(row)
        rhs.append(0.0)
    row = [0.0] * size  # sigma_r = -pressure on the outside
    stress_row(n - 1, float(layers[-1].outer_radius), 1.0, row)
    matrix.append(row)
    rhs.append(-float(pressure))

    x = _gauss(matrix, rhs)
    a = tuple(x[a_col(i)] for i in range(n))
    b = tuple(0.0 if (j := b_col(i)) is None else x[j] for i in range(n))
    return Solution(layers, a, b)


CABLE_LAYERS = (
    Layer("CORE", 10.0, 110000.0, 0.34),
    Layer("INSULATION", 18.0, 1000.0, 0.45),
    Layer("SHEATH", 20.0, 70000.0, 0.33),
    Layer("ARMOUR", 24.0, 210000.0, 0.30),
)
CABLE_PRESSURE = 10.0  # MPa, external; about 1000 m of water: an illustrative load


def cable_reference() -> dict:
    """Reference of exercise 04 in the compare format (`workshop/compare.py`): radial displacements in mm, at the
    edge of the core (r = 10 mm) and at the outside (r = 24 mm), for the four-layer cable under 10 MPa."""
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    return {
        "source": (
            "multi-layer Lamé solution, plane strain, bonded layers, external pressure 10 MPa (workshop/layers.py); "
            "TEACHING SIMPLIFICATION; instructor to verify"
        ),
        "values": {
            "u_r_core_edge": float(f"{solution.radial_displacement(CABLE_LAYERS[0].outer_radius):.10g}"),
            "u_r_outer": float(f"{solution.radial_displacement(CABLE_LAYERS[-1].outer_radius):.10g}"),
        },
        "tolerance": {"rel": 0.02, "abs": 0.0},
    }
