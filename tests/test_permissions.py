"""The permission hook step: the script is copied and settings.json is merged, never overwritten, and nothing fails the setup."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from workshop import permissions

SCRIPT = b"#!/usr/bin/env python3\n# stands in for the plugin's hook script\n"
COMMAND = 'python3 "$HOME/.claude/hooks/allow_mcp_anything_scripts.py" || true'  # fails open: see the test at the end
LEGACY_COMMAND = 'python3 "$HOME/.claude/hooks/allow_mcp_anything_scripts.py"'
ENTRY = {"matcher": "Bash", "hooks": [{"type": "command", "command": COMMAND}]}
NORMAL_PROMPTS = "participants will see the normal prompts"
posix_only = pytest.mark.skipif(os.name == "nt", reason="file modes are a POSIX matter")


def _plugin(home: Path, *, hook: bool = True, where: str = "cache/mcp-anything/mcp-anything/0.1.0", script: bytes = SCRIPT) -> Path:
    """An installed plugin below `home`: a folder with METHOD.md, and with the hook script when `hook` is True."""
    root = home / ".claude" / "plugins" / where
    root.mkdir(parents=True, exist_ok=True)
    (root / "METHOD.md").write_text("# Method\n", encoding="utf-8")
    if hook:
        (root / "extras").mkdir(exist_ok=True)
        (root / "extras" / "allow_mcp_anything_scripts.py").write_bytes(script)
    return root


def _strict(text: str):
    """Parse as strict JSON: NaN and Infinity are refused."""

    def refuse(name):
        raise ValueError(name)

    return json.loads(text, parse_constant=refuse)


def _settings(home: Path):
    return _strict((home / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _write_settings(home: Path, content: str | bytes) -> Path:
    path = home / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def _leftovers(home: Path) -> list[str]:
    return sorted(p.name for folder in (home / ".claude", home / ".claude" / "hooks") if folder.is_dir() for p in folder.glob("*.tmp"))


def test_the_entry_is_the_one_claude_code_needs():
    assert permissions.HOOK_ENTRY == ENTRY
    assert permissions.HOOK_COMMAND == ENTRY["hooks"][0]["command"] == COMMAND
    assert permissions.LEGACY_COMMAND == LEGACY_COMMAND
    assert permissions.HOOK_PATH == "~/.claude/hooks/allow_mcp_anything_scripts.py"


def test_an_empty_home_gets_the_script_and_a_new_settings_file(tmp_path):
    root = _plugin(tmp_path)
    line = permissions.install_hook(tmp_path, root)
    assert line.startswith("permission hook installed")
    assert "entry added" in line
    assert (tmp_path / ".claude" / "hooks" / "allow_mcp_anything_scripts.py").read_bytes() == SCRIPT
    assert _settings(tmp_path) == {"hooks": {"PreToolUse": [ENTRY]}}
    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8").endswith("}\n")
    assert _leftovers(tmp_path) == []


@posix_only
def test_the_script_has_mode_0644_whatever_the_plugin_file_has(tmp_path):
    root = _plugin(tmp_path)
    (root / "extras" / "allow_mcp_anything_scripts.py").chmod(0o755)
    permissions.install_hook(tmp_path, root)
    assert stat.S_IMODE((tmp_path / ".claude" / "hooks" / "allow_mcp_anything_scripts.py").stat().st_mode) == 0o644


def test_existing_settings_and_hooks_are_kept(tmp_path):
    other_pre = {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo edit"}]}
    post = [{"matcher": "*", "hooks": [{"type": "command", "command": "echo done"}]}]
    before = {
        "model": "sonnet",
        "env": {"NOTE": "café ✓"},
        "permissions": {"allow": ["Bash(ls:*)"], "deny": []},
        "enabledPlugins": {"mcp-anything@mcp-anything": True},
        "hooks": {"PreToolUse": [other_pre], "PostToolUse": post},
    }
    _write_settings(tmp_path, json.dumps(before))
    assert permissions.install_hook(tmp_path, _plugin(tmp_path)).startswith("permission hook installed")
    after = _settings(tmp_path)
    assert after["hooks"]["PreToolUse"] == [other_pre, ENTRY]  # appended after the user's own
    assert after["hooks"]["PostToolUse"] == post
    assert {key: value for key, value in after.items() if key != "hooks"} == {key: value for key, value in before.items() if key != "hooks"}
    assert list(after) == list(before)  # same keys, same order
    assert "café ✓" in (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")  # not escaped
    assert _leftovers(tmp_path) == []


def test_settings_with_other_keys_but_no_hooks_get_the_hooks_object(tmp_path):
    _write_settings(tmp_path, '{"theme": "dark"}')
    permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert _settings(tmp_path) == {"theme": "dark", "hooks": {"PreToolUse": [ENTRY]}}


def test_a_second_run_changes_nothing(tmp_path):
    root = _plugin(tmp_path)
    _write_settings(tmp_path, json.dumps({"model": "sonnet", "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": []}]}}))
    first = permissions.install_hook(tmp_path, root)
    settings_file = tmp_path / ".claude" / "settings.json"
    stored = settings_file.read_bytes()
    second = permissions.install_hook(tmp_path, root)
    assert "entry added" in first
    assert second.startswith("permission hook installed") and "entry already in" in second
    assert settings_file.read_bytes() == stored
    assert _settings(tmp_path)["hooks"]["PreToolUse"].count(ENTRY) == 1
    assert len(_settings(tmp_path)["hooks"]["PreToolUse"]) == 2


def test_an_entry_with_the_same_command_under_another_matcher_is_not_added_again(tmp_path):
    mine = {"matcher": "*", "hooks": [{"type": "command", "command": permissions.HOOK_COMMAND}, {"type": "command", "command": "echo x"}]}
    _write_settings(tmp_path, json.dumps({"hooks": {"PreToolUse": [mine]}}))
    stored = (tmp_path / ".claude" / "settings.json").read_bytes()
    assert "entry already in" in permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert (tmp_path / ".claude" / "settings.json").read_bytes() == stored


def test_an_entry_without_or_true_is_upgraded_in_place_not_duplicated(tmp_path):
    """The command used to end at the script: a missing script then exited 2, which Claude Code treats as a block."""
    other = {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo edit"}]}
    old = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo first"}, {"type": "command", "command": LEGACY_COMMAND}]}
    before = {"model": "sonnet", "hooks": {"PreToolUse": [other, old], "PostToolUse": []}}
    _write_settings(tmp_path, json.dumps(before))
    root = _plugin(tmp_path)
    line = permissions.install_hook(tmp_path, root)
    assert line.startswith("permission hook installed") and "entry updated in" in line
    after = _settings(tmp_path)
    upgraded = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo first"}, {"type": "command", "command": COMMAND}]}
    assert after == {"model": "sonnet", "hooks": {"PreToolUse": [other, upgraded], "PostToolUse": []}}  # same place, one entry
    stored = (tmp_path / ".claude" / "settings.json").read_bytes()
    assert "entry already in" in permissions.install_hook(tmp_path, root)  # and now it is the hook as it should be
    assert (tmp_path / ".claude" / "settings.json").read_bytes() == stored
    assert (tmp_path / ".claude" / "hooks" / "allow_mcp_anything_scripts.py").read_bytes() == SCRIPT


def test_the_old_entry_alone_is_the_same_hook(tmp_path):
    _write_settings(tmp_path, json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": LEGACY_COMMAND}]}]}}))
    permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert _settings(tmp_path) == {"hooks": {"PreToolUse": [ENTRY]}}


def test_a_look_alike_command_is_not_the_hook(tmp_path):
    """Only the exact command (or the old one) counts: a command that merely mentions the script is left alone."""
    mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": LEGACY_COMMAND + " --debug"}]}
    _write_settings(tmp_path, json.dumps({"hooks": {"PreToolUse": [mine]}}))
    assert "entry added to" in permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert _settings(tmp_path)["hooks"]["PreToolUse"] == [mine, ENTRY]


def test_a_second_run_takes_the_newer_script_of_the_plugin(tmp_path):
    root = _plugin(tmp_path)
    permissions.install_hook(tmp_path, root)
    (root / "extras" / "allow_mcp_anything_scripts.py").write_bytes(SCRIPT + b"# newer\n")
    permissions.install_hook(tmp_path, root)
    assert (tmp_path / ".claude" / "hooks" / "allow_mcp_anything_scripts.py").read_bytes() == SCRIPT + b"# newer\n"


@posix_only
def test_the_mode_of_an_existing_settings_file_is_kept(tmp_path):
    path = _write_settings(tmp_path, "{}")
    path.chmod(0o640)
    permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_a_missing_plugin_is_said_and_nothing_is_written(tmp_path):
    line = permissions.install_hook(tmp_path, None)
    assert line.startswith("permission hook not installed: ")
    assert "plugin was not found" in line
    assert line.endswith(NORMAL_PROMPTS)
    assert not (tmp_path / ".claude").exists()


def test_a_plugin_without_the_hook_script_is_said_and_nothing_is_written(tmp_path):
    """An older release has no extras/ folder."""
    line = permissions.install_hook(tmp_path, _plugin(tmp_path, hook=False))
    assert line.startswith("permission hook not installed: ")
    assert "extras/allow_mcp_anything_scripts.py" in line and "older release" in line
    assert line.endswith(NORMAL_PROMPTS)
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".claude" / "hooks").exists()


def test_a_plugin_folder_that_is_gone_is_the_same_as_a_missing_script(tmp_path):
    line = permissions.install_hook(tmp_path, tmp_path / "nowhere")
    assert line.startswith("permission hook not installed: ") and line.endswith(NORMAL_PROMPTS)


@pytest.mark.parametrize(
    "content, said",
    [
        ('{"model": "sonnet",', "is not valid JSON"),  # cut off
        ("", "is not valid JSON"),
        ("{'model': 'sonnet'}", "is not valid JSON"),
        ('{"model": "sonnet",}', "is not valid JSON"),  # trailing comma
        ('{"budget": NaN}', "is not strict JSON"),
        (b"\xff\xfe{}", "is not valid UTF-8"),
        ("[1, 2]", "is not a JSON object"),
        ('{"hooks": []}', 'has a "hooks" that is not an object'),
        ('{"hooks": {"PreToolUse": {}}}', 'has a "hooks.PreToolUse" that is not a list'),
    ],
)
def test_a_settings_file_that_cannot_be_merged_is_left_untouched(tmp_path, content, said):
    path = _write_settings(tmp_path, content)
    stored = path.read_bytes()
    line = permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert line.startswith("permission hook not installed: ~/.claude/settings.json ")
    assert said in line
    assert "left untouched" in line
    assert line.endswith(NORMAL_PROMPTS)
    assert path.read_bytes() == stored
    assert not (tmp_path / ".claude" / "hooks").exists()  # no script without its entry
    assert _leftovers(tmp_path) == []


def test_a_write_that_fails_is_said_and_does_not_raise(tmp_path, monkeypatch):
    def refuse(path, data, mode):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(permissions, "_write_atomic", refuse)
    line = permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert line.startswith("permission hook not installed: cannot write")
    assert "Permission denied" in line and line.endswith(NORMAL_PROMPTS)


def test_a_failed_write_leaves_the_old_file_and_no_temporary_file(tmp_path, monkeypatch):
    path = _write_settings(tmp_path, '{"model": "sonnet"}')

    def broken_replace(source, target):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(permissions.os, "replace", broken_replace)
    line = permissions.install_hook(tmp_path, _plugin(tmp_path))
    assert line.startswith("permission hook not installed: cannot write")
    assert path.read_text(encoding="utf-8") == '{"model": "sonnet"}'
    assert _leftovers(tmp_path) == []


def test_add_hook_entry_changes_nothing_when_it_refuses():
    settings = {"hooks": {"PreToolUse": "no"}}
    with pytest.raises(ValueError):
        permissions.add_hook_entry(settings)
    assert settings == {"hooks": {"PreToolUse": "no"}}


def test_add_hook_entry_never_shares_the_constant_with_the_settings():
    settings: dict = {}
    assert permissions.add_hook_entry(settings) == permissions.ADDED
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "changed"
    assert permissions.HOOK_ENTRY == ENTRY


def test_the_installed_plugin_is_found_the_way_the_instructor_finds_it(tmp_path):
    assert permissions.find_plugin_root(tmp_path) is None  # no ~/.claude/plugins at all
    other = _plugin(tmp_path, where="cache/other/other/1.0.0")
    assert permissions.find_plugin_root(tmp_path) is None  # a METHOD.md of another plugin
    clone = _plugin(tmp_path, where="marketplaces/mcp-anything")
    assert permissions.find_plugin_root(tmp_path) == clone
    installed = _plugin(tmp_path, where="cache/mcp-anything/mcp-anything/0.1.0")
    assert permissions.find_plugin_root(tmp_path) == installed  # the installed copy, not the marketplace clone
    assert other != installed


def test_the_newest_installed_copy_wins(tmp_path):
    old = _plugin(tmp_path, where="cache/mcp-anything/mcp-anything/0.1.0")
    new = _plugin(tmp_path, where="cache/mcp-anything/mcp-anything/0.2.0")
    os.utime(old / "METHOD.md", (1_000_000_000, 1_000_000_000))
    os.utime(new / "METHOD.md", (1_700_000_000, 1_700_000_000))
    assert permissions.find_plugin_root(tmp_path) == new
    os.utime(new / "METHOD.md", (900_000_000, 900_000_000))
    assert permissions.find_plugin_root(tmp_path) == old


def test_main_installs_for_the_given_home_and_prints_one_line(tmp_path, capsys):
    _plugin(tmp_path)
    assert permissions.main([], home=tmp_path) == 0
    out = capsys.readouterr().out
    assert out.startswith("permission hook installed: ~/.claude/hooks/allow_mcp_anything_scripts.py")
    assert len(out.splitlines()) == 1
    assert _settings(tmp_path)["hooks"]["PreToolUse"] == [ENTRY]


@pytest.mark.parametrize("problem", ["no plugin", "old plugin", "broken settings"])
def test_main_never_fails_the_setup(tmp_path, capsys, problem):
    if problem == "old plugin":
        _plugin(tmp_path, hook=False)
    elif problem == "broken settings":
        _plugin(tmp_path)
        _write_settings(tmp_path, "{")
    assert permissions.main([], home=tmp_path) == 0
    out = capsys.readouterr().out
    assert out.startswith("permission hook not installed: ") and out.rstrip().endswith(NORMAL_PROMPTS)


def test_main_uses_the_home_of_the_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _plugin(tmp_path)
    assert permissions.main([]) == 0
    assert capsys.readouterr().out.startswith("permission hook installed")
    assert _settings(tmp_path) == {"hooks": {"PreToolUse": [ENTRY]}}


def test_the_command_fails_open_when_the_script_is_missing_or_crashes(tmp_path):
    """Exit code 2 from a hook blocks the Bash call; `|| true` turns a missing or crashing script into no decision."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("needs bash")
    env = {**os.environ, "HOME": str(tmp_path)}
    run = [bash, "-c", permissions.HOOK_COMMAND]
    done = subprocess.run(run, input=b"{}", capture_output=True, env=env, timeout=60)
    assert (done.returncode, done.stdout) == (0, b"")  # no script at all
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "allow_mcp_anything_scripts.py").write_text("raise SystemExit(2)", encoding="utf-8")
    done = subprocess.run(run, input=b"{}", capture_output=True, env=env, timeout=60)
    assert (done.returncode, done.stdout) == (0, b"")  # a script that exits 2
    (hooks / "allow_mcp_anything_scripts.py").write_text("print('no closing quote", encoding="utf-8")
    done = subprocess.run(run, input=b"{}", capture_output=True, env=env, timeout=60)
    assert (done.returncode, done.stdout) == (0, b"")  # a script that does not even compile


def test_the_command_still_lets_a_working_script_speak(tmp_path):
    bash, python = shutil.which("bash"), shutil.which("python3")
    if bash is None or python is None or subprocess.run([python, "-c", "pass"], capture_output=True).returncode != 0:
        pytest.skip("needs bash and a working python3")
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "allow_mcp_anything_scripts.py").write_text("print('{\"decision\": \"allow\"}')", encoding="utf-8")
    done = subprocess.run(
        [bash, "-c", permissions.HOOK_COMMAND], input=b"{}", capture_output=True, env={**os.environ, "HOME": str(tmp_path)}, timeout=60
    )
    assert done.returncode == 0 and json.loads(done.stdout) == {"decision": "allow"}
