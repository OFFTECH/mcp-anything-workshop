"""Beam theory for the workshop's cantilever: the analytic references of exercises 01 and 02, and the exercise 01 mesh
and deck. Standard library only.

Units everywhere: N, mm, MPa (= N/mm^2), t (tonne), s. So a length is in mm, a force in N, a stress or modulus in MPa,
a mass density in t/mm^3 (= N s^2/mm^4) and the acceleration of gravity in mm/s^2.

The beam is a prism along x, fixed at x = 0. Its height is along y, its width along z, and loads act in -y, so the tip
moves in -y (negative `tip_displacement_y`) while the support pushes back in +y (positive `support_reaction_y`).
The Euler-Bernoulli theory used here neglects shear deformation; at length/height = 50 that is far below the 2 %
tolerance of the references.
"""

from dataclasses import dataclass

STEEL_E = 210000.0  # Young's modulus, MPa
STEEL_NU = 0.3  # Poisson's ratio
STEEL_DENSITY = 7.85e-9  # t/mm^3 (= N s^2/mm^4), the density of steel, 7850 kg/m^3
GRAVITY = 9810.0  # mm/s^2

_DIGITS = 10  # significant digits of the values written to the reference files


@dataclass(frozen=True)
class Cantilever:
    """The exercise 01 beam: dimensions in mm, `young` in MPa, `tip_load` in N (acting in -y), and the mesh divisions."""

    length: float = 1000.0
    height: float = 20.0  # along y
    width: float = 20.0  # along z
    young: float = STEEL_E
    poisson: float = STEEL_NU
    tip_load: float = 21.0
    n_length: int = 40
    n_height: int = 2
    n_width: int = 2


def second_moment(height: float, width: float) -> float:
    """Second moment of area I = width * height^3 / 12 of a rectangle bending about z, in mm^4 (height along y)."""
    return width * height**3 / 12.0


def tip_deflection(c: Cantilever) -> float:
    """Tip deflection P * L^3 / (3 * E * I) of a cantilever under the tip load P, in mm. Positive (the load is in -y)."""
    return c.tip_load * c.length**3 / (3.0 * c.young * second_moment(c.height, c.width))


def _selfweight_load(height: float, width: float, density: float, gravity: float) -> float:
    """Self-weight per unit length q = density * gravity * width * height, in N/mm."""
    return density * gravity * width * height


def selfweight_tip_deflection(
    length: float,
    height: float,
    width: float,
    young: float = STEEL_E,
    density: float = STEEL_DENSITY,
    gravity: float = GRAVITY,
) -> float:
    """Tip deflection q * L^4 / (8 * E * I) of a cantilever under its own weight, in mm. Positive (gravity is in -y)."""
    q = _selfweight_load(height, width, density, gravity)
    return q * length**4 / (8.0 * young * second_moment(height, width))


def selfweight_reaction(
    length: float, height: float, width: float, density: float = STEEL_DENSITY, gravity: float = GRAVITY
) -> float:
    """Support reaction q * L of a cantilever under its own weight, in N: the whole weight, acting in +y."""
    return _selfweight_load(height, width, density, gravity) * length


def _rounded(value: float) -> float:
    return float(f"{value:.{_DIGITS}g}")


def _plain(value: float) -> str:
    """A number as short text for a `source` string: 21.0 -> '21', 7.85e-09 -> '7.85e-09'."""
    return f"{value:.{_DIGITS}g}"


def cantilever_reference(c: Cantilever = Cantilever()) -> dict:
    """Reference of exercise 01 in the compare format (`workshop/compare.py`). Displacement in mm, reaction in N."""
    source = (
        "Euler-Bernoulli cantilever under a tip load: tip deflection = P*L^3/(3*E*I) with I = w*h^3/12, "
        f"support reaction = P (P = {_plain(c.tip_load)} N in -y, L = {_plain(c.length)} mm, "
        f"h = {_plain(c.height)} mm, w = {_plain(c.width)} mm, E = {_plain(c.young)} MPa)"
    )
    return {
        "source": source,
        "values": {
            "tip_displacement_y": _rounded(-tip_deflection(c)),
            "support_reaction_y": _rounded(c.tip_load),
        },
        "tolerance": {"rel": 0.02, "abs": 0.0},
        "tolerances": {"support_reaction_y": {"rel": 1e-06, "abs": 0.0001}},
    }


def selfweight_reference(length: float = 1000.0, height: float = 20.0, width: float = 20.0) -> dict:
    """Reference of exercise 02 in the compare format: steel cantilever under its own weight. Displacement in mm,
    reaction in N."""
    source = (
        "Euler-Bernoulli cantilever under its own weight: tip deflection = q*L^4/(8*E*I) with q = density*g*w*h and "
        "I = w*h^3/12, support reaction = q*L "
        f"(L = {_plain(length)} mm, h = {_plain(height)} mm, w = {_plain(width)} mm, E = {_plain(STEEL_E)} MPa, "
        f"density = {_plain(STEEL_DENSITY)} t/mm^3, g = {_plain(GRAVITY)} mm/s^2 acting in -y); "
        "the printed total force of FIXED also holds the self-weight that the FIXED nodes carry themselves "
        "(CalculiX manual section 7.98), hence the 1 % tolerance on the reaction"
    )
    return {
        "source": source,
        "values": {
            "tip_displacement_y": _rounded(-selfweight_tip_deflection(length, height, width)),
            "support_reaction_y": _rounded(selfweight_reaction(length, height, width)),
        },
        "tolerance": {"rel": 0.02, "abs": 0.0},
        "tolerances": {"support_reaction_y": {"rel": 0.01, "abs": 0.0}},
    }


# The exercise 01 mesh and deck: C3D20R bricks, 20 nodes each (manual §6.2.5; node order of §6.2.4, Figure 60).


@dataclass(frozen=True)
class BrickMesh:
    """A mesh of 20-node bricks. `nodes` maps id -> (x, y, z) in mm, `elements` maps id -> the 20 node ids in C3D20R
    order; `fixed` holds the nodes at x = 0, `tip` those at x = length, and `tip_center` the node at the middle of the
    tip face."""

    nodes: dict[int, tuple[float, float, float]]
    elements: dict[int, tuple[int, ...]]
    fixed: tuple[int, ...]
    tip: tuple[int, ...]
    tip_center: int


# The 20 nodes of a brick as offsets (di, dj, dk) on the half-step grid from its first corner: corners 1-4 on the face
# k = 0 and 5-8 on k = 2, then the midside nodes of edges 1-2, 2-3, 3-4, 4-1 (9-12), 5-6, 6-7, 7-8, 8-5 (13-16) and
# 1-5, 2-6, 3-7, 4-8 (17-20).
_C3D20R_OFFSETS = (
    (0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
    (0, 0, 2), (2, 0, 2), (2, 2, 2), (0, 2, 2),
    (1, 0, 0), (2, 1, 0), (1, 2, 0), (0, 1, 0),
    (1, 0, 2), (2, 1, 2), (1, 2, 2), (0, 1, 2),
    (0, 0, 1), (2, 0, 1), (2, 2, 1), (0, 2, 1),
)  # fmt: skip


def c3d20r_mesh(c: Cantilever) -> BrickMesh:
    """A structured C3D20R mesh of the beam: n_length x n_height x n_width bricks.

    The nodes sit on a half-step grid i = 0..2*n_length, j = 0..2*n_height, k = 0..2*n_width (a point is a node when at
    most one index is odd), numbered from 1 with i in the outer loop and k in the inner one. n_height and n_width must
    be even, so that a node sits at the middle of the tip face.
    """
    if c.n_length < 1 or c.n_height < 2 or c.n_width < 2 or c.n_height % 2 or c.n_width % 2:
        raise ValueError(
            f"need n_length >= 1 and even n_height, n_width >= 2, got {c.n_length}, {c.n_height}, {c.n_width}"
        )
    ni, nj, nk = 2 * c.n_length, 2 * c.n_height, 2 * c.n_width
    number: dict[tuple[int, int, int], int] = {}
    nodes: dict[int, tuple[float, float, float]] = {}
    for i in range(ni + 1):
        for j in range(nj + 1):
            for k in range(nk + 1):
                if i % 2 + j % 2 + k % 2 <= 1:
                    node = len(nodes) + 1
                    number[i, j, k] = node
                    nodes[node] = (i * c.length / ni, j * c.height / nj, k * c.width / nk)
    elements: dict[int, tuple[int, ...]] = {}
    for ex in range(c.n_length):
        for ey in range(c.n_height):
            for ez in range(c.n_width):
                i0, j0, k0 = 2 * ex, 2 * ey, 2 * ez
                element = 1 + ex * c.n_height * c.n_width + ey * c.n_width + ez
                elements[element] = tuple(number[i0 + di, j0 + dj, k0 + dk] for di, dj, dk in _C3D20R_OFFSETS)
    return BrickMesh(
        nodes=nodes,
        elements=elements,
        fixed=tuple(node for (i, _, _), node in number.items() if i == 0),
        tip=tuple(node for (i, _, _), node in number.items() if i == ni),
        tip_center=number[ni, c.n_height, c.n_width],
    )


def _id_lines(ids: tuple[int, ...], per_line: int = 10) -> list[str]:
    return [", ".join(str(n) for n in ids[i : i + per_line]) for i in range(0, len(ids), per_line)]


def cantilever_deck(c: Cantilever = Cantilever(), *, modulus: str = "210000.") -> str:
    """The CalculiX input deck of exercise 01: the beam clamped at x = 0, the tip load shared equally by the tip nodes.

    `modulus` is the text of the Young's modulus field (the default is `STEEL_E`); `broken_cantilever_deck` passes one
    that is not a number. Keywords and their manual sections: `workshop/decklint.py`, `KEYWORDS`.
    """
    if modulus == "210000." and c.young != STEEL_E:
        raise ValueError(f"the modulus text is the default 210000.; pass modulus= to match E = {c.young:g} MPa")
    mesh = c3d20r_mesh(c)
    lines = [
        "** Workshop exercise 01: cantilever beam, linear static (our own deck; units N, mm, MPa).",
        "** Generated by: python -m workshop.generate   (do not edit by hand)",
        "** Keyword sections of the CalculiX 2.21 manual are listed in README.md next to this file.",
        "*HEADING",
        f"Cantilever {c.length:g} x {c.height:g} x {c.width:g} mm with C3D20R elements and a tip load of "
        f"{c.tip_load:g} N in -y",
        "*NODE, NSET=NALL",
    ]
    lines += [f"{node}, {x:.6f}, {y:.6f}, {z:.6f}" for node, (x, y, z) in mesh.nodes.items()]
    lines.append("*ELEMENT, TYPE=C3D20R, ELSET=EALL")
    for element, conn in mesh.elements.items():
        lines.append(", ".join(str(n) for n in (element, *conn[:15])) + ",")  # 16 entries; the comma continues it
        lines.append(", ".join(str(n) for n in conn[15:]))
    lines += ["*NSET, NSET=FIX", *_id_lines(mesh.fixed)]
    lines += ["*NSET, NSET=TIP", *_id_lines(mesh.tip)]
    lines += ["*NSET, NSET=TIPC", str(mesh.tip_center)]
    lines += [
        "*MATERIAL, NAME=STEEL",
        "*ELASTIC",
        f"{modulus}, {c.poisson:g}",
        "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL",
        "*STEP",
        "*STATIC",
        "*BOUNDARY",
        "FIX, 1, 3",
        "*CLOAD",
        f"TIP, 2, {-c.tip_load / len(mesh.tip):.6E}",
        "*NODE PRINT, NSET=TIPC",
        "U",
        "*NODE PRINT, NSET=FIX, TOTALS=ONLY",
        "RF",
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]
    return "\n".join(lines) + "\n"


def broken_cantilever_deck(c: Cantilever = Cantilever()) -> str:
    """The exercise 01 deck with a Young's modulus that is not a number, and a first line that says so."""
    return (
        "** Broken on purpose: the Young's modulus is not a number. CalculiX stops with *ERROR reading *ELASTIC.\n"
        + cantilever_deck(c, modulus="abc")
    )
