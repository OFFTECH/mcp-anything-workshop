"""Install MCP-Anything's optional permission hook for Claude Code. Standard library only.

    python3 -m workshop.permissions

The plugin ships `extras/allow_mcp_anything_scripts.py`, a Claude Code PreToolUse hook that approves a Bash call of the
plugin's own `scripts/*.py` (and nothing else), so that a participant is not asked dozens of times. A plugin cannot
install a hook into the user's settings itself, so this step does it: it copies the script to
`~/.claude/hooks/` and adds one entry to `hooks.PreToolUse` in `~/.claude/settings.json`, leaving everything else in
that file as it is. Running it again changes nothing. The entry's command ends in `|| true`, so that a missing or broken
script gives Claude Code no decision (the normal prompt applies) instead of exit code 2, which blocks every Bash call.
It never fails the setup: when it cannot install the hook it prints why, and Claude Code asks about every command as
usual.
"""

import argparse
import contextlib
import copy
import json
import os
import tempfile
from pathlib import Path

HOOK_NAME = "allow_mcp_anything_scripts.py"
HOOK_SOURCE = Path("extras") / HOOK_NAME  # inside the plugin
HOOK_MODE = 0o644
LEGACY_COMMAND = 'python3 "$HOME/.claude/hooks/allow_mcp_anything_scripts.py"'  # without `|| true`: upgraded when found
HOOK_COMMAND = LEGACY_COMMAND + " || true"  # fail open: a missing script must not exit 2, which Claude Code treats as a block
HOOK_ENTRY = {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}

HOOK_PATH = "~/.claude/hooks/" + HOOK_NAME  # as the log shows them
SETTINGS_PATH = "~/.claude/settings.json"
ADDED, UPDATED, KEPT = "added", "updated", "kept"  # what `add_hook_entry` did
INSTALLED = "permission hook installed"
NOT_INSTALLED = "permission hook not installed"
_NORMAL_PROMPTS = "participants will see the normal prompts"


def _not_installed(reason: str) -> str:
    return f"{NOT_INSTALLED}: {reason}; {_NORMAL_PROMPTS}"


def find_plugin_root(home: Path) -> Path | None:
    """The folder of the installed mcp-anything plugin (the one that holds METHOD.md), or None.

    The same search as `find ~/.claude/plugins -path '*mcp-anything*' -name METHOD.md` (INSTRUCTOR.md, C17). Claude
    Code keeps two copies: the marketplace clone and the installed one under `cache/`. The installed copy wins, then the
    newest.
    """
    plugins = home / ".claude" / "plugins"
    found = []
    try:
        for method in plugins.rglob("METHOD.md"):
            relative = method.relative_to(plugins)
            if "mcp-anything" in relative.as_posix() and method.is_file():
                found.append((relative.parts[0] != "cache", -method.stat().st_mtime, relative.as_posix(), method.parent))
    except OSError:
        return None
    return min(found)[3] if found else None


def _reject_constant(name: str):
    raise ValueError(f"is not strict JSON ({name})")


def _read_settings(path: Path) -> dict:
    """The settings as a dict ({} when the file is missing). Raises ValueError when it is not a strict JSON object."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError as error:
        raise ValueError(f"is not valid UTF-8 ({error.reason})") from error
    try:
        settings = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise ValueError(f"is not valid JSON ({error.msg}, line {error.lineno} column {error.colno})") from error
    if not isinstance(settings, dict):
        raise ValueError("is not a JSON object")
    return settings


def add_hook_entry(settings: dict) -> str:
    """Make `settings["hooks"]["PreToolUse"]` hold the hook: ADDED, UPDATED or KEPT (it was there already).

    An entry whose command is HOOK_COMMAND is the hook. One with LEGACY_COMMAND (no `|| true`) is the same hook, and
    is upgraded in place, not duplicated. Raises ValueError, with `settings` unchanged, when `hooks` is not an object
    or `hooks.PreToolUse` is not a list.
    """
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError('has a "hooks" that is not an object')
    pre_tool_use = hooks.get("PreToolUse", [])
    if not isinstance(pre_tool_use, list):
        raise ValueError('has a "hooks.PreToolUse" that is not a list')
    commands = [
        hook
        for entry in pre_tool_use
        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
        for hook in entry["hooks"]
        if isinstance(hook, dict) and hook.get("command") in (HOOK_COMMAND, LEGACY_COMMAND)
    ]
    if not commands:
        settings["hooks"] = hooks
        hooks["PreToolUse"] = [*pre_tool_use, copy.deepcopy(HOOK_ENTRY)]
        return ADDED
    old = [hook for hook in commands if hook["command"] == LEGACY_COMMAND]
    for hook in old:
        hook["command"] = HOOK_COMMAND
    return UPDATED if old else KEPT


def _write_atomic(path: Path, data: bytes, mode: int | None) -> None:
    """Write `path` through a temporary file in the same folder, then rename it over `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def install_hook(home: Path, plugin_root: Path | None) -> str:
    """Install the hook for the user `home` from the plugin folder `plugin_root`. Returns the line for the setup log.

    The line starts with "permission hook installed" or "permission hook not installed: <reason>". Nothing is raised
    for a missing plugin or script, a settings file that cannot be merged (it is left untouched) or a file that
    cannot be written: the setup goes on, and Claude Code asks about every command as usual.
    """
    if plugin_root is None:
        return _not_installed("the mcp-anything plugin was not found under ~/.claude/plugins")
    source = plugin_root / HOOK_SOURCE
    try:
        script = source.read_bytes()
    except FileNotFoundError:
        return _not_installed(f"the installed plugin has no {HOOK_SOURCE.as_posix()} (an older release)")
    except OSError as error:
        return _not_installed(f"cannot read {HOOK_SOURCE.as_posix()} of the plugin ({error.strerror or error})")

    settings_file = (home / ".claude" / "settings.json").resolve()  # a settings file that is a link stays a link
    try:
        settings = _read_settings(settings_file)
        done = add_hook_entry(settings)
    except OSError as error:
        return _not_installed(f"cannot read {SETTINGS_PATH} ({error.strerror or error}), left untouched")
    except ValueError as error:
        return _not_installed(f"{SETTINGS_PATH} {error}, left untouched")

    try:
        _write_atomic(home / ".claude" / "hooks" / HOOK_NAME, script, HOOK_MODE)
        if done != KEPT:
            mode = settings_file.stat().st_mode & 0o777 if settings_file.exists() else None
            text = json.dumps(settings, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            _write_atomic(settings_file, text.encode("utf-8"), mode)
    except OSError as error:
        return _not_installed(f"cannot write under ~/.claude ({error.strerror or error})")
    entry = {ADDED: "entry added to", UPDATED: "entry updated in", KEPT: "entry already in"}[done]
    return f"{INSTALLED}: {HOOK_PATH}, {entry} {SETTINGS_PATH}"


def main(argv: list[str] | None = None, home: Path | None = None) -> int:
    """Always 0: this step never fails the setup. `home` is for tests."""
    argparse.ArgumentParser(prog="python3 -m workshop.permissions", description=__doc__.split("\n\n")[0]).parse_args(argv)
    home = Path.home() if home is None else home
    print(install_hook(home, find_plugin_root(home)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
