"""A small checker for the workshop's own CalculiX decks. Standard library only.

`lint_deck(text)` returns one problem string per finding (empty means clean). It knows only the keywords these decks
use, each with its section of the CalculiX 2.21 manual (`KEYWORDS`), and checks the layout of their data lines, the
sets and materials they reference, and the step structure. It does not replace a run of ccx: the instructor runs
scripts/verify_decks.sh for that.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass

# keyword -> its section of the CalculiX 2.21 manual
KEYWORDS: dict[str, str] = {
    "HEADING": "§7.71",
    "NODE": "§7.95",
    "ELEMENT": "§7.49",
    "NSET": "§7.100",
    "ELSET": "§7.53",
    "MATERIAL": "§7.83",
    "ELASTIC": "§7.46",
    "DENSITY": "§7.35",
    "SOLID SECTION": "§7.118",
    "STEP": "§7.124",
    "STATIC": "§7.122",
    "BOUNDARY": "§7.4",
    "CLOAD": "§7.15",
    "DLOAD": "§7.43",
    "NODE PRINT": "§7.98",
    "NODE FILE": "§7.96",
    "EL FILE": "§7.51",
    "END STEP": "§7.54",
    "INCLUDE": "§7.75",
}
NODES_PER_ELEMENT = {"C3D20R": 20, "C3D20": 20, "C3D10": 10, "CPE6": 6}
STEP_ONLY = {"STATIC", "CLOAD", "DLOAD", "NODE PRINT", "NODE FILE", "EL FILE"}
# the keywords whose cards may have data lines; any other keyword takes none. *SOLID SECTION may have the one line of
# the plane-strain thickness, nothing more (`_thickness_line`)
TAKES_DATA = {
    "HEADING", "NODE", "ELEMENT", "NSET", "ELSET", "ELASTIC", "DENSITY", "SOLID SECTION", "BOUNDARY", "CLOAD", "DLOAD",
    "NODE PRINT", "NODE FILE", "EL FILE",
}  # fmt: skip

MAX_LINE = 132  # bytes per line: the manual's 132 columns (§5.1), which ccx counts in bytes
MAX_ENTRIES = 16  # entries per data line of *ELEMENT (manual §7.49), *NSET and *ELSET

_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([EeDd][+-]?\d+)?")
_INTEGER = re.compile(r"\d+")
_SET_PARAM = {"NSET": "NSET", "ELSET": "ELSET", "NODE": "NSET", "ELEMENT": "ELSET"}  # keyword -> set it can define

Found = list[tuple[int | None, str]]  # (line number or None, message)


@dataclass(frozen=True)
class Card:
    """A keyword line and its data lines: `params` maps each parameter name to its value (None without `=`), `lines`
    holds (line number, fields) for each data line, and `line_no` is the keyword line's number (from 1)."""

    keyword: str
    params: dict[str, str | None]
    lines: tuple[tuple[int, tuple[str, ...]], ...]
    line_no: int


def _name(text: str) -> str:
    """A keyword, parameter or set name normalised: whitespace collapsed to one space, upper case."""
    return " ".join(text.split()).upper()


def parse_deck(text: str) -> list[Card]:
    """The cards of a deck. `**` lines are comments and blank lines are skipped. Raises ValueError for data before the
    first keyword line."""
    cards: list[tuple[str, dict[str, str | None], list, int]] = []
    for line_no, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            name, *fields = line[1:].split(",")
            params: dict[str, str | None] = {}
            for field in fields:
                key, equals, value = field.partition("=")
                if key.strip() or equals:
                    params[_name(key)] = value.strip() if equals else None
            cards.append((_name(name), params, [], line_no))
            continue
        if not cards:
            raise ValueError(f"line {line_no}: data line before the first keyword")
        fields = [field.strip() for field in line.split(",")]
        if fields[-1] == "":
            fields.pop()  # one trailing comma: a continued *ELEMENT record, or a habit
        cards[-1][2].append((line_no, tuple(fields)))
    return [Card(keyword, params, tuple(lines), line_no) for keyword, params, lines, line_no in cards]


def includes(text: str) -> list[str]:
    """The INPUT= values of the deck's *INCLUDE cards, in order."""
    return [card.params["INPUT"] for card in parse_deck(text) if card.keyword == "INCLUDE" and card.params.get("INPUT")]


def lint_deck(text: str, external_sets: Collection[str] = ()) -> list[str]:
    """The deck's problems, sorted by line, each starting with `line N:` where a line applies. Empty means clean.

    `external_sets` names sets that another file defines (an included or separate mesh); like all set and material
    names they are compared case-insensitively.
    """
    found: Found = []
    for line_no, raw in enumerate(text.split("\n"), start=1):
        length = len(raw.rstrip("\r").encode("utf-8"))
        if length > MAX_LINE:
            found.append((line_no, f"{length} bytes, longer than {MAX_LINE} (manual §5.1)"))
    try:
        cards = parse_deck(text)
    except ValueError as error:
        return _formatted(found) + [str(error)]
    sets = {_name(name) for name in external_sets} | _defined_sets(cards)
    materials = {_name(c.params["NAME"] or "") for c in cards if c.keyword == "MATERIAL" and c.params.get("NAME")}
    for card in cards:
        found += _card_problems(card, sets, materials)
    found += _step_problems(cards)
    return _formatted(found)


def _defined_sets(cards: list[Card]) -> set[str]:
    """The names given by *NSET NSET=, *ELSET ELSET=, *NODE NSET= and *ELEMENT ELSET=, normalised."""
    names = set()
    for card in cards:
        param = _SET_PARAM.get(card.keyword)
        value = card.params.get(param) if param else None
        if value:
            names.add(_name(value))
    return names


def _formatted(found: Found) -> list[str]:
    ordered = sorted(found, key=lambda item: (item[0] is None, item[0] or 0))  # stable: same-line order is kept
    return [f"line {line_no}: {message}" if line_no is not None else message for line_no, message in ordered]


def _is_reference(field: str, sets: set[str]) -> bool:
    """A node or element id, or a defined set."""
    return bool(_INTEGER.fullmatch(field)) or _name(field) in sets


def _card_problems(card: Card, sets: set[str], materials: set[str]) -> Found:
    keyword = card.keyword
    if keyword not in KEYWORDS:
        return [(card.line_no, f"unknown keyword *{keyword}")]
    found: Found = []
    if card.lines and keyword not in TAKES_DATA:
        found.append((card.lines[0][0], f"*{keyword}: these exercises give it no data lines"))
    if keyword == "NODE":
        found += _node_lines(card)
    elif keyword == "ELEMENT":
        found += _element_lines(card)
    elif keyword in ("NSET", "ELSET"):
        found += _set_lines(card, sets)
    elif keyword == "ELASTIC":
        found += _constants(card, 2)
    elif keyword == "DENSITY":
        found += _constants(card, 1)
    elif keyword in ("BOUNDARY", "CLOAD", "DLOAD"):
        found += _load_lines(card, sets)
    elif keyword == "NODE PRINT":
        found += _set_parameter(card, "NSET", sets)
    elif keyword == "SOLID SECTION":
        found += _set_parameter(card, "ELSET", sets)
        found += _thickness_line(card)
        material = card.params.get("MATERIAL")
        if not material:
            found.append((card.line_no, "*SOLID SECTION needs MATERIAL="))
        elif _name(material) not in materials:
            found.append((card.line_no, f"undefined material {material}"))
    return found


def _node_lines(card: Card) -> Found:
    found: Found = []
    for line_no, fields in card.lines:
        if len(fields) != 4:
            found.append((line_no, f"*NODE needs 4 fields (id, x, y, z), got {len(fields)}"))
            continue
        if not _INTEGER.fullmatch(fields[0]):
            found.append((line_no, f"*NODE: '{fields[0]}' is not an integer id"))
        found += [(line_no, f"*NODE: '{field}' is not a number") for field in fields[1:] if not _NUMBER.fullmatch(field)]
    return found


def _element_lines(card: Card) -> Found:
    found: Found = []
    element_type = card.params.get("TYPE")
    choices = ", ".join(NODES_PER_ELEMENT)
    nodes = NODES_PER_ELEMENT.get(_name(element_type or ""))
    if not element_type:
        found.append((card.line_no, f"*ELEMENT needs TYPE=, one of {choices}"))
    elif nodes is None:
        found.append((card.line_no, f"*ELEMENT TYPE={element_type} is not one of {choices}"))
    record_line, count = card.line_no, 0  # a record is the element id and its nodes, continued over lines
    for line_no, fields in card.lines:
        if len(fields) > MAX_ENTRIES:
            message = f"*ELEMENT line has {len(fields)} entries, at most {MAX_ENTRIES} entries per line (manual §7.49)"
            found.append((line_no, message))
        found += [(line_no, f"*ELEMENT: '{field}' is not an integer") for field in fields if not _INTEGER.fullmatch(field)]
        if nodes is None:
            continue
        if count == 0:
            record_line = line_no
        count += len(fields)
        if count >= nodes + 1:
            if count > nodes + 1:
                found.append((record_line, _record_size(count, element_type, nodes)))
            count = 0
    if count:
        found.append((record_line, _record_size(count, element_type, nodes)))
    return found


def _record_size(count: int, element_type: str | None, nodes: int | None) -> str:
    return f"*ELEMENT record has {count} entries, TYPE={element_type} needs {(nodes or 0) + 1} (id and {nodes} nodes)"


def _set_lines(card: Card, sets: set[str]) -> Found:
    keyword = card.keyword  # NSET or ELSET, which is also the name of the required parameter
    found: Found = []
    if not card.params.get(keyword):
        found.append((card.line_no, f"*{keyword} needs {keyword}="))
    for line_no, fields in card.lines:
        if len(fields) > MAX_ENTRIES:
            limit = f"at most {MAX_ENTRIES} entries per line (manual {KEYWORDS[keyword]})"
            found.append((line_no, f"*{keyword} line has {len(fields)} entries, {limit}"))
        found += [(line_no, f"undefined set {field}") for field in fields if not _is_reference(field, sets)]
    return found


def _constants(card: Card, numbers: int) -> Found:
    """*ELASTIC (modulus, Poisson's ratio) and *DENSITY: one data line with `numbers` numbers."""
    keyword = card.keyword
    found: Found = []
    if len(card.lines) != 1:
        found.append((card.line_no, f"*{keyword} needs one data line, got {len(card.lines)}"))
    for line_no, fields in card.lines:
        if len(fields) != numbers:
            found.append((line_no, f"*{keyword} needs {numbers} number{'s' if numbers > 1 else ''}, got {len(fields)}"))
        found += [(line_no, f"*{keyword}: '{field}' is not a number") for field in fields if not _NUMBER.fullmatch(field)]
    return found


def _thickness_line(card: Card) -> Found:
    """*SOLID SECTION: no data line (solid elements), or one line with one number above 0, the thickness of a plane
    strain element (manual §7.118). Nothing else is accepted."""
    found: Found = []
    section = KEYWORDS["SOLID SECTION"]
    thickness = f"the plane-strain thickness, manual {section}"
    if len(card.lines) > 1:
        found.append((card.lines[1][0], f"*SOLID SECTION: these exercises give it at most one data line ({thickness})"))
    for line_no, fields in card.lines[:1]:
        if len(fields) != 1:
            found.append((line_no, f"*SOLID SECTION needs 1 number ({thickness}), got {len(fields)}"))
        found += [(line_no, f"*SOLID SECTION: '{field}' is not a number") for field in fields if not _NUMBER.fullmatch(field)]
        if len(fields) == 1 and _NUMBER.fullmatch(fields[0]) and float(re.sub("[Dd]", "e", fields[0])) <= 0:
            found.append((line_no, f"*SOLID SECTION: thickness '{fields[0]}' must be above 0 (manual {section})"))
    return found


def _load_lines(card: Card, sets: set[str]) -> Found:
    """*BOUNDARY: target, first and optional last degree of freedom, optional value. *CLOAD: target, degree of freedom,
    value. *DLOAD: only its target (element or element set) is checked."""
    keyword = card.keyword
    found: Found = []
    for line_no, fields in card.lines:
        target, *rest = fields
        if not _is_reference(target, sets):
            found.append((line_no, f"undefined set {target}"))
        if keyword == "DLOAD":
            continue
        if keyword == "BOUNDARY" and not 2 <= len(fields) <= 4:
            found.append((line_no, f"*BOUNDARY needs 2 to 4 fields, got {len(fields)}"))
            continue
        if keyword == "CLOAD" and len(fields) != 3:
            found.append((line_no, f"*CLOAD needs 3 fields, got {len(fields)}"))
            continue
        dofs, values = (rest[:2], rest[2:]) if keyword == "BOUNDARY" else (rest[:1], rest[1:])
        found += [
            (line_no, f"*{keyword}: '{dof}' is not an integer degree of freedom")
            for dof in dofs
            if not _INTEGER.fullmatch(dof)
        ]
        found += [(line_no, f"*{keyword}: '{value}' is not a number") for value in values if not _NUMBER.fullmatch(value)]
    return found


def _set_parameter(card: Card, param: str, sets: set[str]) -> Found:
    value = card.params.get(param)
    if not value:
        return [(card.line_no, f"*{card.keyword} needs {param}=")]
    return [] if _is_reference(value, sets) else [(card.line_no, f"undefined set {value}")]


def _step_problems(cards: list[Card]) -> Found:
    """Exactly one *STEP, then one *END STEP; the STEP_ONLY keywords only between them."""
    found: Found = []
    starts = [card.line_no for card in cards if card.keyword == "STEP"]
    ends = [card.line_no for card in cards if card.keyword == "END STEP"]
    for keyword, lines in (("STEP", starts), ("END STEP", ends)):
        if not lines:
            found.append((None, f"no *{keyword} (a deck needs exactly one)"))
        found += [(line_no, f"another *{keyword} (a deck needs exactly one)") for line_no in lines[1:]]
    if starts and ends and ends[0] < starts[0]:
        found.append((ends[0], "*END STEP before *STEP"))
    inside = False
    for card in cards:
        if card.keyword == "STEP":
            inside = True
        elif card.keyword == "END STEP":
            inside = False
        elif card.keyword in STEP_ONLY and not inside:
            found.append((card.line_no, f"*{card.keyword} outside *STEP ... *END STEP"))
    return found
