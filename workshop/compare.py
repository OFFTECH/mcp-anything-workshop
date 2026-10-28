"""The comparison rule: values a server read from a solver's result against reference values.

This mirrors the semantics of MCP-Anything's `templates/common/compare.py`, so that this repository's verification and
a participant's `compare_to_reference` tool agree. Standard library only.

A reference file is JSON::

    {"source": "hand calculation",
     "values": {"tip_displacement_y": -2.5, "support_reaction_y": 21.0},
     "tolerance": {"rel": 0.02, "abs": 0.0},
     "tolerances": {"support_reaction_y": {"rel": 1e-06, "abs": 0.0001}}}

`source` and `values` are required. `tolerance` defaults to 0/0 (an exact match), and a name in `tolerances` uses that
tolerance instead of the general one (it replaces it, key by key defaulting to 0, and is never added to it). Anything
else in the file is an error: a typo must not silently loosen a check.

A value is allowed to differ from its reference by `limit = max(abs, rel * |expected|)`. The unit of a value is the
unit of the thing it names; this module does not convert units.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REFERENCE_KEYS = ("source", "values", "tolerance", "tolerances")
_TOLERANCE_KEYS = ("rel", "abs")


@dataclass(frozen=True)
class Row:
    """One reference value against the actual one. `actual` is None when the name is missing from the actual values."""

    name: str
    expected: float
    actual: float | None
    limit: float
    ok: bool


def _number(value: object) -> float | None:
    """`value` as a float if it is a finite int or float (never a bool); else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)  # an int too large for a float raises OverflowError
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _show(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


class _DuplicateKey(ValueError):
    pass


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _refuse(path: Path, problem: str, key: str | None = None) -> ValueError:
    where = f"'{key}' " if key is not None else ""
    return ValueError(f"Reference file {path}: {where}{problem}")


def _check_tolerance(path: Path, key: str, raw: object) -> None:
    if not isinstance(raw, dict):
        raise _refuse(path, 'must be an object like {"rel": 0.01, "abs": 0.0}.', key)
    for part, number in raw.items():
        if part not in _TOLERANCE_KEYS:
            raise _refuse(path, f"is not a known key (known: {', '.join(_TOLERANCE_KEYS)}).", f"{key}.{part}")
        checked = _number(number)
        if checked is None or checked < 0:
            raise _refuse(path, f"must be a finite number >= 0, got {_show(number)}.", f"{key}.{part}")


def load_reference(path: Path) -> dict:
    """Read and check a reference file; returns the parsed JSON object.

    Raises ValueError, naming the file and the offending key, for: a file that is not a JSON object (or has a key
    twice); an unknown key; a missing `source` or `values`, or empty `values`; a bool or non-finite value; a negative or
    non-finite tolerance; a `tolerances` name that is not in `values`. A file that cannot be read raises OSError.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_no_duplicate_keys)
    except _DuplicateKey as exc:
        raise _refuse(path, "is given twice.", str(exc)) from None
    except (ValueError, RecursionError) as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise _refuse(path, f"is not valid JSON ({exc}).") from None
    if not isinstance(data, dict):
        raise _refuse(path, f"must hold a JSON object, not {type(data).__name__}.")
    for key in data:
        if key not in REFERENCE_KEYS:
            raise _refuse(path, f"is not a known key (known: {', '.join(REFERENCE_KEYS)}).", key)

    source = data.get("source")
    if not isinstance(source, str) or not source.strip():
        raise _refuse(path, "is required: a non-empty text saying where the reference values come from.", "source")

    values = data.get("values")
    if not isinstance(values, dict) or not values:
        raise _refuse(path, "is required: an object of name: number, with at least one entry.", "values")
    for name, raw in values.items():
        if _number(raw) is None:
            raise _refuse(path, f"must be a finite number (not text, true/false, NaN or infinity), got {_show(raw)}.", f"values.{name}")

    if "tolerance" in data:
        _check_tolerance(path, "tolerance", data["tolerance"])
    if "tolerances" in data:
        tolerances = data["tolerances"]
        if not isinstance(tolerances, dict):
            raise _refuse(path, "must be an object of name: {rel, abs}.", "tolerances")
        for name, raw in tolerances.items():
            if name not in values:
                raise _refuse(path, "names a value that is not in 'values'.", f"tolerances.{name}")
            _check_tolerance(path, f"tolerances.{name}", raw)
    return data


def _limit(tolerance: Mapping[str, float], expected: float) -> float:
    return max(float(tolerance.get("abs", 0.0)), float(tolerance.get("rel", 0.0)) * abs(expected))


def compare(actual: Mapping[str, float], reference: dict) -> list[Row]:
    """Compare actual values with a loaded reference: one row per reference value, in the reference's order.

    `limit = max(abs, rel * |expected|)` from the name's own tolerance if it has one, else the general one (default
    0/0). A row is `ok` when `actual` is finite and `|actual - expected| <= limit`. A name missing from `actual` gives
    `actual=None, ok=False`; a name in `actual` that the reference does not have is ignored. An actual value that is
    not an int or a float (a bool included) raises ValueError: that is a bug in whatever produced it, not a difference
    in results.
    """
    general = reference.get("tolerance", {})
    own = reference.get("tolerances", {})
    rows = []
    for name, raw_expected in reference["values"].items():
        expected = float(raw_expected)
        limit = _limit(own.get(name, general), expected)
        if name not in actual:
            rows.append(Row(name, expected, None, limit, False))
            continue
        value = actual[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"The actual value '{name}' is {_show(value)}, not a number.")
        try:
            number = float(value)
        except OverflowError:
            raise ValueError(f"The actual value '{name}' is too large to compare ({_show(value)}).") from None
        ok = math.isfinite(number) and abs(number - expected) <= limit
        rows.append(Row(name, expected, number, limit, ok))
    return rows
