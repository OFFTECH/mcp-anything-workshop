"""Builders of `.dat` text in the layout of CalculiX 2.21 `printoutnode.f`, shared by the tests of the reader and of the
verification. They write the Fortran formats in Python; no text here comes from a real run.

    displacements:  ` displacements (vx,vy,vz) for set <SET> and time <e14.7>`, a blank line, rows `(i10,1p,3(1x,e13.6))`
    total force:    ` total force (fx,fy,fz) for set <SET> and time <e14.7>`, a blank line, one row `(6x,1p,3(1x,e13.6))`
"""

TIME_1 = " 0.1000000E+01"
TIME_2 = " 0.2000000E+01"


def disp_row(node: int, *vector: float) -> str:
    return f"{node:10d}" + "".join(f" {v:13.6E}" for v in vector)


def total_row(*vector: float, indent: int = 6) -> str:
    """`(6x,1p,3(1x,e13.6))`: 6 blanks, then three fields of a blank and 13 characters. `indent` replaces the 6."""
    return " " * indent + "".join(f" {v:13.6E}" for v in vector)


def disp_block(name: str, rows: list[tuple[int, tuple[float, float, float]]], time: str = TIME_1) -> str:
    """A blank line, the header, a blank line, one row per node."""
    lines = ["", f" displacements (vx,vy,vz) for set {name} and time {time}", ""]
    lines += [disp_row(node, *vector) for node, vector in rows]
    return "\n".join(lines) + "\n"


def total_block(name: str, vector: tuple[float, float, float], time: str = TIME_1, indent: int = 6) -> str:
    """A blank line, the header, a blank line, the one row."""
    lines = ["", f" total force (fx,fy,fz) for set {name} and time {time}", "", total_row(*vector, indent=indent)]
    return "\n".join(lines) + "\n"
