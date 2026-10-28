"""Install the MCP-Anything plugin with the documented `claude plugin` commands. Standard library only.

    python3 -m workshop.plugin [install|print|status]

The plugin repository comes from workshop.conf (`MCP_ANYTHING_REPO`) and is never used while it is still the placeholder.
"""

import argparse
import re
import shlex
import sys
from pathlib import Path

from workshop.config import CONF_PATH, ROOT, is_placeholder, mcp_anything_repo
from workshop.proc import Runner, run_process

MARKETPLACE = "mcp-anything"
PLUGIN_ID = "mcp-anything@mcp-anything"  # name@marketplace, both named in the plugin repository's marketplace.json

INSTALL_TIMEOUT_S = 300.0  # `marketplace add` clones the plugin repository
LIST_TIMEOUT_S = 60.0
PLACEHOLDER_MESSAGE = "set MCP_ANYTHING_REPO in workshop.conf (INSTRUCTOR.md, step 3)"

# the id as a whole word: not part of a longer plugin or marketplace name
_ID_RE = re.compile(r"(?<![\w.@-])" + re.escape(PLUGIN_ID) + r"(?![\w@-]|\.\w)")


def shell_commands(repo: str) -> list[list[str]]:
    """The two shell commands that register the marketplace and install the plugin (user scope)."""
    return [["claude", "plugin", "marketplace", "add", repo], ["claude", "plugin", "install", PLUGIN_ID]]


def slash_commands(repo: str) -> list[str]:
    """The same two steps typed inside Claude Code: the fallback when the shell commands do not work."""
    return ["/plugin marketplace add " + repo, "/plugin install " + PLUGIN_ID]


def remove_command() -> list[str]:
    """Remove the marketplace (the way to move an installed plugin to another ref, before `install` runs again)."""
    return ["claude", "plugin", "marketplace", "remove", MARKETPLACE]


def ref_line(repo: str) -> str:
    """What workshop.conf asks for: the repository and its ref (`owner/name#ref`), or the default branch without one."""
    name, _, ref = repo.partition("#")
    return f"workshop.conf names {name}, " + (f"ref {ref}" if ref else "no ref (the default branch)")


def not_updated_note() -> str:
    """Said when the plugin was installed before `install` ran: `installed()` knows the plugin's name, not its ref."""
    return (
        f"The plugin {PLUGIN_ID} was installed already. `install` does not update an installed plugin, and it cannot tell "
        f"which ref the installed one came from. If workshop.conf has changed since (a corrected repository, a new tag), "
        f"move this codespace over: `git pull`, then `{shlex.join(remove_command())}`, then "
        "`python3 -m workshop.plugin install` again."
    )


def installed(run: Runner) -> bool:
    """True when `claude plugin list` exits 0 and lists the plugin (`name@marketplace`).

    A missing `claude` raises FileNotFoundError.
    """
    done = run(["claude", "plugin", "list"], ROOT, LIST_TIMEOUT_S)
    return done.returncode == 0 and _ID_RE.search(done.output) is not None


def _configured_repo(conf: Path) -> str | None:
    """The repository from workshop.conf, or None after printing why it cannot be used."""
    try:
        repo = mcp_anything_repo(conf)
    except (OSError, ValueError) as error:
        print(f"workshop.conf cannot be used: {error}", file=sys.stderr)
        return None
    if is_placeholder(repo):
        print(PLACEHOLDER_MESSAGE, file=sys.stderr)
        return None
    return repo


def _no_claude(error: OSError) -> None:
    if isinstance(error, FileNotFoundError):
        print("the 'claude' command was not found: open a new terminal, or ask the instructor", file=sys.stderr)
    else:  # for example PermissionError
        print(f"the 'claude' command could not be run: {error}", file=sys.stderr)


def _install(run: Runner, conf: Path) -> int:
    repo = _configured_repo(conf)
    if repo is None:
        return 2
    print(ref_line(repo), flush=True)
    try:
        was_installed = installed(run)
        for argv in shell_commands(repo):
            print("$ " + shlex.join(argv), flush=True)
            done = run(argv, ROOT, INSTALL_TIMEOUT_S)
            if done.output.strip():
                print(done.output.rstrip())
            # a failing command does not stop the next one: "already added" also exits non-zero, and the check decides
        ok = installed(run)
    except OSError as error:
        _no_claude(error)
        return 1
    if ok:
        print(f"The plugin {PLUGIN_ID} is installed.")
        if was_installed:
            print(not_updated_note())
        return 0
    print(f"The plugin {PLUGIN_ID} is not installed. Start `claude` and type these two lines instead:")
    for line in slash_commands(repo):
        print("  " + line)
    return 1


def _print(conf: Path) -> int:
    repo = _configured_repo(conf)
    if repo is None:
        return 2
    for line in slash_commands(repo):
        print(line)
    return 0


def _status(run: Runner) -> int:
    try:
        ok = installed(run)
    except OSError as error:
        _no_claude(error)
        return 1
    print(f"The plugin {PLUGIN_ID} is {'installed' if ok else 'not installed'}.")
    return 0 if ok else 1


def main(argv: list[str] | None = None, run: Runner = run_process, conf: Path = CONF_PATH) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m workshop.plugin", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "command",
        nargs="?",
        default="install",
        choices=("install", "print", "status"),
        help="install (the default): run the two claude commands and check (it does not update a plugin that is installed "
        "already); print: show the two lines to type in Claude Code; status: is the plugin installed?",
    )
    command = parser.parse_args(argv).command
    if command == "print":
        return _print(conf)
    if command == "status":
        return _status(run)
    return _install(run, conf)


if __name__ == "__main__":
    raise SystemExit(main())
