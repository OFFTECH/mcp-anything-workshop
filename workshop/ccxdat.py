"""Read the node results that CalculiX prints to the `.dat` file (`*NODE PRINT`). Standard library only.

The layouts are those of CalculiX 2.21 `printoutnode.f` / `printout.f`, read from the source and never compared with a run
in this repository (the instructor's `scripts/verify_decks.sh` does that, checklist C31)::

     displacements (vx,vy,vz) for set <SET> and time <e14.7>
                                                       (a blank line)
    <node, i10>  <vx, e13.6>  <vy, e13.6>  <vz, e13.6>  (one row per node, format (i10,1p,3(1x,e13.6)))

     total force (fx,fy,fz) for set <SET> and time <e14.7>
                                                       (a blank line)
          <fx, e13.6>  <fy, e13.6>  <fz, e13.6>        (one row, format (6x,1p,3(1x,e13.6)); `TOTALS=ONLY`)

A header is matched by its text, and a row is split on whitespace, never by column: a node id and three numbers, or three
numbers for a total. That tolerates small differences of layout, such as the indent of the total line. A row that does not
split into these numbers is an error. A block ends at the first blank line after its rows, or at the next header of any
quantity; the text of other quantities (stresses, energies ...) is skipped.

When a set is printed more than once (several increments or steps), the last block is the result. A set name is not
case sensitive. A missing set, a block without a row and a malformed row raise `ValueError`, which names the set and the
sets that were found.
"""

import re
from dataclasses import dataclass, field

_HEADERS = {
    "displacements": re.compile(r"\s*displacements \(vx,vy,vz\) for set (\S+) and time"),
    "total force": re.compile(r"\s*total force \(fx,fy,fz\) for set (\S+) and time"),
}
_ANY_HEADER = re.compile(r" for set \S+ and time")  # the header of any quantity: it ends the block above it


@dataclass
class _Block:
    kind: str  # a key of _HEADERS
    name: str  # the set name, as printed
    rows: list[tuple[int, str]] = field(default_factory=list)  # (line number, line) of every non-blank line below the header


def _blocks(dat_text: str) -> list[_Block]:
    """Every displacements and total-force block of the text, in file order, with its raw rows."""
    blocks: list[_Block] = []
    current: _Block | None = None
    for number, line in enumerate(dat_text.splitlines(), start=1):
        for kind, pattern in _HEADERS.items():
            if match := pattern.match(line):
                current = _Block(kind, match.group(1))
                blocks.append(current)
                break
        else:
            if _ANY_HEADER.search(line):  # another quantity: its rows are not ours
                current = None
            elif current is not None:
                if line.strip():
                    current.rows.append((number, line))
                elif current.rows:  # the blank line under the header comes before the first row
                    current = None
    return blocks


def _found(blocks: list[_Block]) -> str:
    """The sets of the blocks with their quantity, for an error message."""
    seen: dict[str, list[str]] = {}
    for block in blocks:
        names = seen.setdefault(block.kind, [])
        if block.name not in names:
            names.append(block.name)
    return "; ".join(f"{kind}: {', '.join(names)}" for kind, names in seen.items()) or "none"


def _last_block(dat_text: str, kind: str, set_name: str) -> tuple[_Block, str]:
    """The last block of `kind` for the set, and the text of the sets found in the whole text."""
    blocks = _blocks(dat_text)
    wanted = [b for b in blocks if b.kind == kind and b.name.upper() == set_name.upper()]
    if not wanted:
        raise ValueError(f"no {kind} block for set {set_name} in the .dat text (sets found: {_found(blocks)})")
    return wanted[-1], _found(blocks)


def _malformed(block: _Block, found: str, number: int, line: str, expected: str) -> ValueError:
    return ValueError(
        f"{block.kind} block for set {block.name}, line {number}: expected {expected}, found {line.strip()!r} "
        f"(sets found: {found})"
    )


def _floats(tokens: list[str]) -> tuple[float, ...]:
    return tuple(float(token) for token in tokens)


def node_vectors(dat_text: str, set_name: str, quantity: str = "displacements") -> dict[int, tuple[float, float, float]]:
    """Node id -> (x, y, z) from the last `displacements` block printed for the node set `set_name`.

    `quantity` is "displacements", the only node quantity read. Raises ValueError for another quantity, a set that is
    not in the text, a block without a row, a row that is not a node id and three numbers, and a node printed twice.
    """
    if quantity != "displacements":
        raise ValueError(f"cannot read the quantity {quantity!r} (supported: displacements)")
    block, found = _last_block(dat_text, quantity, set_name)
    if not block.rows:
        raise ValueError(f"{quantity} block for set {block.name} has no row (sets found: {found})")
    vectors: dict[int, tuple[float, float, float]] = {}
    for number, line in block.rows:
        tokens = line.split()
        try:
            if len(tokens) != 4:
                raise ValueError
            node = int(tokens[0])
            x, y, z = _floats(tokens[1:])
        except ValueError:
            raise _malformed(block, found, number, line, "a node id and 3 numbers") from None
        if node in vectors:
            raise ValueError(
                f"{quantity} block for set {block.name}, line {number}: node {node} is printed twice (sets found: {found})"
            )
        vectors[node] = (x, y, z)
    return vectors


def total_force(dat_text: str, set_name: str) -> tuple[float, float, float]:
    """(fx, fy, fz) from the last `total force` block printed for the node set `set_name` (`*NODE PRINT, TOTALS=ONLY` + RF).

    Raises ValueError for a set that is not in the text, a block that does not hold exactly one row, and a row that is
    not three numbers.
    """
    block, found = _last_block(dat_text, "total force", set_name)
    if len(block.rows) != 1:
        raise ValueError(f"total force block for set {block.name} has {len(block.rows)} rows, expected 1 (sets found: {found})")
    number, line = block.rows[0]
    tokens = line.split()
    try:
        if len(tokens) != 3:
            raise ValueError
        fx, fy, fz = _floats(tokens)
    except ValueError:
        raise _malformed(block, found, number, line, "3 numbers") from None
    return fx, fy, fz
