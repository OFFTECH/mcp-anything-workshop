"""Helpers for the Abaqus/CalculiX-style `.inp` mesh that Gmsh exports, and a command line for two pre-processing steps.

Standard library only. Neither step reimplements the solver: they edit and read the mesh text, nothing more.

The layout read here is what Gmsh 4.12.1 writes (tag `gmsh_4_12_1`, `src/geo/GModelIO_INP.cpp` and
`MElement::writeINP` in `src/geo/MElement.cpp`)::

    *Heading
     <file name>
    *NODE
    <id>, <x>, <y>, <z>
    *ELEMENT, type=<T>, ELSET=<Entity><tag>
    <id>, <n1>, <n2>, ...            (a line is wrapped after 16 entries; the wrapped line ends with ", ")
    *ELSET,ELSET=<NAME>
    <id>, <id>, ...,                 (10 entries per line, each line ends with ", ")
    *NSET,NSET=<NAME>
    <id>, <id>, ...,

Gmsh writes 6-node triangles as `CPS6` (plane stress). CalculiX would solve plane stress without complaint when the
analysis is meant to be plane strain: a wrong result, not an error. `to_plane_strain` renames `CPS6` to `CPE6` (manual
section 6.2.25) and refuses every other element type.

Rule: a mesh is never changed silently. An element type that is not known, an element whose node count does not match
its type, a repeated id, an unreadable number or a node that is not defined all raise `ValueError`. Nothing is passed
through or skipped. References to the CalculiX manual are to version 2.21.
"""

import argparse
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Number of nodes of each element type this module accepts (Abaqus/CalculiX names, manual section 6.2).
NODES_PER_TYPE = {
    "T3D2": 2,
    "T3D3": 3,
    "CPS3": 3,
    "CPS4": 4,
    "CPS6": 6,
    "CPS8": 8,
    "CPE3": 3,
    "CPE4": 4,
    "CPE6": 6,
    "CPE8": 8,
    "C3D4": 4,
    "C3D6": 6,
    "C3D8": 8,
    "C3D10": 10,
    "C3D15": 15,
    "C3D20": 20,
}

TRIANGLES = frozenset({"CPS3", "CPS6", "CPE3", "CPE6"})  # corner nodes 1, 2, 3; a 6-node triangle adds mid-nodes 4-6
PRESSURE_TYPES = frozenset({"CPS6", "CPE6"})
UNSUPPORTED_PLANE_TYPES = frozenset({"CPS3", "CPE3", "CPS4", "CPE4", "CPS8", "CPE8"})  # edges with no face here

# Faces of the 6-node triangle as (first corner, second corner, mid-node), 1-based positions in the element's node
# list: face 1 = nodes 1, 2 and 4; face 2 = nodes 2, 3 and 5; face 3 = nodes 3, 1 and 6 (manual section 7.43 for the
# face numbers of *DLOAD, section 6.2.25 for the mid-nodes).
TRIANGLE_FACES = ((1, 2, 4), (2, 3, 5), (3, 1, 6))

_PHYSICAL_DIMENSIONS = {"Point": 0, "Curve": 1, "Line": 1, "Surface": 2, "Volume": 3}  # Gmsh reads Line as Curve
_PHYSICAL = re.compile(r'\bPhysical\s+(Point|Curve|Line|Surface|Volume)\s*\(\s*"([^"]*)"')
_GEO_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_LINES = re.compile(r"[^\n]*\n|[^\n]+")
_TYPE_PARAMETER = re.compile(r"(\btype\s*=\s*)([^,\s]+)", re.IGNORECASE)


def physical_names(geo_text: str) -> dict[str, int]:
    """Name -> dimension (0 point, 1 curve, 2 surface, 3 volume) of every named `Physical` group of a `.geo` file.

    `Physical Line` counts as `Physical Curve`. Comments are ignored. A name used for two dimensions is ambiguous and
    raises `ValueError`.
    """
    names: dict[str, int] = {}
    for kind, name in _PHYSICAL.findall(_GEO_COMMENT.sub("", geo_text)):
        dimension = _PHYSICAL_DIMENSIONS[kind]
        if names.setdefault(name, dimension) != dimension:
            raise ValueError(f"physical name {name!r} is used for dimensions {names[name]} and {dimension}")
    return names


@dataclass
class _Block:
    """A keyword line and the data records below it."""

    keyword: str  # upper case, without the "*": "NODE", "ELEMENT", "NSET" ...
    parameters: dict[str, str]  # upper-case names; the value is stripped, and empty for a flag such as GENERATE
    index: int  # position of the keyword line in the list of lines
    number: int  # 1-based line number of the keyword line
    records: list[tuple[int, list[str]]] = field(default_factory=list)  # (line number, stripped fields)


def _parse(inp_text: str) -> tuple[list[str], list[_Block]]:
    """The lines of the text (with their line ends) and its blocks.

    A comment line (`**`) and a blank line are skipped. A data line that ends with a comma continues on the next line,
    which is how Gmsh wraps long element lines.
    """
    lines = _LINES.findall(inp_text)
    blocks: list[_Block] = []
    continued = False
    for index, raw in enumerate(lines):
        number = index + 1
        text = raw.strip()
        if not text or text.startswith("**"):
            continue
        if text.startswith("*"):
            head, *rest = text.split(",")
            parameters = {}
            for item in rest:
                name, _, value = item.strip().partition("=")
                if name.strip():
                    parameters[name.strip().upper()] = value.strip()
            blocks.append(_Block(" ".join(head[1:].split()).upper(), parameters, index, number))
            continued = False
            continue
        if not blocks:
            raise ValueError(f"line {number}: data before the first keyword line")
        fields = [f.strip() for f in text.split(",")]
        if text.endswith(","):
            fields.pop()  # the empty field after the trailing comma
        records = blocks[-1].records
        if continued:
            records[-1][1].extend(fields)
        else:
            records.append((number, fields))
        continued = text.endswith(",")
    return lines, blocks


def _int(value: str, number: int, what: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"line {number}: {what} must be an integer, found {value!r}") from None


def _float(value: str, number: int, what: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"line {number}: {what} must be a number, found {value!r}") from None


def _element_type(block: _Block) -> str:
    try:
        return block.parameters["TYPE"].upper()
    except KeyError:
        raise ValueError(f"line {block.number}: *ELEMENT block without a type= parameter") from None


def element_types(inp_text: str) -> list[str]:
    """The upper-case `TYPE` of every `*ELEMENT` block, in file order."""
    return [_element_type(b) for b in _parse(inp_text)[1] if b.keyword == "ELEMENT"]


def node_coordinates(inp_text: str) -> dict[int, tuple[float, float, float]]:
    """Node id -> (x, y, z) from the `*NODE` blocks. A line is `id, x, y, z`.

    A repeated id and a coordinate that is not finite (`nan`, `inf`) raise `ValueError`.
    """
    coordinates: dict[int, tuple[float, float, float]] = {}
    for block in _parse(inp_text)[1]:
        if block.keyword != "NODE":
            continue
        for number, fields in block.records:
            if len(fields) != 4:
                raise ValueError(f"line {number}: a node needs 'id, x, y, z', found {len(fields)} fields")
            node = _int(fields[0], number, "node id")
            if node in coordinates:
                raise ValueError(f"line {number}: node {node} is defined twice")
            x, y, z = (_float(f, number, "a coordinate") for f in fields[1:])
            if not all(math.isfinite(c) for c in (x, y, z)):
                raise ValueError(f"line {number}: the coordinates of node {node} must be finite, found {fields[1:]}")
            coordinates[node] = (x, y, z)
    return coordinates


def elements(inp_text: str) -> dict[int, tuple[str, tuple[int, ...]]]:
    """Element id -> (type, node ids) from the `*ELEMENT` blocks.

    An unknown type, a node count that does not match the type, and a repeated id raise `ValueError`.
    """
    found: dict[int, tuple[str, tuple[int, ...]]] = {}
    for block in _parse(inp_text)[1]:
        if block.keyword != "ELEMENT":
            continue
        element_type = _element_type(block)
        expected = NODES_PER_TYPE.get(element_type)
        if expected is None:
            raise ValueError(f"line {block.number}: unknown element type {element_type}")
        for number, fields in block.records:
            element = _int(fields[0], number, "element id")
            nodes = tuple(_int(f, number, f"a node of element {element}") for f in fields[1:])
            if len(nodes) != expected:
                raise ValueError(
                    f"line {number}: element {element} has {len(nodes)} nodes, but type {element_type} has {expected}"
                )
            if element in found:
                raise ValueError(f"line {number}: element {element} is defined twice")
            found[element] = (element_type, nodes)
    return found


def node_sets(inp_text: str) -> dict[str, set[int]]:
    """Set name (upper case) -> node ids from the `*NSET` blocks. Empty fields are ignored; blocks of one name add up.

    The `GENERATE` form is not written by Gmsh and raises `ValueError`, as does a block without a name.
    """
    sets: dict[str, set[int]] = {}
    for block in _parse(inp_text)[1]:
        if block.keyword != "NSET":
            continue
        name = block.parameters.get("NSET", "").upper()
        if not name:
            raise ValueError(f"line {block.number}: *NSET block without an NSET= name")
        if "GENERATE" in block.parameters:
            raise ValueError(f"line {block.number}: *NSET {name} uses GENERATE, which is not supported")
        members = sets.setdefault(name, set())
        for number, fields in block.records:
            members.update(_int(f, number, f"a member of {name}") for f in fields if f)
    return sets


def to_plane_strain(inp_text: str) -> str:
    """The text with every `*ELEMENT` block `type=CPS6` rewritten to `type=CPE6`; the rest is unchanged, byte for byte.

    Every block must be `CPS6`: any other type (`CPS3`, `CPS8`, `T3D3`, `C3D10` ...) raises `ValueError` naming it, and
    so does a text without an element block or with an element whose node count does not match its type.
    """
    lines, blocks = _parse(inp_text)
    element_blocks = [b for b in blocks if b.keyword == "ELEMENT"]
    if not element_blocks:
        raise ValueError("no *ELEMENT block: there is nothing to rewrite")
    for block in element_blocks:
        if (element_type := _element_type(block)) != "CPS6":
            raise ValueError(
                f"line {block.number}: element type {element_type} cannot be rewritten to plane strain; only CPS6 can "
                "(Gmsh writes CPS6 with Mesh.ElementOrder = 2, nothing recombined and only the surface elements saved)"
            )
    elements(inp_text)  # the node counts, the numbers and the ids must all be right before anything is rewritten
    for block in element_blocks:
        lines[block.index], count = _TYPE_PARAMETER.subn(r"\1CPE6", lines[block.index], count=1)
        if count != 1:  # unreachable for a block whose type= was read from this very line
            raise ValueError(f"line {block.number}: cannot rewrite the type of this *ELEMENT line")
    return "".join(lines)


def clockwise_elements(inp_text: str) -> list[int]:
    """Sorted ids of the triangles (CPS3, CPS6, CPE3, CPE6) whose corner nodes 1-2-3 do not run counter-clockwise.

    The signed area in the x-y plane is at most 0, or not a number. Other element types are not triangles and are not
    looked at. A node that an element names but the mesh does not define, and a coordinate that is not finite, raise
    `ValueError`.
    """
    coordinates = node_coordinates(inp_text)
    clockwise = []
    for element, (element_type, nodes) in elements(inp_text).items():
        if element_type not in TRIANGLES:
            continue
        corners = []
        for node in nodes[:3]:
            if node not in coordinates:
                raise ValueError(f"element {element} uses node {node}, which is not defined")
            corners.append(coordinates[node])
        (x1, y1, _), (x2, y2, _), (x3, y3, _) = corners
        area = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)  # twice the signed area; NaN if the products overflow
        if not area > 0.0:  # also true for NaN: only a positive area passes
            clockwise.append(element)
    return sorted(clockwise)


def pressure_faces(inp_text: str, nset: str) -> list[tuple[int, int]]:
    """Sorted (element, face) pairs of the CPE6/CPS6 faces whose three nodes are all in the node set `nset`.

    Face 1 = nodes 1, 2 and mid-node 4; face 2 = nodes 2, 3 and mid-node 5; face 3 = nodes 3, 1 and mid-node 6 (manual
    section 7.43, mid-nodes as in section 6.2.25). The set name is not case sensitive; an unknown name raises
    `ValueError`.

    A mesh that holds another plane element type (CPS3, CPE3, CPS4, CPE4, CPS8, CPE8) raises `ValueError` too: its edges
    would not get a face, and the load would be partial without a sign of it. Elements that carry no pressure, such as
    the T3D3 line elements of a physical curve, and solids are not looked at.
    """
    for element_type in element_types(inp_text):
        if element_type in UNSUPPORTED_PLANE_TYPES:
            raise ValueError(
                f"the mesh holds {element_type} elements, which get no pressure face here, so the load would be "
                "partial; only CPS6/CPE6 are supported "
                "(Gmsh writes CPS6 with Mesh.ElementOrder = 2, nothing recombined and only the surface elements saved)"
            )
    sets = node_sets(inp_text)
    wanted = sets.get(nset.upper())
    if wanted is None:
        known = ", ".join(sorted(sets)) or "none"
        raise ValueError(f"no node set named {nset.upper()} (the mesh has: {known})")
    faces = []
    for element, (element_type, nodes) in elements(inp_text).items():
        if element_type not in PRESSURE_TYPES:
            continue
        for face, positions in enumerate(TRIANGLE_FACES, start=1):
            if all(nodes[p - 1] in wanted for p in positions):
                faces.append((element, face))
    return sorted(faces)


def dload_text(faces: Sequence[tuple[int, int]], pressure: float) -> str:
    """A `*DLOAD` block (manual section 7.43): one line `element, P<face>, pressure` per face. No faces is an error.

    A positive pressure presses onto the face (manual section 7.43).
    """
    if not faces:
        raise ValueError("no faces: a *DLOAD block without a line would load nothing")
    return "*DLOAD\n" + "".join(f"{element}, P{face}, {pressure:.6E}\n" for element, face in faces)


def _read(path: str) -> str:
    return Path(path).read_bytes().decode("utf-8")  # bytes, so that the line ends are not translated


def _write(path: str, text: str) -> None:
    Path(path).write_bytes(text.encode("utf-8"))


def _plane_strain(source: str, target: str) -> None:
    result = to_plane_strain(_read(source))
    wrong = clockwise_elements(result)
    if wrong:
        shown = ", ".join(str(e) for e in wrong[:10]) + (", ..." if len(wrong) > 10 else "")
        raise ValueError(
            f"{len(wrong)} triangle(s) do not run counter-clockwise (element {shown}): "
            "CalculiX needs corner nodes 1-2-3 counter-clockwise in the x-y plane"
        )
    _write(target, result)
    print(f"wrote {target}: {len(element_types(result))} element block(s), type CPE6")


def _dload(mesh: str, nset: str, pressure: str, target: str) -> None:
    magnitude = _pressure(pressure)
    faces = pressure_faces(_read(mesh), nset)
    _write(target, dload_text(faces, magnitude))
    print(f"wrote {target}: {len(faces)} face(s) of node set {nset.upper()}")


def _pressure(value: str) -> float:
    try:
        magnitude = float(value)
    except ValueError:
        raise ValueError(f"the pressure must be a number, found {value!r}") from None
    if not math.isfinite(magnitude):
        raise ValueError(f"the pressure must be finite, found {value!r}")
    return magnitude


DLOAD_EPILOG = """\
sign: a positive value presses onto the face (manual section 7.43).

A negative value in exponent form needs `--` before the arguments, because Python 3.12 (the codespace's python3) reads -1e3
as an option:
  python3 -m workshop.gmshinp dload -- MESH NSET -1e3 OUT
A plain negative number such as -5 needs no `--`.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.gmshinp", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    plane_strain = commands.add_parser(
        "plane-strain",
        help="rename CPS6 to CPE6 (any other element type is refused) and require counter-clockwise triangles",
    )
    plane_strain.add_argument("source", metavar="IN", help="the .inp mesh that Gmsh wrote")
    plane_strain.add_argument("target", metavar="OUT", help="the plane-strain mesh to write")
    dload = commands.add_parser(
        "dload",
        usage="%(prog)s [-h] [--] MESH NSET PRESSURE OUT",
        help="write a *DLOAD block for the faces whose nodes are all in a node set",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=DLOAD_EPILOG,
    )
    dload.add_argument("mesh", metavar="MESH", help="the .inp mesh (CPS6 or CPE6 elements)")
    dload.add_argument("nset", metavar="NSET", help="name of the node set, not case sensitive")
    dload.add_argument(
        "pressure",
        metavar="PRESSURE",
        help="the pressure, in the units of the deck (MPa); positive presses onto the face",
    )
    dload.add_argument("target", metavar="OUT", help="the include file to write")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:  # argparse has printed its message
        return stop.code if isinstance(stop.code, int) else 2
    try:
        if args.command == "plane-strain":
            _plane_strain(args.source, args.target)
        else:
            _dload(args.mesh, args.nset, args.pressure, args.target)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
