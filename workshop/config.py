"""Workshop configuration: where the MCP-Anything plugin is hosted (workshop.conf). Standard library only."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF_PATH = ROOT / "workshop.conf"
PLACEHOLDER = "YOUR-GITHUB-OWNER/mcp-anything"
KNOWN_KEYS = ("MCP_ANYTHING_REPO",)
_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}(#[A-Za-z0-9._/-]{1,100})?")


def load_conf(path: Path = CONF_PATH) -> dict[str, str]:
    """Read `KEY=VALUE` lines (blank lines and `#` comment lines are skipped) from the configuration file.

    Raises ValueError, naming the line, for a malformed line, an unknown key, a key given twice or a value that is not
    `owner/name` or `owner/name#ref`; and, naming the file, for a missing key.
    """
    values: dict[str, str] = {}
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, equals, value = line.partition("=")
        if not equals or not _KEY_RE.fullmatch(key):
            raise ValueError(f"{path}: line {number}: expected KEY=VALUE (no spaces around '='), got {line!r}")
        if key not in KNOWN_KEYS:
            raise ValueError(f"{path}: line {number}: unknown key {key!r} (known: {', '.join(KNOWN_KEYS)})")
        if key in values:
            raise ValueError(f"{path}: line {number}: {key} is given twice")
        if not REPO_RE.fullmatch(value):
            raise ValueError(f"{path}: line {number}: {key} must be owner/name or owner/name#ref, got {value!r}")
        values[key] = value
    for key in KNOWN_KEYS:
        if key not in values:
            raise ValueError(f"{path}: {key} is missing")
    return values


def mcp_anything_repo(path: Path = CONF_PATH) -> str:
    """The `owner/name[#ref]` that hosts the MCP-Anything plugin."""
    return load_conf(path)["MCP_ANYTHING_REPO"]


def is_placeholder(value: str) -> bool:
    """True while the owner is still the placeholder (with or without a `#ref`)."""
    return value.split("#", 1)[0] == PLACEHOLDER
