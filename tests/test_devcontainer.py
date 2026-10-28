"""The dev container: its pins agree with the tool check, and the post-create script never blocks the codespace.

The container cannot be built here. These tests read the three files statically, from what git stores (the index blob)
once they are tracked: on Windows `core.autocrlf=true` may leave CRLF in the working tree of a file that git stores
with LF. What only a build can confirm is an instructor checklist item (INSTRUCTOR.md).
"""

import json
import re
import shutil
import subprocess

import pytest
from conftest import git_output, in_git, stored_bytes

from workshop.check_tools import EXPECTED

DEVCONTAINER = ".devcontainer/devcontainer.json"
DOCKERFILE = ".devcontainer/Dockerfile"
POST_CREATE = ".devcontainer/post-create.sh"
CONTAINER_FILES = (DEVCONTAINER, DOCKERFILE, POST_CREATE)

FROM_LINE = "FROM mcr.microsoft.com/devcontainers/base:3.0.10-ubuntu24.04"
_ARG_RE = re.compile(r"^ARG[ \t]+([A-Z_][A-Z0-9_]*)=(\S+)[ \t]*$", re.MULTILINE)
# a pipe into a shell, also through sudo with options: `curl ... | bash`, `curl ... |sh -`, `curl ... | sudo -E bash -`
_PIPE_TO_SHELL_RE = re.compile(r"\|\s*(?:sudo\s+(?:-\S+\s+)*)?(?:ba|da|z)?sh\b")
_ERREXIT_RE = re.compile(r"^\s*set\s+(?:-[A-Za-z]*e|-o\s+errexit)", re.MULTILINE)


def _text(root, rel: str) -> str:
    return stored_bytes(root, rel).decode("utf-8")


def test_devcontainer_json(root):
    spec = json.loads(_text(root, DEVCONTAINER))  # strict JSON: no comments, no trailing commas
    assert spec["build"]["dockerfile"] == "Dockerfile"
    assert spec["hostRequirements"] == {"cpus": 4, "memory": "8gb", "storage": "32gb"}
    # DISABLE_AUTOUPDATER keeps the pinned Claude Code; uv cannot hard-link across /workspaces and ~/.cache, so it copies
    assert spec["containerEnv"] == {"DISABLE_AUTOUPDATER": "1", "UV_LINK_MODE": "copy"}
    assert spec["postCreateCommand"] == "bash .devcontainer/post-create.sh"
    assert spec["remoteUser"] == "vscode"


def test_pipe_to_shell_pattern_self_check():
    """The pattern below must catch the usual forms, so that a broken pattern cannot pass the Dockerfile silently."""
    assert _PIPE_TO_SHELL_RE.search("curl -fsSL https://example.org/setup | bash")
    assert _PIPE_TO_SHELL_RE.search("curl -fsSL https://example.org/setup |sh -")
    assert _PIPE_TO_SHELL_RE.search("curl -fsSL https://example.org/setup | sudo -E bash -")
    assert not _PIPE_TO_SHELL_RE.search(" && bash /tmp/nodesource_setup.sh \\")
    assert not _PIPE_TO_SHELL_RE.search("curl -fsSL https://example.org/setup -o /tmp/setup.sh")


def test_dockerfile_pins_agree_with_the_tool_check(root):
    text = _text(root, DOCKERFILE)
    lines = text.splitlines()
    args = dict(_ARG_RE.findall(text))
    assert [line for line in lines if line.startswith("FROM ")] == [FROM_LINE]
    assert args.get("CALCULIX_VERSION") == EXPECTED["calculix-ccx"]
    # the Debian version of Gmsh 4.12.1 adds a repack suffix and a revision (+ds1-1.1build2)
    assert re.fullmatch(re.escape(EXPECTED["gmsh"]) + r"(?:[+~-]\S*)?", args.get("GMSH_VERSION", ""))
    assert "v" + args.get("NODE_MAJOR", "") + "." == EXPECTED["node"]
    assert args.get("CLAUDE_CODE_VERSION") == EXPECTED["claude"]
    assert "ghcr.io/astral-sh/uv:" + EXPECTED["uv"] in text
    assert f"COPY --from=ghcr.io/astral-sh/uv:{EXPECTED['uv']} /uv /uvx /bin/" in lines
    # the packages are installed at the pinned versions; calculix-ccx-doc is version 2.11 and is never used
    assert "calculix-ccx=${CALCULIX_VERSION}" in text
    assert "gmsh=${GMSH_VERSION}" in text
    assert "calculix-ccx-doc" not in text
    assert "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" in text
    assert "npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" in text
    # a build argument, so that DEBIAN_FRONTEND does not stay in the participants' shells
    assert args.get("DEBIAN_FRONTEND") == "noninteractive"
    assert not re.search(r"^ENV\b.*DEBIAN_FRONTEND", text, re.MULTILINE)
    assert [line for line in lines if _PIPE_TO_SHELL_RE.search(line)] == []
    assert "/usr/local/bin/ccx" not in text  # participants use the real /usr/bin/ccx: no wrapper


def test_post_create_never_blocks_and_runs_the_helpers(root):
    text = _text(root, POST_CREATE)
    lines = text.splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert "set -u" in lines
    assert not _ERREXIT_RE.search(text), "set -e would let one failing step stop the codespace from opening"
    assert "python3 -m workshop.plugin install" in text
    assert "python3 -m workshop.check_tools" in text
    assert "--with hatchling" in text
    # the optional permission hook comes after the plugin install and cannot make the setup incomplete or stop it
    assert text.index("python3 -m workshop.plugin install") < text.index("python3 -m workshop.permissions")
    hook_line = next(line for line in lines if "python3 -m workshop.permissions" in line)
    assert hook_line.strip().startswith("python3 -m workshop.permissions || echo ")
    assert "permission hook not installed" in hook_line and "participants will see the normal prompts" in hook_line
    assert "$?" not in hook_line, "the hook step must not feed the SETUP INCOMPLETE test"
    assert [line.strip() for line in lines if line.strip()][-1] == "exit 0"
    assert "/usr/local/bin/ccx" not in text
    if in_git(root):
        staged = git_output(root, "ls-files", "-s", "--", POST_CREATE)
        assert staged is not None, "git ls-files -s failed"
        if staged:  # tracked: git must store the executable bit (Windows records 100644 without update-index --chmod)
            assert staged.startswith(b"100755"), staged.decode("utf-8", errors="replace")


def _usable_bash() -> str | None:
    """A bash that can check syntax (`bash -n` on a trivial script), or None."""
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        done = subprocess.run([bash, "-n"], input=b"true\n", capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return bash if done.returncode == 0 else None


def test_post_create_is_valid_bash(root):
    bash = _usable_bash()
    if bash is None:
        pytest.skip("needs a working bash")
    # the stored bytes go in on stdin: no path translation, and the index content is what is checked
    done = subprocess.run([bash, "-n"], input=stored_bytes(root, POST_CREATE), capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")


def test_container_files_have_no_cr(root):
    """bash in the container fails on a carriage return, and a script needs git's LF: what git stores must be LF."""
    for rel in CONTAINER_FILES:
        assert b"\r" not in stored_bytes(root, rel), f"{rel}: carriage return"
    if in_git(root):
        listed = git_output(root, "check-attr", "text", "eol", "--", *CONTAINER_FILES)
        assert listed is not None, "git check-attr failed"
        attrs = set(listed.decode("utf-8").splitlines())
        for rel in CONTAINER_FILES:
            assert {f"{rel}: text: auto", f"{rel}: eol: lf"} <= attrs, rel
