"""The tool check: every probe is a fake answer; nothing real is run."""

from pathlib import Path

import pytest

from workshop import check_tools, config
from workshop.check_tools import EXPECTED, Row
from workshop.proc import Completed

CCX_NOTE = "exits 201 after printing its version; MCP-Anything needs version_exit_codes=(0, 201) (exercise 01)"
PLUGIN_LISTED = "  > mcp-anything@mcp-anything\n    Version: 0.1.0\n    Status: ✔ enabled\n"

PROBES = [  # (row, argv), in the order check() must run them
    ("calculix-ccx", ("dpkg-query", "-W", "-f=${Version}", "calculix-ccx")),
    ("ccx", ("ccx", "-v")),
    ("gmsh", ("gmsh", "--version")),
    ("python3", ("python3", "--version")),
    ("uv", ("uv", "--version")),
    ("node", ("node", "--version")),
    ("npm", ("npm", "--version")),
    ("claude", ("claude", "--version")),
    ("git", ("git", "--version")),
    ("mcp-anything plugin", ("claude", "plugin", "list")),
]


def good_answers() -> dict:
    return {
        PROBES[0][1]: Completed(0, "2.21-1"),
        PROBES[1][1]: Completed(201, "\n  This is Version 2.21\n\n"),
        PROBES[2][1]: Completed(0, "4.12.1\n"),
        PROBES[3][1]: Completed(0, "Python 3.12.3\n"),
        PROBES[4][1]: Completed(0, "uv 0.13.5 (abcdef012 2026-10-01)\n"),
        PROBES[5][1]: Completed(0, "v24.11.0\n"),
        PROBES[6][1]: Completed(0, "11.6.1\n"),
        PROBES[7][1]: Completed(0, "2.1.308 (Claude Code)\n"),
        PROBES[8][1]: Completed(0, "git version 2.43.0\n"),
        PROBES[9][1]: Completed(0, PLUGIN_LISTED),
    }


class Fake:
    """A runner that answers from a dict; a program that is not in the dict is not installed."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, cwd, timeout_s):
        assert isinstance(cwd, Path) and timeout_s > 0
        self.calls.append(tuple(argv))
        try:
            answer = self.answers[tuple(argv)]
        except KeyError:
            raise FileNotFoundError(argv[0]) from None
        if isinstance(answer, BaseException):
            raise answer
        return answer


def by_tool(rows) -> dict:
    return {row.tool: row for row in rows}


def _conf(tmp_path, repo="acme/mcp-anything"):
    path = tmp_path / "workshop.conf"
    path.write_text(f"MCP_ANYTHING_REPO={repo}\n", encoding="utf-8", newline="\n")
    return path


def test_expected_versions_are_pinned():
    assert EXPECTED == {
        "calculix-ccx": "2.21-1",
        "gmsh": "4.12.1",
        "python3": "3.12.",
        "uv": "0.13.5",
        "node": "v24.",
        "claude": "2.1.308",
    }


def test_all_expected_versions_are_ok():
    fake = Fake(good_answers())
    rows = check_tools.check(fake)
    assert [r.tool for r in rows] == [name for name, _ in PROBES]
    assert fake.calls == [argv for _, argv in PROBES]
    assert [r.status for r in rows] == ["OK"] * len(PROBES), rows
    assert all(isinstance(r, Row) for r in rows)


def test_ccx_201_with_a_version_is_ok_and_without_one_fails():
    def ccx(done):
        answers = good_answers()
        answers[("ccx", "-v")] = done
        return by_tool(check_tools.check(Fake(answers)))["ccx"]

    ok = ccx(Completed(201, "This is Version 2.21\n"))
    assert ok.status == "OK"
    assert ok.note == CCX_NOTE
    assert "201" in ok.found and "2.21" in ok.found
    assert ccx(Completed(0, "This is Version 2.21\n")).status == "OK"  # a future build that exits 0
    assert ccx(Completed(201, "")).status == "FAIL"  # exit 201 alone is no evidence of a working ccx
    assert ccx(Completed(201, "*ERROR in ccx: no input\n")).status == "FAIL"
    assert ccx(Completed(3, "This is Version 2.21\n")).status == "WARN"
    assert ccx(Completed(0, "")).status == "FAIL"
    assert ccx(Completed(201, "This is Version\n2.21\n")).status == "FAIL"  # the version is on the same line
    assert ccx(Completed(201, "This is Version \t 2.21\n")).status == "OK"
    assert ccx(Completed(201, "This is Version 2.20\n")).status == "WARN"  # another version
    assert ccx(Completed(None, "This is Version 2.21\n[timed out after 30 s]")).status == "FAIL"


def test_missing_tool_fails_and_exit_code_is_1(capsys, tmp_path):
    for name, argv in PROBES[:9]:
        if name in ("ccx", "mcp-anything plugin"):
            continue
        answers = good_answers()
        del answers[argv]
        row = by_tool(check_tools.check(Fake(answers)))[name]
        assert (row.status, row.note) == ("FAIL", "not installed"), name
    answers = good_answers()
    del answers[("gmsh", "--version")]
    assert check_tools.main([], run=Fake(answers), conf=_conf(tmp_path)) == 1
    assert "gmsh" in capsys.readouterr().out


def test_a_non_zero_exit_is_not_installed():
    answers = good_answers()
    answers[("dpkg-query", "-W", "-f=${Version}", "calculix-ccx")] = Completed(1, "dpkg-query: no packages found")
    answers[("git", "--version")] = Completed(127, "")
    rows = by_tool(check_tools.check(Fake(answers)))
    assert (rows["calculix-ccx"].status, rows["calculix-ccx"].note) == ("FAIL", "not installed")
    assert rows["git"].status == "FAIL"


def test_a_program_that_cannot_be_run_is_a_fail_row_not_a_traceback(tmp_path, capsys):
    for name, argv in PROBES[:9]:
        answers = good_answers()
        answers[argv] = PermissionError(13, "Permission denied", argv[0])
        rows = by_tool(check_tools.check(Fake(answers)))
        assert rows[name].status == "FAIL", name
        assert "permission denied" in rows[name].note.lower(), name
        assert check_tools.main([], run=Fake(answers), conf=_conf(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "Traceback" not in out
    answers = good_answers()
    answers[("gmsh", "--version")] = OSError(8, "Exec format error", "gmsh")
    row = by_tool(check_tools.check(Fake(answers)))["gmsh"]
    assert row.status == "FAIL" and "Exec format error" in row.note


def test_the_plugin_row_survives_a_claude_that_cannot_be_run():
    answers = good_answers()
    answers[("claude", "plugin", "list")] = PermissionError(13, "Permission denied", "claude")
    assert by_tool(check_tools.check(Fake(answers)))["mcp-anything plugin"].status == "WARN"


def test_missing_ccx_fails():
    answers = good_answers()
    del answers[("ccx", "-v")]
    row = by_tool(check_tools.check(Fake(answers)))["ccx"]
    assert (row.status, row.note) == ("FAIL", "not installed")


@pytest.mark.parametrize(
    "tool, argv, answer",
    [
        ("calculix-ccx", ("dpkg-query", "-W", "-f=${Version}", "calculix-ccx"), "2.19-2"),
        ("gmsh", ("gmsh", "--version"), "4.8.4\n"),
        ("python3", ("python3", "--version"), "Python 3.10.12\n"),
        ("uv", ("uv", "--version"), "uv 0.9.0\n"),
        ("node", ("node", "--version"), "v20.11.0\n"),
        ("claude", ("claude", "--version"), "2.0.1 (Claude Code)\n"),
    ],
)
def test_another_version_is_a_warning(tool, argv, answer):
    answers = good_answers()
    answers[argv] = Completed(0, answer)
    row = by_tool(check_tools.check(Fake(answers)))[tool]
    assert row.status == "WARN"
    assert answer.strip().splitlines()[0] in row.found
    assert EXPECTED[tool] in row.note


def test_gmsh_version_must_start_the_first_line():
    answers = good_answers()
    answers[("gmsh", "--version")] = Completed(0, "warning: something\n4.12.1\n")
    assert by_tool(check_tools.check(Fake(answers)))["gmsh"].status == "WARN"


def test_the_plugin_row_is_a_warning_when_it_is_not_installed():
    answers = good_answers()
    answers[("claude", "plugin", "list")] = Completed(0, "No plugins installed\n")
    row = by_tool(check_tools.check(Fake(answers)))["mcp-anything plugin"]
    assert row.status == "WARN"
    assert "workshop.plugin" in row.note
    del answers[("claude", "plugin", "list")]  # no claude at all: the claude row fails, this one stays a warning
    rows = by_tool(check_tools.check(Fake(answers)))
    assert rows["mcp-anything plugin"].status == "WARN"


def test_main_prints_the_table_and_workshop_root(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSHOP_ROOT", "/workspaces/workshop")
    assert check_tools.main([], run=Fake(good_answers()), conf=_conf(tmp_path)) == 0
    out = capsys.readouterr().out
    for name, _ in PROBES:
        assert name in out
    assert "WORKSHOP_ROOT: /workspaces/workshop" in out
    monkeypatch.delenv("WORKSHOP_ROOT")
    assert check_tools.main([], run=Fake(good_answers()), conf=_conf(tmp_path)) == 0
    assert "WORKSHOP_ROOT: (not set: open a new terminal)" in capsys.readouterr().out
    monkeypatch.setenv("WORKSHOP_ROOT", "")
    check_tools.main([], run=Fake(good_answers()), conf=_conf(tmp_path))
    assert "(not set: open a new terminal)" in capsys.readouterr().out


def test_a_warning_alone_does_not_fail_the_check(tmp_path):
    answers = good_answers()
    answers[("node", "--version")] = Completed(0, "v20.11.0\n")
    assert check_tools.main([], run=Fake(answers), conf=_conf(tmp_path)) == 0


def test_without_ready_the_placeholder_and_the_plugin_are_not_checked(tmp_path):
    answers = good_answers()
    answers[("claude", "plugin", "list")] = Completed(0, "No plugins installed\n")
    assert check_tools.main([], run=Fake(answers), conf=_conf(tmp_path, config.PLACEHOLDER)) == 0


def test_ready_fails_on_the_placeholder(tmp_path, capsys):
    run = Fake(good_answers())
    assert check_tools.main(["--ready"], run=run, conf=_conf(tmp_path, config.PLACEHOLDER)) == 1
    out = capsys.readouterr().out
    assert "workshop.conf" in out and "FAIL" in out
    assert config.PLACEHOLDER not in out
    assert check_tools.main(["--ready"], run=run, conf=_conf(tmp_path, config.PLACEHOLDER + "#v1")) == 1
    assert check_tools.main(["--ready"], run=run, conf=_conf(tmp_path, "acme/mcp-anything#v0.1.0")) == 0


def test_ready_fails_when_the_plugin_is_missing_and_when_the_conf_is_broken(tmp_path):
    answers = good_answers()
    answers[("claude", "plugin", "list")] = Completed(0, "No plugins installed\n")
    assert check_tools.main(["--ready"], run=Fake(answers), conf=_conf(tmp_path)) == 1
    assert check_tools.main(["--ready"], run=Fake(good_answers()), conf=tmp_path / "missing.conf") == 1
    assert check_tools.main(["--ready"], run=Fake(good_answers()), conf=_conf(tmp_path, "nonsense")) == 1


def test_unknown_option_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stop:
        check_tools.main(["--frobnicate"], run=Fake(good_answers()), conf=_conf(tmp_path))
    assert stop.value.code == 2
