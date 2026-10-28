"""Plugin installation through the documented `claude plugin` commands, with the repository from workshop.conf."""

from pathlib import Path

import pytest

from workshop import config, plugin
from workshop.proc import Completed

REPO = "acme/mcp-anything#v0.1.0"
LISTED = "Installed plugins:\n\n  > mcp-anything@mcp-anything\n    Version: 0.1.0\n    Status: ✔ enabled\n"
ADD = ["claude", "plugin", "marketplace", "add", REPO]
INSTALL = ["claude", "plugin", "install", "mcp-anything@mcp-anything"]
LIST = ["claude", "plugin", "list"]
NONE_LISTED = Completed(0, "No plugins installed\n")
REMOVE = "claude plugin marketplace remove mcp-anything"


def _conf(tmp_path: Path, repo: str) -> Path:
    path = tmp_path / "workshop.conf"
    path.write_text(f"MCP_ANYTHING_REPO={repo}\n", encoding="utf-8", newline="\n")
    return path


class Recorder:
    """A fake runner: records every call and answers from `answers` (argv tuple -> Completed) or with `default`.

    An answer that is a list is used up one call at a time (the last one is kept for the calls after that).
    """

    def __init__(self, answers=None, default=Completed(0, ""), raises=None):
        self.calls: list[list[str]] = []
        self.answers = answers or {}
        self.default = default
        self.raises = raises

    def __call__(self, argv, cwd, timeout_s):
        assert isinstance(cwd, Path) and timeout_s > 0
        self.calls.append(list(argv))
        if self.raises is not None:
            raise self.raises
        answer = self.answers.get(tuple(argv), self.default)
        if isinstance(answer, list):
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return answer


def test_names_are_the_documented_install_id():
    assert plugin.MARKETPLACE == "mcp-anything"
    assert plugin.PLUGIN_ID == "mcp-anything@mcp-anything"


def test_commands_use_the_configured_repository(tmp_path):
    assert plugin.shell_commands(REPO) == [ADD, INSTALL]
    assert plugin.slash_commands(REPO) == [
        "/plugin marketplace add acme/mcp-anything#v0.1.0",
        "/plugin install mcp-anything@mcp-anything",
    ]


def test_placeholder_stops_install_with_exit_2(tmp_path, capsys):
    run = Recorder()
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, config.PLACEHOLDER)) == 2
    assert plugin.main([], run=run, conf=_conf(tmp_path, config.PLACEHOLDER + "#v1")) == 2  # install is the default
    assert run.calls == []  # the placeholder is never passed to a program
    err = capsys.readouterr().err
    assert "set MCP_ANYTHING_REPO in workshop.conf (INSTRUCTOR.md, step 3)" in err
    assert config.PLACEHOLDER not in err


def test_a_broken_conf_stops_install_with_exit_2(tmp_path, capsys):
    run = Recorder()
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, "not a repository")) == 2
    assert "workshop.conf" in capsys.readouterr().err
    assert plugin.main(["install"], run=run, conf=tmp_path / "missing.conf") == 2
    assert "workshop.conf" in capsys.readouterr().err
    assert run.calls == []


def test_install_runs_both_commands_then_checks(tmp_path, capsys):
    run = Recorder({tuple(LIST): [NONE_LISTED, Completed(0, LISTED)], tuple(ADD): Completed(0, "added the marketplace\n")})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 0
    assert run.calls == [LIST, ADD, INSTALL, LIST]  # the first LIST: was it installed before?
    out = capsys.readouterr().out
    assert "added the marketplace" in out
    assert "is installed." in out
    assert "does not update" not in out  # nothing was installed before: nothing to warn about


def test_install_says_which_ref_workshop_conf_names(tmp_path, capsys):
    """The instructor and the participant see what the file asks for, before anything is run."""
    run = Recorder({tuple(LIST): [NONE_LISTED, Completed(0, LISTED)]})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 0
    out = capsys.readouterr().out
    assert "workshop.conf names acme/mcp-anything, ref v0.1.0" in out
    assert out.index("workshop.conf names") < out.index("$ claude plugin marketplace add")
    run = Recorder({tuple(LIST): [NONE_LISTED, Completed(0, LISTED)]})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, "acme/mcp-anything")) == 0
    assert "workshop.conf names acme/mcp-anything, no ref (the default branch)" in capsys.readouterr().out


def test_an_installed_plugin_is_not_updated_and_install_says_so_plainly(tmp_path, capsys):
    """`installed()` checks the plugin name, not the ref: `install` cannot move a codespace to another tag."""
    run = Recorder({tuple(LIST): Completed(0, LISTED)})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 0
    assert run.calls == [LIST, ADD, INSTALL, LIST]
    out = " ".join(capsys.readouterr().out.split())
    assert "workshop.conf names acme/mcp-anything, ref v0.1.0" in out
    assert "was installed already" in out
    assert "does not update an installed plugin" in out
    assert "cannot tell which ref" in out
    assert REMOVE in out  # the way out, with the command spelled out
    assert "python3 -m workshop.plugin install" in out  # and then install again


def test_the_not_updated_note_is_not_printed_when_the_install_failed(tmp_path, capsys):
    run = Recorder({tuple(LIST): NONE_LISTED})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 1
    out = capsys.readouterr().out
    assert "does not update" not in out
    assert "workshop.conf names acme/mcp-anything, ref v0.1.0" in out


def test_the_ref_line_is_not_printed_for_the_placeholder(tmp_path, capsys):
    plugin.main(["install"], run=Recorder(), conf=_conf(tmp_path, config.PLACEHOLDER + "#v1"))
    captured = capsys.readouterr()
    assert "workshop.conf names" not in captured.out + captured.err


def test_the_remove_command_names_the_marketplace_of_the_install_id():
    assert plugin.remove_command() == ["claude", "plugin", "marketplace", "remove", plugin.MARKETPLACE]
    assert " ".join(plugin.remove_command()) == REMOVE


def test_install_failure_prints_the_fallback(tmp_path, capsys):
    run = Recorder({tuple(LIST): Completed(0, "No plugins installed\n")})
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 1
    assert run.calls == [LIST, ADD, INSTALL, LIST]  # a failing first command does not skip the second
    out = capsys.readouterr().out
    for line in plugin.slash_commands(REPO):
        assert line in out


def test_a_failing_command_still_leads_to_the_check(tmp_path):
    run = Recorder({tuple(ADD): Completed(1, "already exists"), tuple(LIST): Completed(0, LISTED)})
    assert plugin.main([], run=run, conf=_conf(tmp_path, REPO)) == 0  # already installed earlier: still fine


def test_missing_claude_is_exit_1(tmp_path, capsys):
    run = Recorder(raises=FileNotFoundError("claude"))
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 1
    assert plugin.main(["status"], run=run, conf=_conf(tmp_path, REPO)) == 1
    assert "claude" in capsys.readouterr().err


def test_a_missing_claude_sends_the_participant_to_the_instructor_not_to_the_instructor_notes(tmp_path, capsys):
    """INSTRUCTOR.md says participants never need it."""
    assert plugin.main(["status"], run=Recorder(raises=FileNotFoundError("claude")), conf=_conf(tmp_path, REPO)) == 1
    err = capsys.readouterr().err
    assert "open a new terminal, or ask the instructor" in err
    assert "INSTRUCTOR" not in err


def test_a_claude_that_cannot_be_run_is_exit_1_without_a_traceback(tmp_path, capsys):
    run = Recorder(raises=PermissionError(13, "Permission denied", "claude"))
    assert plugin.main(["install"], run=run, conf=_conf(tmp_path, REPO)) == 1
    assert plugin.main(["status"], run=run, conf=_conf(tmp_path, REPO)) == 1
    assert "Permission denied" in capsys.readouterr().err


def test_print_shows_the_slash_commands(tmp_path, capsys):
    run = Recorder()
    assert plugin.main(["print"], run=run, conf=_conf(tmp_path, REPO)) == 0
    assert run.calls == []
    assert capsys.readouterr().out.splitlines() == plugin.slash_commands(REPO)


def test_print_stops_on_the_placeholder(tmp_path, capsys):
    assert plugin.main(["print"], run=Recorder(), conf=_conf(tmp_path, config.PLACEHOLDER)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "workshop.conf" in captured.err


def test_status_reports_installed_or_not(tmp_path):
    conf = _conf(tmp_path, config.PLACEHOLDER)  # status does not need the repository
    assert plugin.main(["status"], run=Recorder({tuple(LIST): Completed(0, LISTED)}), conf=conf) == 0
    assert plugin.main(["status"], run=Recorder({tuple(LIST): Completed(0, "none")}), conf=conf) == 1


def test_unknown_subcommand_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stop:
        plugin.main(["frobnicate"], run=Recorder(), conf=_conf(tmp_path, REPO))
    assert stop.value.code == 2


@pytest.mark.parametrize(
    "done, expected",
    [
        (Completed(0, LISTED), True),
        (Completed(0, "mcp-anything@mcp-anything"), True),
        (Completed(1, LISTED), False),  # a failing command is not evidence
        (Completed(None, LISTED + "\n[timed out after 60 s]"), False),
        (Completed(0, "No plugins installed"), False),
        (Completed(0, "other@mcp-anything\nmcp-anything@other"), False),
        (Completed(0, "mcp-anything@mcp-anything-old"), False),  # another plugin whose id starts the same
        (Completed(0, "old-mcp-anything@mcp-anything"), False),
    ],
)
def test_installed_needs_a_clean_exit_and_the_exact_id(done, expected):
    run = Recorder({tuple(LIST): done})
    assert plugin.installed(run) is expected
    assert run.calls == [LIST]
