import pytest

from workshop import config


def _write(tmp_path, text):
    path = tmp_path / "workshop.conf"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def test_load_conf_reads_the_placeholder(tmp_path):
    path = _write(tmp_path, f"# a comment\n\nMCP_ANYTHING_REPO={config.PLACEHOLDER}\n")
    assert config.load_conf(path) == {"MCP_ANYTHING_REPO": config.PLACEHOLDER}
    assert config.mcp_anything_repo(path) == config.PLACEHOLDER
    assert config.is_placeholder(config.PLACEHOLDER)


def test_the_committed_conf_loads(root):
    # the placeholder or a real owner/name[#ref]: stays green after the instructor sets the repository
    assert config.CONF_PATH == root / "workshop.conf"
    assert set(config.load_conf(config.CONF_PATH)) == {"MCP_ANYTHING_REPO"}


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("MCP_ANYTHING_REPO=a b/c\n", "line 1"),
        ("NOPE=x/y\n", "unknown key"),
        ("", "MCP_ANYTHING_REPO is missing"),
        ("MCP_ANYTHING_REPO=owner\n", "owner/name"),
        ("MCP_ANYTHING_REPO=x/y\nMCP_ANYTHING_REPO=x/z\n", "twice"),
        ("just text\n", "line 1"),
    ],
)
def test_bad_conf_is_refused(tmp_path, text, fragment):
    with pytest.raises(ValueError) as refused:
        config.load_conf(_write(tmp_path, text))
    assert fragment in str(refused.value)


@pytest.mark.parametrize(
    "text, line",
    [
        ("# comment\n\nNOPE=x/y\n", "line 3"),
        ("MCP_ANYTHING_REPO=x/y\nMCP_ANYTHING_REPO=x/z\n", "line 2"),
        ("# comment\nMCP_ANYTHING_REPO = x/y\n", "line 2"),
        ("MCP_ANYTHING_REPO=x/y#\n", "line 1"),
    ],
)
def test_bad_conf_names_the_line(tmp_path, text, line):
    with pytest.raises(ValueError, match=line):
        config.load_conf(_write(tmp_path, text))


def test_repo_with_a_tag_is_accepted(tmp_path):
    path = _write(tmp_path, "MCP_ANYTHING_REPO=acme/mcp-anything#v0.1.0\n")
    value = config.mcp_anything_repo(path)
    assert value == "acme/mcp-anything#v0.1.0"
    assert not config.is_placeholder(value)


def test_the_placeholder_with_a_tag_is_still_the_placeholder():
    assert config.is_placeholder(config.PLACEHOLDER + "#v0.1.0")
    assert not config.is_placeholder("acme/mcp-anything")


def test_line_endings_and_blank_lines_do_not_matter(tmp_path):
    path = tmp_path / "workshop.conf"
    path.write_bytes(b"# c\r\n\r\n  \r\nMCP_ANYTHING_REPO=acme/tools\r\n")  # a CRLF working tree, as on Windows
    assert config.mcp_anything_repo(path) == "acme/tools"
