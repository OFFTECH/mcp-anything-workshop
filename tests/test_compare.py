import json
import math

import pytest

from workshop.compare import REFERENCE_KEYS, Row, compare, load_reference


def test_reference_keys_are_the_four_known_ones():
    assert REFERENCE_KEYS == ("source", "values", "tolerance", "tolerances")


def test_exact_match_and_relative_limit():
    reference = {"source": "s", "values": {"a": 2.0}, "tolerance": {"rel": 0.01}}
    [row] = compare({"a": 2.0}, reference)
    assert row == Row("a", 2.0, 2.0, row.limit, True)
    assert row.limit == pytest.approx(0.02)
    assert compare({"a": 2.019}, reference)[0].ok
    assert not compare({"a": 2.03}, reference)[0].ok
    assert compare({"a": 1.981}, reference)[0].ok  # the limit is two-sided
    assert not compare({"a": 1.97}, reference)[0].ok


def test_default_tolerance_is_an_exact_match():
    reference = {"source": "s", "values": {"a": 2.0}}
    assert compare({"a": 2.0}, reference)[0].ok
    assert not compare({"a": 2.0000000001}, reference)[0].ok
    assert compare({"a": 2.0}, reference)[0].limit == 0.0


def test_limit_is_the_larger_of_absolute_and_relative():
    # |expected| = 100: rel gives 1.0, abs gives 5.0 -> 5.0; |expected| = 1000: rel gives 10.0 -> 10.0
    reference = {"source": "s", "values": {"a": 100.0, "b": -1000.0}, "tolerance": {"rel": 0.01, "abs": 5.0}}
    rows = compare({"a": 104.9, "b": -1009.9}, reference)
    assert [row.limit for row in rows] == [pytest.approx(5.0), pytest.approx(10.0)]
    assert [row.ok for row in rows] == [True, True]
    rows = compare({"a": 105.1, "b": -1010.1}, reference)
    assert [row.ok for row in rows] == [False, False]


def test_a_difference_exactly_at_the_limit_is_ok():
    reference = {"source": "s", "values": {"a": 2.0}, "tolerance": {"abs": 0.5}}
    assert compare({"a": 2.5}, reference)[0].ok
    assert compare({"a": 1.5}, reference)[0].ok
    assert not compare({"a": 2.5000001}, reference)[0].ok


def test_per_name_tolerance_wins():
    reference = {
        "source": "s",
        "values": {"a": 10.0, "b": 10.0},
        "tolerance": {"rel": 0.5, "abs": 0.0},
        "tolerances": {"b": {"rel": 1e-6, "abs": 0.0}},
    }
    rows = compare({"a": 12.0, "b": 12.0}, reference)
    assert [row.name for row in rows] == ["a", "b"]  # the order of the reference
    assert [row.ok for row in rows] == [True, False]  # b's own tolerance replaces the general one, it is not widened by it
    assert rows[1].limit == pytest.approx(1e-5)
    # a per-name tolerance that gives only `abs` does not inherit the general `rel`
    reference["tolerances"] = {"b": {"abs": 0.001}}
    assert compare({"a": 10.0, "b": 10.0005}, reference)[1].ok
    assert not compare({"a": 10.0, "b": 10.002}, reference)[1].ok


def test_missing_and_nonfinite_values_fail():
    reference = {"source": "s", "values": {"a": 1.0, "b": 2.0, "c": 3.0}, "tolerance": {"rel": 1.0, "abs": 1e9}}
    rows = compare({"a": float("nan"), "c": float("inf")}, reference)
    assert [row.name for row in rows] == ["a", "b", "c"]
    assert rows[1].actual is None and not rows[1].ok  # missing
    assert math.isnan(rows[0].actual) and not rows[0].ok  # NaN never matches, however wide the limit
    assert math.isinf(rows[2].actual) and not rows[2].ok
    assert not compare({"a": float("-inf")}, {"source": "s", "values": {"a": 1.0}, "tolerance": {"abs": 1e300}})[0].ok


def test_extra_actual_values_are_not_compared():
    rows = compare({"a": 1.0, "zzz": 5.0}, {"source": "s", "values": {"a": 1.0}})
    assert [row.name for row in rows] == ["a"]


def test_a_value_that_is_not_a_number_is_refused():
    reference = {"source": "s", "values": {"a": 1.0}}
    for bad in (True, "1.0", None):
        with pytest.raises(ValueError, match="'a'"):
            compare({"a": bad}, reference)


def test_an_int_counts_as_a_number():
    assert compare({"a": 2}, {"source": "s", "values": {"a": 2}})[0].ok


def _write(tmp_path, ref):
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(ref), encoding="utf-8")
    return path


def test_a_good_reference_loads_unchanged(tmp_path):
    ref = {
        "source": "s",
        "values": {"a": 1, "b": 2.5},
        "tolerance": {"rel": 0.01, "abs": 0.0},
        "tolerances": {"b": {"rel": 0.0, "abs": 0.1}},
    }
    assert load_reference(_write(tmp_path, ref)) == ref
    assert load_reference(_write(tmp_path, {"source": "s", "values": {"a": 1}})) == {"source": "s", "values": {"a": 1}}


@pytest.mark.parametrize(
    "ref, fragment",
    [
        ({"values": {"a": 1}}, "source"),
        ({"source": "s", "values": {}}, "values"),
        ({"source": "s", "values": {"a": True}}, "a"),
        ({"source": "s", "values": {"a": 1}, "tolerance": {"rel": -1}}, "rel"),
        ({"source": "s", "values": {"a": 1}, "tolerances": {"b": {"rel": 0}}}, "b"),
        ({"source": "s", "values": {"a": 1}, "tolerence": {}}, "tolerence"),
    ],
)
def test_bad_reference_is_refused(tmp_path, ref, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_reference(_write(tmp_path, ref))


@pytest.mark.parametrize(
    "text, key",
    [
        ('{"values": {"a": 1}}', "'source'"),
        ('{"source": "", "values": {"a": 1}}', "'source'"),
        ('{"source": "s"}', "'values'"),
        ('{"source": "s", "values": []}', "'values'"),
        ('{"source": "s", "values": {"a": "1"}}', "'values.a'"),
        ('{"source": "s", "values": {"a": true}}', "'values.a'"),
        ('{"source": "s", "values": {"a": NaN}}', "'values.a'"),
        ('{"source": "s", "values": {"a": Infinity}}', "'values.a'"),
        ('{"source": "s", "values": {"a": 1e999}}', "'values.a'"),
        ('{"source": "s", "values": {"a": 1}, "tolerance": {"rel": -1}}', "'tolerance.rel'"),
        ('{"source": "s", "values": {"a": 1}, "tolerance": {"abs": NaN}}', "'tolerance.abs'"),
        ('{"source": "s", "values": {"a": 1}, "tolerance": {"abs": true}}', "'tolerance.abs'"),
        ('{"source": "s", "values": {"a": 1}, "tolerance": {"rell": 1}}', "'tolerance.rell'"),
        ('{"source": "s", "values": {"a": 1}, "tolerance": 0.1}', "'tolerance'"),
        ('{"source": "s", "values": {"a": 1}, "tolerances": {"b": {"rel": 0}}}', "'tolerances.b'"),
        ('{"source": "s", "values": {"a": 1}, "tolerances": {"a": {"abs": Infinity}}}', "'tolerances.a.abs'"),
        ('{"source": "s", "values": {"a": 1}, "tolerances": []}', "'tolerances'"),
        ('{"source": "s", "values": {"a": 1}, "extra": 1}', "'extra'"),
        ('{"source": "s", "source": "t", "values": {"a": 1}}', "'source'"),
        ("[1, 2]", "JSON object"),
        ("{not json", "not valid JSON"),
    ],
)
def test_the_refusal_names_the_offending_key(tmp_path, text, key):
    path = tmp_path / "reference.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        load_reference(path)
    assert key in str(caught.value) or key.strip("'") in str(caught.value)
    assert str(path) in str(caught.value)  # the file is named too


def test_a_reference_in_a_byte_order_mark_file_loads(tmp_path):
    path = tmp_path / "reference.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"source": "s", "values": {"a": 1}}).encode("utf-8"))
    assert load_reference(path)["values"] == {"a": 1}
