"""Participant documents: the README and the exercise READMEs state the facts the workshop depends on.

They read what git stores (the index blob), not the working tree: on Windows `core.autocrlf=true` may leave CRLF in
the working tree of a file that git stores with LF.
"""

import argparse
import importlib
import re
import shlex

import pytest
from conftest import repo_files, stored_bytes

from workshop import check_tools, gmshinp, manual, permissions, plugin, verify
from workshop.beam import (
    Cantilever,
    c3d20r_mesh,
    cantilever_reference,
    selfweight_reaction,
    selfweight_reference,
    selfweight_tip_deflection,
)
from workshop.check_tools import EXPECTED
from workshop.layers import CABLE_LAYERS, CABLE_PRESSURE, solve_plane_strain
from workshop.proc import Completed

EXERCISES = ("00-setup", "01-cantilever", "02-gmsh-beam", "03-documentation", "04-cable-section")
PARTICIPANT_DOCS = ("README.md", *(f"exercises/{name}/README.md" for name in EXERCISES))
INSTRUCTOR = "INSTRUCTOR.md"
ALL_DOCS = (*PARTICIPANT_DOCS, INSTRUCTOR)
CI_WORKFLOW = ".github/workflows/ci.yml"
# `python` as a command word: not python3, not part of a longer name or path, not the `uv python` subcommand (a whole
# word `uv`). The dev container has no bare `python`.
_PYTHON_WORD = re.compile(r"(?<![\w./-])(?<!\buv )python(?![\w.])")
GMSHINP_COMMANDS = (
    "python3 -m workshop.gmshinp plane-strain cable_mesh_gmsh.inp cable_mesh.inp",
    "python3 -m workshop.gmshinp dload cable_mesh.inp OUTER 10 cable_pressure_load.inc",
)
EXPAND_AREA = (
    "/mcp-anything:expand self-weight runs: read the mean tip displacement over node set TIP and compare it with a "
    "reference"
)
README_HEADINGS = (
    "## What you need",
    "## Start",
    "## Log in",
    "## If something is missing",
    "## Exercises",
    "## Where you work",
    "## Software and licences",
)


def _text(root, rel: str) -> str:
    return stored_bytes(root, rel).decode("utf-8")


def _exercise(root, name: str) -> str:
    return _text(root, f"exercises/{name}/README.md")


def _missing(text: str, needles) -> list[str]:
    return [needle for needle in needles if needle not in text]


def test_readme_headings_and_facts(root):
    text = _text(root, "README.md")
    lines = text.splitlines()
    assert [heading for heading in README_HEADINGS if heading not in lines] == []
    facts = (
        "Paste code here if prompted",
        "read -rs ANTHROPIC_API_KEY",
        "unset ANTHROPIC_API_KEY",
        "/plugin install mcp-anything@mcp-anything",
        "python3 -m workshop.plugin print",
        "python3 -m workshop.plugin install",
        "python3 -m workshop.check_tools",
        "python3 -m workshop.manual",
        "The free claude.ai plan does not include Claude Code access",
        "SETUP OK",
        "cat ~/workshop-setup.txt",
        "workshop.conf",
        "work/",
    )
    assert _missing(text, facts) == []
    assert _missing(text, [f"(exercises/{name}/README.md)" for name in EXERCISES]) == []  # the exercise table links


def test_every_exercise_has_a_readme(root):
    for name in EXERCISES:
        assert _exercise(root, name).startswith("# "), name


def test_building_exercises_say_where_to_work(root):
    for name in ("01-cantilever", "02-gmsh-beam"):
        assert 'mkdir -p "$WORKSHOP_ROOT/work/' in _exercise(root, name), name


def test_exercise_01_pins_names_and_citations(root):
    """The run-time answer must lead MCP-Anything to the batch-solver route, never to `cli`."""
    text = _exercise(root, "01-cantilever")
    needles = (
        "tip_displacement_y",
        "support_reaction_y",
        "bad_modulus.inp",
        "NOT_NUMERIC",
        "ccx -i",
        "/usr/bin/ccx",
        "help_output",
        "201",
        "version_exit_codes=(0, 201)",
        "keep going after I close Claude Code",
        "Card image cannot be interpreted",
        "No documentation for now",
        "§7.49",
        "§7.98",
        "§7.15",
    )
    assert _missing(text, needles) == []
    assert "A run takes a few seconds" not in text
    assert re.search(r"a\s+few\s+seconds", text, re.IGNORECASE) is None  # in any form, across a line break too
    assert "/usr/local/bin/ccx" not in text


def test_exercise_02_table_matches_the_formula(root):
    text = _exercise(root, "02-gmsh-beam")
    assert _missing(text, [f"{selfweight_tip_deflection(length, 20, 20):.4g}" for length in (500, 750, 1000, 1500)]) == []


def test_exercise_02_route_evidence(root):
    text = _exercise(root, "02-gmsh-beam")
    assert _missing(text, ("--help", "--version", "schema_reviewed", "§7.75", "inputs/examples/")) == []


def test_exercise_04_values_and_warnings(root):
    text = _exercise(root, "04-cable-section")
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    displacements = [f"{solution.radial_displacement(r):.4g}" for r in (10.0, 24.0)]
    interface_pressures = [f"{-solution.radial_stress(r):.4g}" for r in (10.0, 18.0, 20.0)]
    words = (
        "TEACHING SIMPLIFICATION",
        "CPS6",
        "CPE6",
        "instructor to verify",
        "workshop.gmshinp plane-strain",
        "workshop.gmshinp dload",
    )
    assert _missing(text, [*displacements, *interface_pressures, *words]) == []


def _bare_python(text: str) -> list[str]:
    """Lines that use `python` as a command word without `uv run` before it on the same line."""
    return [
        line.strip()
        for line in text.splitlines()
        for match in _PYTHON_WORD.finditer(line)
        if "uv run" not in line[: match.start()]
    ]


def test_bare_python_guard_self_check():
    assert _bare_python("python -m workshop.check_tools") == ["python -m workshop.check_tools"]
    assert _bare_python("run `python script.py` here") == ["run `python script.py` here"]
    assert _bare_python("python3 -m workshop.manual html") == []
    assert _bare_python('uv run --directory "x" python -c "print(1)"') == []
    assert _bare_python("cpython, /usr/bin/python3, python.org, Python") == []
    assert _bare_python("uv python find 3.12") == []
    assert _bare_python("kuv python find 3.12") == ["kuv python find 3.12"]
    assert _bare_python("uv python find 3.12 && python script.py") == ["uv python find 3.12 && python script.py"]


def test_docs_never_use_a_bare_python_command(root):
    """The dev container has `python3` and `uv run`, but no `python` command. The instructor notes are covered too."""
    found = {rel: hits for rel in ALL_DOCS if (hits := _bare_python(_text(root, rel)))}
    assert found == {}


def test_readme_says_yes_to_the_api_key_prompt(root):
    text = _text(root, "README.md")
    assert _missing(text, ('"Detected a custom API key"', "choose Yes")) == []


def test_exercise_01_numbers_match_the_helpers(root):
    text = _exercise(root, "01-cantilever")
    mesh = c3d20r_mesh(Cantilever())
    values = cantilever_reference()["values"]
    needles = (
        f"{len(mesh.nodes)} nodes",
        f"the {len(mesh.elements)} elements",
        f"`tip_displacement_y` = {values['tip_displacement_y']:g} mm",
        f"`support_reaction_y` = {values['support_reaction_y']:g} N",
    )
    assert _missing(text, needles) == []


def test_exercise_01_version_flag_and_knowledge_answers(root):
    """The agent must not have to guess `-v`; Phase 4 may record examples-only knowledge once the knowledge command exists."""
    text = _exercise(root, "01-cantilever")
    needles = (
        "its version flag is `-v`",
        "If it proposes another version flag, ask for `-v` instead.",
        "or only the example decks in `inputs/examples/` if it offers to serve those. Either is fine.",
        "`doc_structure`",
    )
    assert _missing(text, needles) == []


def test_exercise_02_reaction_column_matches_the_helpers(root):
    text = _exercise(root, "02-gmsh-beam")
    rows = [
        f"| {length} | {selfweight_tip_deflection(length, 20, 20):.4g} | {selfweight_reaction(length, 20, 20):.2f} |"
        for length in (500, 750, 1000, 1500)
    ]
    assert _missing(text, rows) == []


def test_exercise_02_part_b_hands_over_first_and_adds_new_tools(root):
    """Expand drafts the new rules from the deck and its mesh, so they are in place first; it never changes the
    existing tools, so the self-weight check is a new tool and a comparison built on it."""
    text = _exercise(root, "02-gmsh-beam")
    handoff = 'cp "$WORKSHOP_ROOT/work/gmsh-mesher/outputs/beam_mesh.inp" .'
    needles = (
        handoff,
        EXPAND_AREA,
        "keywords and forms your 01 schema does not have",
        "for example in `inputs/golden/selfweight/`",
        "the new comparison",
    )
    assert _missing(text, needles) == []
    assert text.index(handoff) < text.index(EXPAND_AREA)
    assert "keywords your 01 schema does not have" not in text


def test_exercise_03_hedges_the_conversion_trial(root):
    assert "If the agent runs a conversion trial" in _exercise(root, "03-documentation")


def test_exercise_04_gmshinp_commands_parse(root, monkeypatch):
    """Both commands are written in full and are accepted by `workshop.gmshinp`'s own command line."""
    text = _exercise(root, "04-cable-section")
    assert _missing(text, GMSHINP_COMMANDS) == []
    calls = []
    monkeypatch.setattr(gmshinp, "_plane_strain", lambda *args: calls.append(("plane-strain", *args)))
    monkeypatch.setattr(gmshinp, "_dload", lambda *args: calls.append(("dload", *args)))
    for command in GMSHINP_COMMANDS:
        assert gmshinp.main(shlex.split(command)[3:]) == 0, command
    assert calls == [
        ("plane-strain", "cable_mesh_gmsh.inp", "cable_mesh.inp"),
        ("dload", "cable_mesh.inp", "OUTER", "10", "cable_pressure_load.inc"),
    ]


def test_exercise_04_describes_what_gmshinp_does(root):
    text = _exercise(root, "04-cable-section")
    assert _missing(text, ("refuses any element type other than `CPS6`", "counter-clockwise")) == []


def test_exercise_04_material_table_matches_cable_layers(root):
    """One row per layer, in order: name, radii, E (MPa), Poisson's ratio, and "instructor to verify"."""
    rows = []
    for line in _exercise(root, "04-cable-section").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("| `") and re.fullmatch(r"`[A-Z_]+`", cells[0]):
            rows.append(cells)
    assert [cells[0].strip("`") for cells in rows] == [layer.name for layer in CABLE_LAYERS]
    inner = 0.0
    for cells, layer in zip(rows, CABLE_LAYERS):
        assert [float(r) for r in cells[1].split(" to ")] == [inner, layer.outer_radius], layer.name
        assert (float(cells[2]), float(cells[3])) == (layer.young, layer.poisson), layer.name
        assert cells[-1] == "instructor to verify", layer.name
        inner = layer.outer_radius


# ---- INSTRUCTOR.md and the CI workflow ---------------------------------------------------------------------------------

INSTRUCTOR_HEADINGS = (
    "## Before the workshop",
    "## Timeline",
    "## Verify the decks",
    "## Checklist",
    "## ccx -v exits 201",
    "## Authentication",
    "## Troubleshooting",
    "## After the workshop",
)
LAST_PLANNED_ROW = 32  # C1-C32 are the basic and day-of checks; the rows after C32 are further checks
FOREIGN_FILES = frozenset({"tests/test_repo.py"})  # MCP-Anything's own banned-name test, run in its checkout (step 2)
_PATH_ROOTS = r"(?:\.devcontainer|\.github|exercises|scripts|tests|workshop)"
_REPO_PATH = re.compile(r"(?<![\w.-])(" + _PATH_ROOTS + r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)")
_ROW_START = re.compile(r"\| (C\d+) \|")
_HEADING = re.compile(r"#{1,6} ")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_PARSE_ARGS = argparse.ArgumentParser.parse_args

CI_TEXT = """name: tests
on: [push, pull_request]
jobs:
  tests:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: astral-sh/setup-uv@v10.3.2
        with:
          version: "0.13.5"
      - run: uv run pytest -q
"""

# What the checklist rows must keep, row by row: their commands and key values.
BRIEF_PHRASES = {
    "C1": ("cat ~/workshop-setup.txt", "SETUP OK"),
    "C2": ("which ccx; ccx -v; echo $?", "/usr/bin/ccx", "This is Version 2.21", "201"),
    "C3": ("claude plugin list", "mcp-anything@mcp-anything", "post-create.sh"),
    "C4": ("scripts/verify_decks.sh", "*ERROR reading *ELASTIC", "201", "within 1 %", "FIXED nodes' own self-weight"),
    "C5": ("C3D10", "CPS6", "*Heading"),
    "C6": ("P_CORE", "P_OUTER", "CPE6"),
    "C7": ("/mcp-anything", "help_output", "exit 201", "version_exit_codes=(0, 201)", "golden"),
    "C8": ("callback", "paste-code"),
    "C9": ("/status",),
    "C10": ("python3 -m workshop.check_tools --ready",),
    "C11": ("523 UTF-8 pages", "PNG"),
    "C12": ("4-core",),
    "C13": ("post-create.sh",),
    "C14": ("echo $WORKSHOP_ROOT",),
    "C15": ("someone who knows cables",),
    "C16": (
        "get_backend()",
        "uv run --directory <server> python -c",
        "from <pkg>.server import server_status; print(server_status())",
        "version_error",
        "version_exit_codes=(0, 201)",
    ),
    "C17": (
        "find ~/.claude/plugins -path '*mcp-anything*' -name METHOD.md",
        "grep -n version_exit_codes",
        "templates/routes/batch_solver",
    ),
    "C18": ("python3 -m workshop.manual html", "pdf", "SHA-256"),
    "C19": ("batch_solver",),
    "C20": ("`knowledge` = `none`", "inputs/examples/", "the build goes on"),
    "C21": ("solver_accepted", "Card image cannot be interpreted"),
    "C22": ("gmsh --help", "`cli`", "schema_reviewed", "L = 1000"),
    "C23": ("workshop.gmshinp", 'scripts/verify_decks.sh --only 04 --keep "$WORKSHOP_ROOT/work/verify"', "04-cable"),
    "C24": ("decklint.KEYWORDS", "§5.1", "§6.2.4", "6.2.25"),
    "C25": ("df -h /", "20 minutes"),
    "C26": ("uv run pytest -q",),
    "C27": ("git ls-files -s scripts/verify_decks.sh .devcontainer/post-create.sh", "100755"),
    "C28": ("apt-cache policy calculix-ccx gmsh libgmsh4.12", "2.21-1", "4.12.1+ds1-1.1build2"),
    "C29": ("claude plugin marketplace list", "code.claude.com/docs/en/plugins/install"),
    "C30": ("70-minute",),
    "C31": ("ccxdat",),
    "C32": ("GModelIO_INP.cpp", "gmsh_4_12_1", "to_plane_strain"),
}

# What the dry runs and reviews asked INSTRUCTOR.md to cover, by the row (or the `####` detail subsection that names the
# row) that holds it.
CARRY_PHRASES = {
    # the dev container
    "C1": (
        "whoami",
        "grep 'uv cache' ~/workshop-setup.txt",
        "uv cache: ready",
        "SETUP OK (uv cache not pre-filled",
        "bash .devcontainer/post-create.sh",
        "DISABLE_AUTOUPDATER",
        "E: Version",
        "NodeSource",
        "npm install -g",
    ),
    "C3": ("python3 -m workshop.plugin status", "python3 -m workshop.plugin install", "Install for you (user scope)", "Installed"),
    "C13": (
        "builds the whole image",
        "same moment",
        "Ubuntu archive",
        "NodeSource",
        "290 MB",
        "storage",
        "Actions minutes",
        "your decision",
    ),
    "C14": ("zsh",),
    "C25": ("SETUP OK", "disk"),
    "C28": ("apt-cache policy calculix-ccx gmsh",),
    "C34": (
        "uv python find 3.12",
        "/usr/bin/python3.12",
        ".local/share/uv/python",
        'du -sh "$(uv cache dir)"',
        "/home/vscode",
        "DEBIAN_FRONTEND",
    ),
    "C35": (
        "SETUP INCOMPLETE",
        "PLACEHOLDER",
        "workshop/config.py",
        "check_tools --ready",
        "git checkout workshop.conf",
        "again ends with `SETUP OK`",
    ),
    "C36": ("env -u DISPLAY", "gmsh --help", "-3"),
    # detached runs
    "C33": (
        "job_status",
        "finished",
        "quit Claude Code",
        "reopen",
        "cantilever_deck",
        "check its size first",
        "lower LC step by step",
    ),
    # the exercise 01 deck
    "C4": (
        "ccx -i cantilever",
        "*WARNING",
        "node 1211",
        "-2.4948",
        "(0, +21, 0)",
        "16 + 5",
        "Jacobian",
        "ccx -i bad_modulus",
        "30.77",
        "CABLE_PRESSURE = +10",
        "-0.003571",
    ),
    "C31": ("displacements (vx,vy,vz) for set TIPC", "total force (fx,fy,fz) for set FIX"),
    # the Gmsh helpers
    "C32": ("Mesh.SaveGroupsOfElements = -100", "T3D3"),
    # the Gmsh decks
    "C5": (
        "gmsh --version",
        "grep '^\\*' beam_mesh.inp | sort | uniq -c",
        "*ELEMENT, type=C3D10, ELSET=Volume1",
        "*ELSET,ELSET=BEAM",
        "*NSET,NSET=FIXED",
        "*NSET,NSET=TIP",
        "T3D3",
        "gmsh cable_quarter.geo -2 -format inp -o cable_mesh_gmsh.inp",
        "four `*ELEMENT, type=CPS6` blocks",
        "CORE, INSULATION, SHEATH, ARMOUR and CABLE",
        "P_CORE and P_OUTER",
        "SYMX, SYMY, OUTER",
        "an NSET and an ELSET with the same name",
        "the `1.` thickness line",
        "`*INCLUDE` inside `*STEP`",
        'trailing ", "',
    ),
    "C6": ("P_CORE", "P_OUTER", "3-D", "-9.113e-05", "-0.003571"),
    "C38": ("x = 1000", "x = 0", "-setnumber L 500", "beam_mesh_500.inp", "memory", "4 cores", "02-beam-L1000", "02 beam L=1000"),
    # what the dry run of the participant docs must confirm
    "C7": ("✘ Command line", "Phase 8", "/mcp", "connected"),
    "C8": ("Paste code here if prompted", "Console"),
    "C9": ("Detected a custom API key", "unset ANTHROPIC_API_KEY", "/config"),
    "C11": ("conversion trial", "Serve it section by section", "§7.15"),
    "C12": ("New with options", "branch", "2-core"),
    "C17": ("/mcp-anything:check", "/mcp-anything:knowledge", "/mcp-anything:expand"),
    "C22": ("-setnumber L 500", "TIP-mean", "FIXED"),
    "C23": ("PYTHONPATH", "plane-strain", "P_CORE"),
    "C37": ("Settings", "New secret", "Repository access", "fork", "restart"),
}


def _missing_flat(text: str, needles) -> list[str]:
    """Like `_missing`, but a phrase may break across lines or indentation in the hard-wrapped notes."""
    flat = " ".join(text.split())
    return [needle for needle in needles if " ".join(needle.split()) not in flat]


def _instructor(root) -> str:
    return _text(root, INSTRUCTOR)


def _section(text: str, heading: str) -> str:
    """The lines under the `## ` heading, up to the next `## ` heading."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _checklist(text: str):
    """(row ids in order, cells by id, text by id). A `####` subsection whose heading names rows belongs to them."""
    ids, cells, texts = [], {}, {}
    lines = _section(text, "## Checklist").splitlines()
    for line in lines:
        match = _ROW_START.match(line)
        if match:
            row = match.group(1)
            ids.append(row)
            cells[row] = [cell.strip() for cell in _UNESCAPED_PIPE.split(line.strip())[1:-1]]
            texts[row] = line
    named: list[str] = []
    in_code = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and _HEADING.match(line):
            named = re.findall(r"\bC\d+\b", line) if line.startswith("#### ") else []
        for row in named:
            texts[row] += "\n" + line  # a KeyError here means a heading that names a row that does not exist
    return ids, cells, texts


def _steps(section: str) -> dict[int, str]:
    """The numbered steps of a section (numbers at the start of a line), each with its sub-items and code blocks."""
    parts = re.split(r"^(?=\d+\. )", section, flags=re.MULTILINE)
    return {int(part.split(".", 1)[0]): part for part in parts if re.match(r"\d+\. ", part)}


def _table_rows(section: str) -> list[list[str]]:
    """The cells of every table row (a separator row like |---|---| is not one)."""
    return [[c.strip() for c in _UNESCAPED_PIPE.split(line.strip())[1:-1]] for line in section.splitlines() if line.startswith("| ")]


def test_instructor_notes(root):
    text = _instructor(root)
    lines = text.splitlines()
    assert [heading for heading in INSTRUCTOR_HEADINGS if heading not in lines] == []
    positions = [lines.index(heading) for heading in INSTRUCTOR_HEADINGS]
    assert positions == sorted(positions), "the headings are in the order of the plan"
    needles = (
        "201",
        "version_exit_codes=(0, 201)",
        "git merge --ff-only",
        "git checkout --orphan",
        "Cerebras",
        "not supported as a drop-in",
        "scripts/verify_decks.sh",
        "code.claude.com/docs/en/llm-gateway",
        *(f"C{number}" for number in range(1, LAST_PLANNED_ROW + 1)),
    )
    assert _missing_flat(text, needles) == []
    assert "/usr/local/bin/ccx" not in text  # participants use the real /usr/bin/ccx: no wrapper


def test_instructor_checklist_is_unbroken_and_every_row_is_complete(root):
    text = _instructor(root)
    ids, cells, _ = _checklist(text)
    assert ids == [f"C{number}" for number in range(1, len(ids) + 1)]
    assert len(ids) > LAST_PLANNED_ROW, "the review items come after C32"
    assert [row for row in ids if len(cells[row]) != 4 or not all(cells[row])] == []  # Id, Check, Expected, If different
    mentioned = {f"C{number}" for number in re.findall(r"\bC(\d+)\b", text)}
    assert sorted(mentioned - set(ids)) == [], "a reference to a row that does not exist"


def test_instructor_rows_keep_the_values_of_the_plan(root):
    _, _, texts = _checklist(_instructor(root))
    assert sorted(set(BRIEF_PHRASES) - set(texts)) == []
    gaps = {row: _missing_flat(texts[row], phrases) for row, phrases in BRIEF_PHRASES.items()}
    assert {row: gone for row, gone in gaps.items() if gone} == {}


def test_instructor_covers_every_item_of_the_earlier_reviews(root):
    """Each item of the dry runs and reviews is in the row (or detail subsection) that is meant to hold it."""
    ids, _, texts = _checklist(_instructor(root))
    assert sorted(set(CARRY_PHRASES) - set(texts)) == []
    gaps = {row: _missing_flat(texts[row], phrases) for row, phrases in CARRY_PHRASES.items()}
    assert {row: gone for row, gone in gaps.items() if gone} == {}
    assert set(range(33, 39)) <= {int(row[1:]) for row in ids}


def test_instructor_before_the_workshop(root):
    steps = _steps(_section(_instructor(root), "## Before the workshop"))
    assert sorted(steps) == list(range(1, 8))
    for number in (1, 2, 4, 5, 6, 7):  # the steps that reach outside the repository say who does them
        assert steps[number].split(". ", 1)[1].startswith("**You"), number
    commands = (
        "cd <your MCP-Anything checkout>",
        "git switch main",
        "git merge --ff-only <branch>",
        "grep -n version_exit_codes METHOD.md",
        "git merge --no-edit <branch>",
        "uv run pytest -q",
        "batch-solver route",
        "version_exit_codes",
        "/mcp-anything:knowledge",
        "/mcp-anything:expand",
    )
    assert _missing_flat(steps[1], commands) == []
    commands = (
        "git checkout --orphan public main",
        'git commit -m "MCP-Anything 0.1.0"',
        "uv run pytest tests/test_repo.py -q",
        "git tag v0.1.0",
        "git remote add origin-public https://github.com/<owner>/mcp-anything.git",
        "git push origin-public public:main",
        "git push origin-public v0.1.0",
        "git config user.name",
        "git config user.email",
    )
    assert _missing_flat(steps[2], commands) == []
    # plugin.py and check_tools.py send the instructor to "step 3" for workshop.conf
    assert _missing_flat(steps[3], ("MCP_ANYTHING_REPO=<owner>/mcp-anything#v0.1.0", "workshop.conf", "uv run pytest -q", "C29")) == []
    assert _missing_flat(
        steps[4], ("Public repository", "Organisation repository", "Codespaces", "git config user.name", "git config user.email")
    ) == []
    assert _missing_flat(steps[5], ("prebuild", "updateContentCommand", "post-create.sh", "C13")) == []
    assert _missing_flat(steps[6], ("C15", "C18")) == []
    assert _missing_flat(steps[7], ("Console workspace", "spend limit", "one key per participant", "hand-out")) == []


def test_instructor_timeline_adds_up(root):
    section = _section(_instructor(root), "## Timeline")
    rows = [row for row in _table_rows(section) if re.fullmatch(r"\d+:\d\d", row[0])]
    minutes = [int(row[1]) for row in rows]
    assert minutes == [15, 20, 70, 10, 45, 25, 20, 5]
    clock = 0
    for row, length in zip(rows, minutes):
        hours, mins = row[0].split(":")
        assert int(hours) * 60 + int(mins) == clock, row
        clock += length
    assert clock == 210
    rules = ("Never touch the user's machine without permission", "Never silently wrong", "Nothing is built on an unconfirmed decision")
    assert _missing_flat(section, rules) == []


def test_instructor_verify_table_matches_the_helpers(root):
    """The table to fill in has the columns and the case labels that `workshop.verify` prints, and the expected numbers."""
    section = _section(_instructor(root), "## Verify the decks")
    rows = _table_rows(section)
    assert rows[0] == ["Case", "Quantity", "Expected", "FE", "Limit", "Result", "Note"]
    beam_labels = [f"02 beam L={length:g}" for length in (verify.DEFAULT_BEAM_LENGTH, 500.0)]
    assert list(dict.fromkeys(case.strip("`") for case, *_ in rows[1:])) == [
        name for group in verify.CASES.values() for name, _ in group
    ]
    assert [(case.strip("`"), quantity.strip("`")) for case, quantity, *_ in rows[1:]] == [
        (verify.CANTILEVER, "tip_displacement_y"),
        (verify.CANTILEVER, "support_reaction_y"),
        (verify.BROKEN, "rejected: *ERROR reading *ELASTIC"),
        (verify.VERSION, "ccx -v"),
        *[(label, name) for label in beam_labels for name in ("tip_displacement_y", "support_reaction_y")],
        (verify.CABLE, "u_r_core_edge"),
        (verify.CABLE, "u_r_outer"),
    ]
    assert not any(any(row[3:]) for row in rows[1:]), "FE, Limit, Result and Note are for the instructor to fill in"
    source = stored_bytes(root, "workshop/verify.py").decode("utf-8")  # the folders of a --keep run, named in the notes
    for folder in ("01-cantilever", "01-broken-deck", "version", "02-beam-L", "04-cable"):
        assert f'"{folder}' in source, folder
    assert _missing_flat(section, ("01-cantilever", "01-broken-deck", "`version`", "02-beam-L1000", "02-beam-L500", "04-cable")) == []
    reaction_rel = selfweight_reference()["tolerances"]["support_reaction_y"]["rel"]
    solution = solve_plane_strain(CABLE_LAYERS, CABLE_PRESSURE)
    needles = (
        "scripts/verify_decks.sh",
        "uv run pytest -m solver -s",
        'scripts/verify_decks.sh --only 04 --keep "$WORKSHOP_ROOT/work/verify"',
        "04-cable",
        "three cases",
        "selfweight_reference(500)",
        "CalculiX or Gmsh not found",
        "VERIFY: PASS",
        "VERIFY: FAIL",
        "Never loosen a tolerance to get a pass",
        "Record the measured value and decide",
        f"within {reaction_rel * 100:g} %",
        f"{selfweight_tip_deflection(1000, 20, 20):.4g}",
        f"{selfweight_reaction(1000, 20, 20):.2f}",
        f"{selfweight_tip_deflection(500, 20, 20):.4g}",
        f"{selfweight_reaction(500, 20, 20):.2f}",
        f"{solution.radial_displacement(10.0):.4g}",
        f"{solution.radial_displacement(24.0):.4g}",
        f"{cantilever_reference()['values']['tip_displacement_y']:g}",
        f"{cantilever_reference()['values']['support_reaction_y']:g}",
    )
    assert _missing_flat(section, needles) == []


def test_instructor_ccx_section(root):
    section = _section(_instructor(root), "## ccx -v exits 201")
    needles = (
        "This is Version 2.21",
        "ccx_2.21.c",
        "line 127",
        "stop.f",
        "call exit(201)",
        "version_exit_codes",
        "help_output",
        "There is no wrapper",
    )
    assert _missing_flat(section, needles) == []


def test_instructor_authentication_section(root):
    section = _section(_instructor(root), "## Authentication")
    needles = (
        "subscription",
        "spend limit",
        "archiv",
        "C30",
        "usage limit",
        "ANTHROPIC_API_KEY",
        "Cerebras",
        "not supported as a drop-in",
        "code.claude.com/docs/en/llm-gateway",
        "LiteLLM",
        "was not tested",
        "Do not offer it to participants",
        "at your own risk",
    )
    assert _missing_flat(section, needles) == []
    for rel in PARTICIPANT_DOCS:  # instructor notes only, never in the participant instructions
        assert "Cerebras" not in _text(root, rel), rel


def test_instructor_troubleshooting_table(root):
    section = _section(_instructor(root), "## Troubleshooting")
    rows = [row for row in _table_rows(section) if len(row) == 2][1:]  # without the header
    assert len(rows) >= 13 and all(all(cell for cell in row) for row in rows)
    needles = (
        "Paste code here if prompted",
        "claude doctor",
        "SETUP INCOMPLETE",
        "*ERROR",
        "ccx exited with code 201",
        "UNKNOWN_VERSION",
        "version_exit_codes=(0, 201)",
        "not empty",
        "nonpositive jacobian",
        "clockwise",
        "Mesh.SaveGroupsOfElements",
        "unmet dependencies",
        "apt-cache policy calculix-ccx gmsh libgmsh4.12",
        "EXPECTED",
        "ANTHROPIC_API_KEY",
        "unset",
        "/config",
        "df -h /",
    )
    assert _missing_flat(section, needles) == []


def test_manual_failure_path_is_written_down(root):
    """Both files of the manual come from one site, so the instructor needs a copy of their own to hand out."""
    text = _instructor(root)
    _, cells, texts = _checklist(text)
    if_different = cells["C18"][3]
    assert _missing_flat(if_different, ("evening before", "--archive", "shared drive", "release asset", "that upload is your decision")) == []
    assert "use the PDF later" not in text  # the PDF comes from the same site
    assert "no fallback" in " ".join(if_different.split())
    # the commands behind it: the hand-out is checked with the option it is meant for, and the urls are the pinned ones
    detail = texts["C18"]
    for kind in ("html", "pdf"):
        assert _missing_flat(detail, (f"python3 -m workshop.manual {kind} --archive",)) == [], kind
        assert manual.SOURCES[kind][0] in detail, kind
    assert set(re.findall(r"https://www\.dhondt\.de/\S+", text)) <= {url for url, _, _ in manual.SOURCES.values()}
    rows = [row for row in _table_rows(_section(text, "## Troubleshooting")) if len(row) == 2]
    (row,) = [row for row in rows if "manual" in row[0] and "download" in row[0]]
    needles = ("Retry", "--archive", "C18", "last resort", "Phase 1", "keyword table", "01 README")
    assert _missing_flat(row[1], needles) == []
    step_4 = _text(root, "exercises/00-setup/README.md").split("4. **Download the manual.**")[1]
    assert "If the download fails, tell the instructor" in step_4
    assert "INSTRUCTOR" not in step_4  # participants never need the instructor notes


def test_moving_an_existing_codespace_to_a_new_tag_is_written_down(root):
    """`install` does not update an installed plugin, so the row gives the three steps, in order, and C29 checks them."""
    text = _instructor(root)
    _, cells, texts = _checklist(text)
    remove = " ".join(plugin.remove_command())
    rows = [row for row in _table_rows(_section(text, "## Troubleshooting")) if len(row) == 2]
    (row,) = [row for row in rows if "existing codespace" in row[0]]
    assert _missing_flat(row[0], ("workshop.conf", "plugin tag")) == []
    flat = " ".join(row[1].split())
    needles = ("git pull", "python3 -m workshop.plugin install", remove, "already added", "is not updated", "C29")
    assert _missing_flat(flat, needles) == []
    assert flat.index("git pull") < flat.index("python3 -m workshop.plugin install") < flat.index(remove)
    assert flat.count("python3 -m workshop.plugin install") >= 2  # again, after the remove
    # the sub-check of C29 runs exactly that in a real codespace, since it is not verified
    check = " ".join(cells["C29"][1].split())
    assert _missing_flat(check, ("second ref", "python3 -m workshop.plugin install", remove, "claude plugin list")) == []
    assert "uninstall" in " ".join(cells["C29"][3].split())  # the other way, if the row does not work
    assert "C29" in texts["C40"]


def test_timeline_starts_the_codespaces_during_the_welcome(root):
    """Without a prebuild the image build is part of exercise 00's 20 minutes, unless it runs during the welcome."""
    section = _section(_instructor(root), "## Timeline")
    needles = ('README "Start" steps 1-3', "0:00", "welcome", "prebuild", "image build", "exercise 00")
    assert _missing_flat(section, needles) == []


def test_step_4_says_how_a_fix_reaches_an_orphan_commit(root):
    steps = _steps(_section(_instructor(root), "## Before the workshop"))
    needles = ("C4", "C7", "C24", "orphan commit again", "force-push", "git branch -D public", "before participants create")
    assert _missing_flat(steps[4], needles) == []


def test_step_2_checks_the_whole_tree_before_it_is_published(root):
    """The orphan commit publishes main's whole tree: docs and notes with local paths must go first."""
    step = " ".join(_steps(_section(_instructor(root), "## Before the workshop"))[2].split())
    needles = ("docs/", "every other tracked file", "local drive paths", "private notes", "remove them first")
    assert _missing_flat(step, needles) == []
    assert step.index("private notes") < step.index("git checkout --orphan")


def test_gitignore_lists_no_folder_that_nothing_uses(root):
    """`verify-runs/` was listed, and nothing wrote to it: every project folder in .gitignore is named somewhere."""
    lines = stored_bytes(root, ".gitignore").decode("utf-8").splitlines()
    tool_folders = {".venv/", "__pycache__/", ".pytest_cache/"}
    folders = [line for line in lines if line.endswith("/") and line not in tool_folders]
    assert "work/" in folders and "calculix-manual/" in folders
    others = "\n".join(_text(root, rel) for rel in PARTICIPANT_DOCS) + _instructor(root) + _text(root, "workshop/verify.py")
    assert [folder for folder in folders if folder not in others] == []
    assert "verify-runs/" not in lines


def test_exercise_00_quotes_what_the_tool_check_prints(root):
    """`2.21 (exit 201)` is the ccx row's Found column, as `workshop.check_tools` prints it."""

    def run(argv, cwd, timeout_s):
        if list(argv) == ["ccx", "-v"]:
            return Completed(201, "\n  This is Version 2.21\n\n")
        raise FileNotFoundError(argv[0])

    (ccx_row,) = [row for row in check_tools.check(run) if row.tool == "ccx"]
    assert ccx_row.status == check_tools.OK
    text = " ".join(_exercise(root, "00-setup").split())
    assert f"The `ccx` row shows `{ccx_row.found}` and a note" in text
    assert "exit code 201" in text
    assert ccx_row.note.startswith("exits 201 after printing its version")


def test_participants_are_not_sent_to_the_instructor_notes_for_ccx_or_claude():
    """INSTRUCTOR.md says participants never need it: their messages say 'exercise 01' and 'ask the instructor'."""
    assert "INSTRUCTOR" not in check_tools.CCX_EXIT_NOTE
    assert "(exercise 01)" in check_tools.CCX_EXIT_NOTE


def test_exercise_02_gives_the_current_reason_for_the_folder(root):
    """An included file next to its deck is no longer cross-checked on its own: that is not the reason any more."""
    text = " ".join(_exercise(root, "02-gmsh-beam").split())
    assert "inputs/examples/" in text
    assert "as a deck of its own" not in text
    assert "keeps the self-weight runs out of the cross-check that runs at every check" in text


def test_exercise_02_meshes_never_overwrite_each_other(root):
    text = _exercise(root, "02-gmsh-beam")
    commands = [line.strip() for line in _section(text, "## The Gmsh commands").splitlines() if line.strip().startswith("gmsh beam.geo")]
    outputs = {}
    for command in commands:
        words = shlex.split(command)
        outputs["L 500" if "500" in words else "L 1000"] = words[words.index("-o") + 1]
    assert outputs == {"L 1000": "beam_mesh.inp", "L 500": "beam_mesh_500.inp"}
    study = _section(text, "## The study")
    copy = 'cp "$WORKSHOP_ROOT/work/gmsh-mesher/outputs/beam_mesh_500.inp" "$WORKSHOP_ROOT/work/beam-ccx/inputs/L500/beam_mesh.inp"'
    assert copy in study  # the deck includes beam_mesh.inp by name: the copy gives the L = 500 mesh that name
    assert text.index("inputs/L500") < text.index(copy)


def test_exercise_04_says_how_two_servers_are_used_together(root):
    """Both servers are registered for their own folder only (exercise 01, Phase 8): say how to work with two."""
    text = " ".join(_exercise(root, "04-cable-section").split())
    needles = ("Only this folder", "work in each server's folder in turn", "hand files over with `cp`", '"Every folder" in Phase 8')
    assert _missing_flat(text, needles) == []


# The Gmsh results that were confirmed before the workshop, with the same Gmsh package. Each is a number or a name that
# only a real Gmsh could give; the ccx parts of the same rows are still open until the codespace run.
GMSH_CONFIRMED = (
    "same Gmsh package",
    "Ubuntu 24.04",
    "4 `CPE6` blocks",
    "48 faces",
    "node 2 at (10, 0)",
    "node 8 at (24, 0)",
    "93 lines",
    "-3",
    "-format",
    "-setnumber",
    "32 126 nodes",
    "byte-identical",
    "`**`",
    "comment prefix",
    "x = 1000",
    "x = 0",
    "exit 0",
)


def test_instructor_notes_the_gmsh_results_confirmed_beforehand(root):
    _, _, texts = _checklist(_instructor(root))
    for row in ("C5", "C6", "C22", "C23", "C36", "C38"):
        assert _missing_flat(texts[row], GMSH_CONFIRMED) == [], row
    assert _missing_flat(texts["C22"], ("ccx parts", "codespace")) == []
    intro = _section(_instructor(root), "## Checklist").split("### The basics")[0]
    assert _missing_flat(intro, ("confirmed beforehand", "same Gmsh package", "ccx parts")) == []


def test_instructor_has_the_final_checks(root):
    ids, cells, texts = _checklist(_instructor(root))
    assert ids[-4:] == ["C39", "C40", "C41", "C42"]
    timing = " ".join(" ".join(cells["C41"][1:]).split())
    assert _missing_flat(timing, ("02", "03", "45", "25", "Timeline", "dry run")) == []
    prompts = " ".join(" ".join(cells["C42"][1:]).split())
    needles = ("permission prompts", "/mcp-anything", "scripts/", "uv run", "01 README", "how to answer")
    assert _missing_flat(prompts, needles) == []


def test_the_permission_hook_is_documented(root, tmp_path):
    """The README says what the hook does and how to remove it; INSTRUCTOR.md quotes the log line, the checks and the way off."""
    readme = _text(root, "README.md")
    assert _missing_flat(
        readme,
        (permissions.HOOK_PATH, "~/.claude/settings.json", "hooks.PreToolUse", "every other command still asks", "remove it"),
    ) == []
    # "If something is missing" sends whoever installed the plugin by hand to the hook step
    step_4 = readme.split("## If something is missing")[1].split("## Exercises")[0].split("4. **The permission hook**")[1]
    assert _missing_flat(step_4, ("python3 -m workshop.permissions", "after logging in", "restart Claude Code")) == []
    text = _instructor(root)
    plugin_root = tmp_path / ".claude" / "plugins" / "cache" / "mcp-anything" / "mcp-anything" / "1.0.0"
    (plugin_root / "extras").mkdir(parents=True)
    (plugin_root / permissions.HOOK_SOURCE).write_text("# hook", encoding="utf-8")
    logged = permissions.install_hook(tmp_path, plugin_root)
    assert logged.startswith(permissions.INSTALLED)
    _, cells, texts = _checklist(text)
    c42 = " ".join(" ".join(cells["C42"]).split())
    needles = (
        logged,
        "python3 -m workshop.permissions",
        "grep 'permission hook' ~/workshop-setup.txt",
        "grep -c allow_mcp_anything_scripts ~/.claude/settings.json",
        "70 to 90",
        "plugin script calls that still asked",
        f"{permissions.NOT_INSTALLED}: <reason>; participants will see the normal prompts",
        "is not valid JSON",
    )
    assert _missing_flat(c42, needles) == []
    assert _missing_flat(texts["C17"], (permissions.HOOK_SOURCE.as_posix(),)) == []
    troubleshooting = _section(text, "## Troubleshooting")
    in_a_cell = permissions.HOOK_COMMAND.replace("|", "\\|")  # a pipe in a table cell is escaped
    assert in_a_cell.endswith("\\|\\| true")
    needles = (permissions.NOT_INSTALLED, in_a_cell, "hooks.PreToolUse", "A missing or broken script is harmless", "blocks nothing")
    assert _missing_flat(troubleshooting, needles) == []
    assert _missing_flat(_section(text, "## Timeline"), ("the method still asks its own consent questions in the chat",)) == []
    assert _missing_flat(_steps(_section(text, "## Before the workshop"))[1], (permissions.HOOK_SOURCE.as_posix(),)) == []


def test_instructor_after_the_workshop(root):
    section = _section(_instructor(root), "## After the workshop")
    assert _missing_flat(section, ("archive the Console workspace", "delete the codespaces", "remove the secrets")) == []


def test_instructor_quotes_the_lines_that_post_create_prints(root):
    """The checklist and the troubleshooting table quote post-create.sh and the dev container: keep them in step."""
    text = _instructor(root)
    script = _text(root, ".devcontainer/post-create.sh")
    for line in ("uv cache: ready", "SETUP OK (uv cache not pre-filled:", "SETUP INCOMPLETE", "SETUP OK"):
        assert line in script and line in text, line
    _, _, texts = _checklist(text)
    expected = ["2.21-1", "4.12.1", "3.12", "0.13.5", "v24", "2.1.308"]
    assert [EXPECTED[key].rstrip(".") for key in ("calculix-ccx", "gmsh", "python3", "uv", "node", "claude")] == expected
    assert _missing_flat(texts["C1"], expected) == []
    pins = dict(re.findall(r"^ARG[ \t]+(\w+)=(\S+)[ \t]*$", _text(root, ".devcontainer/Dockerfile"), re.MULTILINE))
    assert _missing_flat(texts["C28"], (pins["CALCULIX_VERSION"], pins["GMSH_VERSION"])) == []


def test_instructor_names_only_files_that_exist(root):
    files = {path.relative_to(root).as_posix() for path in repo_files(root)}
    unknown = []
    for name in sorted(set(_REPO_PATH.findall(_instructor(root)))):
        name = name.rstrip(".")
        if name in FOREIGN_FILES or name in files or any(f.startswith(name + "/") for f in files):
            continue
        unknown.append(name)
    assert unknown == []
    # the pattern itself: a path ends at a comma, and keeps a final full stop (which the loop above trims)
    assert _REPO_PATH.findall("see exercises/02-gmsh-beam/README.md, workshop/nope.py.") == [
        "exercises/02-gmsh-beam/README.md",
        "workshop/nope.py.",
    ]


class _Parsed(Exception):
    """Raised by the stub in `_accepts` once the tool's parser has accepted the command line."""


def _accepts(module_name: str, args: list[str], monkeypatch) -> None:
    module = importlib.import_module(f"workshop.{module_name}")

    def parse_and_stop(self, argv=None, namespace=None):
        _PARSE_ARGS(self, argv, namespace)  # exits with status 2 on a command line that the tool does not accept
        raise _Parsed

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", parse_and_stop)
    with pytest.raises(_Parsed):
        module.main(args)


def test_command_guard_self_check(monkeypatch):
    """`_accepts` must refuse a command line that the tool's own parser refuses, or the next test proves nothing."""
    with pytest.raises(SystemExit):
        _accepts("plugin", ["bogus"], monkeypatch)
    with pytest.raises(SystemExit):
        _accepts("check_tools", ["--nope"], monkeypatch)
    _accepts("plugin", ["print"], monkeypatch)


def test_instructor_commands_are_accepted_by_the_tools(root, monkeypatch):
    """Every `python3 -m workshop.<tool> ...` in INSTRUCTOR.md names a tool and arguments that its parser accepts."""
    seen = set()
    for module_name, rest in re.findall(r"python3 -m workshop\.(\w+)([^`\n]*)", _instructor(root)):
        assert (root / "workshop" / f"{module_name}.py").is_file(), module_name
        if module_name in ("plugin", "check_tools", "manual", "generate"):
            _accepts(module_name, shlex.split(rest.split(" #")[0]), monkeypatch)
        seen.add(module_name)
    assert {"plugin", "check_tools", "manual", "generate"} <= seen


def test_ci_workflow(root):
    text = _text(root, CI_WORKFLOW)
    needles = (
        "runs-on: ubuntu-24.04",
        "actions/checkout@v7.0.1",
        "astral-sh/setup-uv@v10.3.2",
        'version: "0.13.5"',
        "uv run pytest -q",
    )
    assert _missing_flat(text, needles) == []
    assert "-m solver" not in text  # CI runs no solver
    assert text == CI_TEXT
    assert f'version: "{EXPECTED["uv"]}"' in text  # the uv of CI is the uv of the dev container


_USES = re.compile(r"^[ \t]*(?:-[ \t]+)?uses:[ \t]*(\S+)", re.MULTILINE)
_PINNED_REF = re.compile(r"v\d+\.\d+\.\d+|[0-9a-f]{40}")


def _pinned(action: str) -> bool:
    """`owner/name@vX.Y.Z` or `owner/name@<40 hex>`: a full version or a commit, never a major tag or a branch."""
    name, at, ref = action.partition("@")
    return bool(name) and at == "@" and _PINNED_REF.fullmatch(ref) is not None


def test_pinned_action_guard_self_check():
    sample = "      - uses: a/b@v1.2.3\n        uses: c/d@main\n  uses:e/f@v1\n"
    assert _USES.findall(sample) == ["a/b@v1.2.3", "c/d@main", "e/f@v1"]
    assert _pinned("astral-sh/setup-uv@v10.3.2")
    assert _pinned("actions/checkout@" + "0123456789abcdef" * 2 + "01234567")
    for bad in ("astral-sh/setup-uv@v10", "astral-sh/setup-uv@v10.3", "actions/checkout@v7", "a/b@main", "a/b@v1.2.3-rc1", "a/b", "a/b@abc123"):
        assert not _pinned(bad), bad
    assert not _pinned("a/b@" + "0123456789abcdef" * 2 + "0123456")  # 39 hex digits
    assert not _pinned("a/b@" + "0123456789abcdef" * 2 + "012345678")  # 41 hex digits


def test_ci_workflow_pins_every_action_to_a_full_version(root):
    """setup-uv publishes no major or minor tags, so `@v10` does not exist: CI would not even start."""
    actions = _USES.findall(_text(root, CI_WORKFLOW))
    assert len(actions) >= 2
    assert [action for action in actions if not _pinned(action)] == []


def test_instructor_c26_names_the_actions_that_ci_uses(root):
    """The row that tells the instructor what CI runs names exactly the actions and versions of ci.yml."""
    actions = _USES.findall(_text(root, CI_WORKFLOW))
    _, _, texts = _checklist(_instructor(root))
    assert _missing_flat(texts["C26"], [f"`{action}`" for action in actions]) == []
    row = " ".join(texts["C26"].split())
    assert not re.findall(r"(?:checkout|setup-uv)@v\d+(?![\d.])", row), "a version that is not a full one"


# ---- nothing private or internal in a public file --------------------------------------------------------------------

# The repository may be published. Each pattern is written so that this file does not match it itself.
_PRIVATE_TEXT = {
    "a drive path": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]"),
    "a process folder": re.compile(r"\.super[p]owers"),
    "an internal decision word": re.compile(r"\b[Rr]u[l]ing"),
    "an internal decision id": re.compile(r"\b(?:[WK]\d+|P\d{2,})\b"),
    "an internal branch name": re.compile(r"feat/pl[a]n"),
    "a plan number": re.compile(r"\bPlans? \d"),
    "a task number": re.compile(r"\bTask \d"),
    "process language": re.compile(r"\b(?:[Cc]ontrol[l]er|Review[ ]Focus|[Pp]re-fl[i]ght|[Pp]reflig[h]t)\b"),
}
_NOT_SCANNED = frozenset({"uv.lock", "LICENSE"})


def _private_hits(rel: str, text: str) -> list[str]:
    """The kinds of private or internal text in `text`. The tests may name a Windows drive as data."""
    return [
        name
        for name, pattern in _PRIVATE_TEXT.items()
        if (name != "a drive path" or not rel.startswith("tests/")) and pattern.search(text)
    ]


def test_private_text_guard_self_check():
    flagged = [
        ("a drive path", "cd F" + ":/work/x"),
        ("a drive path", "see C" + ":\\x"),
        ("a process folder", "the .super" + "powers/sdd folder"),
        ("an internal decision word", "ru" + "ling 1"),
        ("an internal decision word", "Ru" + "ling"),
        ("an internal decision id", "P" + "15"),
        ("an internal decision id", "(W" + "10)"),
        ("an internal decision id", "K" + "21"),
        ("an internal branch name", "feat/pl" + "an3-x"),
        ("a plan number", "Plan" + " 2"),
        ("a plan number", "Plans" + " 2 and 5a"),
        ("a task number", "Task" + " 5"),
        ("process language", "the contr" + "oller"),
        ("process language", "Review" + " Focus 1"),
        ("process language", "the pre" + "-flight review"),
    ]
    for name, sample in flagged:
        assert name in _private_hits("notes.md", sample), (name, sample)
    harmless = (
        "https://example.org/x",
        "P1, P2 and P3 are the faces of a triangle",
        "C4, C16 and so on",
        "open-ended task 1",
        "the plane strain model, Phase 4, a 4-core machine, UTF-8",
        "version_exit_codes=(0, 201)",
    )
    for sample in harmless:
        assert _private_hits("notes.md", sample) == [], sample
    assert _private_hits("tests/test_manual.py", "C" + ':/x/owned.txt') == []  # a drive name as test data
    assert _private_hits("workshop/manual.py", "C" + ":/x/owned.txt") == ["a drive path"]


def test_no_private_paths_or_internal_ids_in_the_repository(root):
    """Documents, code, scripts, tests and configuration: no local path, process folder, branch name or internal decision id."""
    found = {}
    for path in repo_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in _NOT_SCANNED:
            continue
        if hits := _private_hits(rel, stored_bytes(root, rel).decode("utf-8")):
            found[rel] = hits
    assert found == {}
