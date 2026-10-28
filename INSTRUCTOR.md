# Instructor notes

These notes are for the person who runs the workshop. Participants start from [README.md](README.md) and never need
this file.

Nothing in this repository ran CalculiX, Gmsh, Docker or Claude Code while it was written, and CI runs no solver. What
only a real codespace can show is a row of the [checklist](#checklist): work through it in your own codespace before
the participants arrive. [Before the workshop](#before-the-workshop) gives the steps in order,
[Troubleshooting](#troubleshooting) the usual failures on the day.

## Before the workshop

Steps marked **You** reach outside this repository (GitHub, the Console, a paid codespace). Do them yourself: no script
and no assistant does them for you.

1. **You: bring MCP-Anything's `main` up to the release you will publish** (the plugin must be on `main` before it
   can be published). It must be the release of MCP-Anything that includes the batch-solver route and its
   `version_exit_codes` support (required for 01). The knowledge command (`/mcp-anything:knowledge`: 03, Phase 4 of
   01) and the expand command (`/mcp-anything:expand`: the expand path of 02) are needed only for those parts. Run
   these commands in your MCP-Anything checkout, with a clean working tree; merge only finished, reviewed work.

   ```bash
   cd <your MCP-Anything checkout>
   git switch main
   git merge --ff-only <branch>                   # the batch-solver route with version_exit_codes (required for 01)
   grep -n version_exit_codes METHOD.md           # METHOD Phase 6 documents it
   git merge --no-edit <branch>                   # the knowledge command, if finished (03; Phase 4 of 01)
   git merge --no-edit <branch>                   # the expand command, if finished (the expand path of 02)
   uv run pytest -q                               # resolve any merge conflict first; the banned-name scan runs here
   ```

   Without the knowledge and expand commands: skip 03, and take the second-server path in 02 (part A, the Gmsh server,
   and the study by hand).

   The release should also hold `extras/allow_mcp_anything_scripts.py`, the optional permission hook that
   `post-create.sh` installs (C17, C42). An older release without it still works: participants then see all of Claude
   Code's prompts.

2. **You: rehost MCP-Anything publicly**, with a history that starts clean, and tag it. A private marketplace needs each
   participant's git credentials (Claude Code's plugin documentation for organisations,
   code.claude.com/docs/en/plugins/org). Create the public repository on GitHub first. Check `git config user.name` and
   `git config user.email` before you commit: they are published with every commit. The orphan commit publishes main's
   whole tree, not only the plugin: check MCP-Anything's `docs/` and every other tracked file for local drive paths
   and private notes (`git grep -nIE '(^|[^A-Za-z0-9])[A-Za-z]:[/\\]' main` finds drive paths; read `docs/` yourself), and remove them
   first, on `main`. Then run, in the same checkout after step 1:

   ```bash
   git checkout --orphan public main              # one fresh commit holding main's tree
   git commit -m "MCP-Anything 0.1.0"
   uv run pytest tests/test_repo.py -q            # the banned-name scan of exactly what is published
   git tag v0.1.0
   git remote add origin-public https://github.com/<owner>/mcp-anything.git   # the new public repository, created on GitHub first
   git push origin-public public:main
   git push origin-public v0.1.0
   ```

   Afterwards `git switch main` returns to your development line; the branch `public` only exists to publish. The
   remote is not called `public`, so that its name cannot be confused with the branch.

3. **Set `MCP_ANYTHING_REPO=<owner>/mcp-anything#v0.1.0`** in `workshop.conf`. The tag pins exactly that commit, not
   whatever `main` holds on the day (C29). Run `uv run pytest -q` and commit. Until this is done,
   `python3 -m workshop.plugin` stops with exit 2 and names `workshop.conf`, and `python3 -m workshop.check_tools --ready`
   fails (C35).

4. **You: create the GitHub repository** for this workshop, publish `main` as one orphan commit (see below), and
   enable Codespaces.
   - Public repository: each participant's codespace is billed to their own account.
   - Organisation repository: check whether the organisation pays.
   - The banned-name test reads the current files, not the history. This repository's development history holds
     earlier drafts that must not be published: publish it only with the orphan-commit method of step 2, never by
     pushing `main` with its history.
   - A fix that you find later (in C4, C7 or C24, say) does not reach a repository that was published as an orphan
     commit by itself. Make the fix on `main` (or merge it into `main`), create the orphan commit again (`git branch -D public`, then
     `git checkout --orphan public main` and `git commit`, as in step 2), and force-push it
     (`git push --force <remote> public:main`) before participants create their codespaces: a codespace that exists
     already keeps the old history.
   - Check `git config user.name` and `git config user.email` before you commit or push: they are published with
     every commit.

5. **You, optional: set up a prebuild** for `main` (repository **Settings** > **Codespaces** > **Set up prebuild**; see
   GitHub's Codespaces documentation for the current options). A prebuild runs everything up to
   `updateContentCommand`. This repository's `devcontainer.json` has no such command, so a prebuild holds the built
   image. `post-create.sh` is the `postCreateCommand`, so it still runs for each participant. Whether a prebuild is
   worth it is your decision: the trade-off is under C13 (see "C13: the prebuild decision" below).

6. **You: create your own codespace** and work through the checklist: everything except C15 (a domain review) and C18
   (the evening before, for the copy to hand out, and on the morning of the workshop).

7. **You: prepare the API-key fallback.** Create a Console workspace with a spend limit, create one key per
   participant, and print a hand-out: the key, and a pointer to "Log in" in the README (see
   [Authentication](#authentication)).

## Timeline

Suggested; adjust. The times are a first estimate, and C30 measures whether exercise 01 fits its slot.

| Start | Minutes | What |
|---|---|---|
| 0:00 | 15 | Welcome and MCP-Anything's three rules |
| 0:15 | 20 | Exercise 00: setup |
| 0:35 | 70 | Exercise 01: cantilever |
| 1:45 | 10 | Break |
| 1:55 | 45 | Exercise 02: Gmsh beam |
| 2:40 | 25 | Exercise 03: documentation |
| 3:05 | 20 | Exercise 04: demo and start |
| 3:25 | 5 | Wrap-up |

Participants start their codespaces at 0:00, during the welcome: they follow README "Start" steps 1-3 while you talk.
Without a prebuild (step 5) the image build would otherwise be part of exercise 00's 20 minutes; C25 times it.

The workshop ends at 3:30. MCP-Anything's three rules (its `METHOD.md`), which the welcome explains:

1. Never touch the user's machine without permission. Inspecting the machine, running the program and opening a file
   outside the project folder each need the user's agreement first.
2. Never silently wrong. A server it builds fails loudly with an explicit error rather than return a plausible-looking
   result.
3. Nothing is built on an unconfirmed decision. Every phase ends with a summary card and a confirm or correct question.

Say in the welcome that the method still asks its own consent questions in the chat. The permission hook that
`post-create.sh` installs (C42) only spares participants Claude Code's prompt for each of the plugin's own script calls:
it cannot answer the method's questions, and every other command still prompts.

Without the knowledge and expand commands, drop 03 and the expand part of 02, and give the time to 04. Exercise 04 is
open-ended: demo it from the `--keep` folder of C23.

## Verify the decks

Run this once in your own codespace, and again after any change to a deck, to `workshop/beam.py`, `workshop/layers.py`,
`workshop/gmshinp.py` or to the dev container. It needs the real `ccx` and `gmsh`, so it runs only inside the dev
container.

```bash
scripts/verify_decks.sh                                                 # every case, with the whole table
scripts/verify_decks.sh --only 04 --keep "$WORKSHOP_ROOT/work/verify"   # one exercise; the run folders stay in that folder
uv run pytest -m solver -s                                              # the same verification, as one test
```

- **The output.** The script prints one row per check (the columns of the table below), then `VERIFY: PASS` or
  `VERIFY: FAIL`. Its exit code is 0 only when every check passed.
- **`--only`.** `--only 01`, `--only 02` or `--only 04` selects one exercise: 01 runs three cases (the cantilever, the
  broken deck and `ccx -v`), 02 two (L=1000 and L=500), 04 one.
- **`--keep`.** Give an absolute path: a relative one resolves against the repository root, because the script changes
  into it first. Each case runs in its own subfolder (`01-cantilever`, `01-broken-deck`, `version`, `02-beam-L1000`,
  `02-beam-L500`, `04-cable`), and the script prints `Run folders: <the folder>`. Without `--keep` the run happens in a
  temporary folder, which is removed when everything passed and kept when something failed.
- **`uv run pytest -m solver -s`** is one test that runs the same verification. The table shows with `-s`, or when the
  test fails. The default `uv run pytest -q` deselects it (`addopts` in `pyproject.toml`), so CI and your own computer
  never need a solver; where `ccx` or `gmsh` is missing, selecting it fails on purpose.
- **No solver.** When `ccx` or `gmsh` is missing, the script prints only "CalculiX or Gmsh not found: run this inside the
  workshop dev container (README.md)" and exits 1, with no VERIFY line.
- **Stricter than `check_tools`.** `verify` FAILs on another ccx version or another exit code than 0 or 201, where
  `python3 -m workshop.check_tools` only WARNs.

The expected values: 01 comes from `exercises/01-cantilever/reference.json`. 02 (L=1000 and L=500, the latter from
`beam.selfweight_reference(500)`) and 04 come from the formula helpers in `workshop/beam.py` and `workshop/layers.py`,
whose values equal the committed `reference.json` files (written by `python3 -m workshop.generate`). FE is the value
the finite-element run gave, Limit the allowed difference. Fill in the table from the script's output:

| Case | Quantity | Expected | FE | Limit | Result | Note |
|---|---|---|---|---|---|---|
| `01 cantilever` | `tip_displacement_y` | -2.5 mm, within 2 % (U_y at node 1211) | | | | |
| `01 cantilever` | `support_reaction_y` | 21 N, exact (RF total of `FIX`) | | | | |
| `01 broken deck` | `rejected: *ERROR reading *ELASTIC` | refused: `*ERROR reading *ELASTIC`, exit code 201 | | | | |
| `version` | `ccx -v` | `This is Version 2.21`, exit code 201 (0 is accepted) | | | | |
| `02 beam L=1000` | `tip_displacement_y` | -1.375 mm, within 2 % (mean over `TIP`) | | | | |
| `02 beam L=1000` | `support_reaction_y` | 30.80 N, within 1 % (RF total of `FIXED`; the printed total is about 30.77) | | | | |
| `02 beam L=500` | `tip_displacement_y` | -0.08595 mm, within 2 % (mean over `TIP`) | | | | |
| `02 beam L=500` | `support_reaction_y` | 15.40 N, within 1 % (RF total of `FIXED`) | | | | |
| `04 cable` | `u_r_core_edge` | -9.113e-05 mm, within 2 % (U_x at `P_CORE`) | | | | |
| `04 cable` | `u_r_outer` | -0.003571 mm, within 2 % (U_x at `P_OUTER`) | | | | |

Never loosen a tolerance to get a pass. Record the measured value and decide: is the deck wrong, the reference, or the
reader (`workshop/ccxdat.py`)? Fix what is wrong, say why in the commit, and run it again. The one tolerance that was
loosened, the 02 reaction, has a physical reason (the printed total of `FIXED` includes those nodes' own weight) that is
written into the reference's `source` text. C4 and C31 say what to look at by hand.

## Checklist

Each row gives what to check, what is expected (with where the expectation comes from), and what to do if it differs.
Work in your own codespace (step 6). "The C7 dry run" means a full run of exercise 01 with `/mcp-anything`, as a
participant does it, and the dry-run server it leaves behind.

Some Gmsh results were confirmed beforehand, with the same Gmsh package (4.12.1 from Ubuntu 24.04): see "C5, C6, C22,
C23, C36 and C38: confirmed beforehand with Gmsh" under Details. Run those rows in your codespace anyway: the ccx parts
of the same rows were not run, and only the codespace shows them.

### The basics (C1-C16)

| Id | Check | Expected | If different |
|---|---|---|---|
| C1 | Create a 4-core codespace from `main` and open a terminal. `whoami`; `cat ~/workshop-setup.txt`; `grep 'uv cache' ~/workshop-setup.txt`; `python3 -m workshop.check_tools`; `claude --version`; `echo "$DISABLE_AUTOUPDATER"` | The codespace builds and you are user `vscode`. The file ends with `SETUP OK`, and the `uv cache` line says `uv cache: ready`. Versions (the Dockerfile pins, `check_tools.EXPECTED`): ccx package 2.21-1, gmsh 4.12.1, Python 3.12, uv 0.13.5, node v24, claude 2.1.308. `claude --version` is still 2.1.308 after the first `claude` run, and `DISABLE_AUTOUPDATER` is `1`: no auto-update. | The image fails to build: read the creation log for apt `E: Version … not found` or a conflict on the gmsh pin (C28), for the NodeSource setup and for `npm install -g`. `SETUP INCOMPLETE`: the file names the failing row (see Troubleshooting). `SETUP OK (uv cache not pre-filled: …)`: every tool is fine, but the uv warm-up failed (the `uv cache: WARN` line and the last three lines of uv's answer are in the file); re-run `bash .devcontainer/post-create.sh` from the repository folder once the network is fine, or the first server build downloads more. |
| C2 | `which ccx; ccx -v; echo $?` | `/usr/bin/ccx`; `This is Version 2.21`, then `201` (see "ccx -v exits 201") | Another path: a wrapper or another ccx is first on `PATH`; remove it, there is no wrapper by design. Another version: C28. No version line: the package is broken, rebuild. |
| C3 | `claude plugin list` before logging in; `python3 -m workshop.plugin status`. Then the manual step: `python3 -m workshop.plugin print`, and type the two lines in Claude Code | `mcp-anything@mcp-anything`, installed by `post-create.sh`; otherwise the manual step works: the scope prompt offers "Install for you (user scope)", `/plugin` has an **Installed** tab that lists it, `claude plugin list` prints `mcp-anything@mcp-anything` and `status` exits 0. Whether the shell commands work before a login is unverified | The shell commands need a login first: every codespace ends `SETUP INCOMPLETE`, and participants run `python3 -m workshop.plugin install` after they log in (README, "If something is missing"); say so in the welcome. The marketplace cannot be cloned: the repository is private (step 2) or the tag is wrong (C29). The placeholder is still in `workshop.conf`: C35. |
| C4 | `scripts/verify_decks.sh`, then the table in "Verify the decks". By hand: "C4 and C31: the decks by hand" | all PASS: 01 within 2 % and the reaction exact; the broken deck refused (`*ERROR reading *ELASTIC`, 201); 02 for L = 1000 and 500, with the displacement within 2 % and the reaction within 1 % (the printed RF total of `FIXED` holds the FIXED nodes' own self-weight share); 04 within 2 %. Source: each exercise's `reference.json` | Never loosen a tolerance. Run the failing deck by hand to see which part is wrong (the deck, the reference or `ccxdat`), and fix that. |
| C5 | The Gmsh `.inp` files, meshed by hand: "C5, C32 and C38: the Gmsh meshes by hand" | only `C3D10` (02) and `CPS6` (04) element blocks; ELSET and NSET named by the physical names; the included `*Heading` is accepted. `gmsh --version` prints 4.12.1 (the Gmsh source cited in the exercises is the tag `gmsh_4_12_1`; the excerpts could not be pinned to the package) | Another element block: C32. A name missing from the sets: the `Physical` names in the `.geo`. |
| C6 | 04 | no clockwise elements; `P_CORE` and `P_OUTER` printed for the 2-D nodes (ccx expands CPE6 into 3-D elements, so the `.dat` may hold more than one node per set: the check takes the row whose node number is in the set of `cable_mesh.inp`). `ccx -i cable_pressure` exits 0; U_x is about -9.113e-05 mm at `P_CORE` and -0.003571 mm at `P_OUTER` (2 %); the Note column of the `04 cable` rows says how many rows ccx printed for each set | Clockwise triangles: reverse the curve loops in the `.geo` (Troubleshooting). Note how ccx really prints the rows, and correct the "Reading the result" paragraph of the 04 README if it differs. |
| C7 | A full dry run of 01 with `/mcp-anything`, from Phase 1 to Phase 8 | Phase 2 proposes `help_output` with `-v` and records exit 201 with the version line, and the inventory card shows ✘ Command line; Phase 6 sets `version_exit_codes=(0, 201)` from it; schema citations match the manual sections; cross-check and golden pass; Phase 8 asks to approve the server, and `/mcp` shows it connected. A local dry run in the workshop container (CalculiX 2.21, no codespace, no login) passed on 2026-10-27: `batch_solver` recommended, version 2.21 with `(0, 201)`, `/mcp-anything:check` PASS (15 audit checks, 29 tests), and a tip displacement of -2.4948 mm against -2.5 mm (0.21 %) with a reaction of 21 N. Claude Code was not driven interactively there, so Phase 8's approval and `/mcp`, the timing (C30), the permission prompts (C42) and a real login are not covered: the codespace dry run is still yours | Correct the 01 README to what the plugin really asks. A plugin without the `version_exit_codes` support: C16 and C17. |
| C8 | Login in the codespace's browser | the callback works, or the paste-code path does. Note the first-run login choices of claude 2.1.308 (subscription or Console), and whether `Paste code here if prompted` appears | Change "Log in" in the README to what you saw. |
| C9 | The API-key fallback with a test key | Claude Code asks once, `/status` shows the key. Note the "Detected a custom API key" question and its default (the README says to choose Yes); `unset ANTHROPIC_API_KEY` returns to the subscription; where the `/config` toggle for the key is and what it is called | Correct the README ("Log in") and the Troubleshooting row for `ANTHROPIC_API_KEY`. |
| C10 | `python3 -m workshop.check_tools --ready` | exit 0 | A FAIL row: Troubleshooting. A FAIL on `workshop.conf`: step 3. |
| C11 | 03 on the HTML manual | the knowledge build succeeds (523 UTF-8 pages; PNGs not copied). Note whether the agent runs a conversion trial or serves the HTML manual directly, the option label "Serve it section by section", and that the `*CLOAD` answer cites §7.15 | Change step 4 of the 03 README to the real flow and label. |
| C12 | Machine type and billing: GitHub **Code** > **Codespaces** > **...** > **New with options...** | participants can create a 4-core codespace and know who pays. The dialog shows a branch picker and offers 4-core (16 GB RAM, 32 GB storage) and larger machines, not 2-core; then **Create codespace** | A 2-core machine is offered: `hostRequirements` in `devcontainer.json` is not applied. No 4-core machine: the owner's policy or billing blocks it (step 4). |
| C13 | Prebuild, if used | the codespace opens from the prebuild and `post-create.sh` still runs. The decision is yours: "C13: the prebuild decision" | The codespace does not open from the prebuild, or `post-create.sh` did not run: check that the prebuild is for the branch the participant chose and has finished. Not used: C25 gives the time it would save. |
| C14 | `echo $WORKSHOP_ROOT` in a new terminal, in bash and in zsh | the repository path | A terminal opened before the setup finished has no `WORKSHOP_ROOT`: open a new one. `post-create.sh` appends it to `~/.bashrc` and `~/.zshrc`. |
| C15 | 04's material values and the simplification statement | reviewed by someone who knows cables | Correct the values in `workshop/layers.py` and the 04 README table together (the tests pin them to each other), then run `python3 -m workshop.generate`. Until reviewed, say in the demo that the values are illustrative. |
| C16 | The version gate with the real `ccx`, in the dry-run server from C7 | `get_backend()` passes `version_exit_codes=(0, 201)`; `uv run --directory <server> python -c "from <pkg>.server import server_status; print(server_status())"` shows `version` `2.21` and `version_error` `None`; the MCP-Anything in use has the `version_exit_codes` support (C17; else stop and publish a release with it, steps 1-3) | `ccx exited with code 201` or `UNKNOWN_VERSION`: Troubleshooting. |

### In the codespace and on the day (C17-C32)

Each item checks something that only a real codespace can show:

| Id | Check | Expected | If different |
|---|---|---|---|
| C17 | In the codespace: `find ~/.claude/plugins -path '*mcp-anything*' -name METHOD.md`; `grep -n version_exit_codes` in it; `ls` its `templates/routes/batch_solver` and `extras/allow_mcp_anything_scripts.py`. In Claude Code, type `/` | found; METHOD Phase 6 mentions `version_exit_codes`; the batch-solver template exists; the permission hook script exists (C42; an older release has none, and the setup log says so). `/` lists `/mcp-anything` and `/mcp-anything:check`, and `/mcp-anything:knowledge` and `/mcp-anything:expand` once the published MCP-Anything has them | publish a release whose METHOD Phase 6 documents `version_exit_codes` and that has `templates/routes/batch_solver` (steps 1-2), tag it, update `workshop.conf` (step 3) |
| C18 | Morning of the workshop, a fresh codespace: `python3 -m workshop.manual html`, then `pdf` | both exit 0; the pinned SHA-256 and sizes still match | a changed hash or size: stop and re-check the archive (never loosen the pin). Site down, or too slow for the whole room: both files come from the same site (www.dhondt.de), so the PDF is no fallback for the HTML. The evening before, fetch both files yourself and check them with `--archive` ("C18 and C39: the manual from your own copy"), and hand them out: participants then run `python3 -m workshop.manual html --archive <file>`. Give out the file from a shared drive, or as a release asset of this repository that you upload yourself; that upload is your decision, and nothing in git holds the manual |
| C19 | C7 dry run, Phase 3, with the README's run-time answer | the route card recommends `batch_solver` | change the README answer until it does |
| C20 | C7 dry run, Phase 4, with "No documentation for now" | `knowledge` = `none`, or examples-only (`inputs/examples/`); the build goes on | update the 01 and 03 READMEs, or fold 03 into 01 and adjust the timeline |
| C21 | C7 dry run, the agent's own broken decks | the cross-check passes, with `solver_accepted` refusing `Card image cannot be interpreted` | adjust the README sentence; never remove the protected test |
| C22 | A dry run of 02 on both paths | `gmsh --help` prints usage, lists `-setnumber` and exits 0 headless; `/mcp-anything` recommends `cli` for Gmsh; `-setnumber L 500` given after the file takes effect; `-1000`/`-100` give only C3D10 blocks, the ELSET `BEAM` and the NSETs FIXED/TIP; the CalculiX schema gains the 02 keywords and `expand` accepts it with a new `schema_reviewed`; expand adds the averaging tool (a TIP-mean read tool and a compare tool); the golden check at L = 1000 matches. A local dry run of 02 in the workshop container (Gmsh 4.12.1, CalculiX 2.21, no codespace, no login) passed on 2026-10-27: the Gmsh server passed `/mcp-anything:check` (48 tests), the CalculiX server was expanded and passed it (43 tests, a new `schema_reviewed`), and the self-weight results at L = 500, 750, 1000 and 1500 were within 0.3 % of beam theory (L = 1000: -1.3728 mm against -1.375 mm, reaction 30.78 N against 30.80 N; the tip moves 16.01 times as far at L = 1000 as at L = 500). The approval and restart of the Gmsh server, the timing (C41), the permission prompts (C42) and a real login are not covered: the codespace dry run is still yours | rewrite the failing 02 path, or keep only the path that works |
| C23 | 04 with the `workshop.gmshinp` commands (by hand: `export PYTHONPATH="$WORKSHOP_ROOT"` first, as in the 04 README), and `scripts/verify_decks.sh --only 04 --keep "$WORKSHOP_ROOT/work/verify"` (an absolute path) | the same values as C4; `plane-strain` accepts Gmsh's triangle orientation (no clockwise element); the `P_CORE` and `P_OUTER` rows are as in C6; the demo folder `$WORKSHOP_ROOT/work/verify/04-cable` is ready | demo from the `--keep` folder |
| C24 | Spot-check the citations against the 2.21 PDF: the 01 README table, `decklint.KEYWORDS`, §3, the §5.1 quote, §6.2.4/6.2.5/6.2.7/6.2.25 | every number and quote is right | correct `decklint.py` and the README, run the tests |
| C25 | A codespace without prebuild, timed until `SETUP OK`; `df -h /` | well under 20 minutes; the disk is not near full. Note both numbers | set up the prebuild (C13); the repository owner pays its storage and Actions minutes |
| C26 | After step 3: `uv run pytest -q` locally, and CI after the push (`.github/workflows/ci.yml`: `ubuntu-24.04`, `actions/checkout@v7.0.1`, `astral-sh/setup-uv@v10.3.2` with uv 0.13.5, no solver; both are pinned to a full release, the latest on 2026-10-27: setup-uv publishes no major or minor tag, so `@v10` does not exist) | both green | fix before participants arrive; CI does not block codespaces. A run that cannot even start names an action version that does not exist: look up its tags and pin a full one |
| C27 | `git ls-files -s scripts/verify_decks.sh .devcontainer/post-create.sh`; `ls -l` in the codespace | `100755`, executable | `git update-index --chmod=+x <path>`, commit, push |
| C28 | `apt-cache policy calculix-ccx gmsh libgmsh4.12` in the built container | installed = pinned (2.21-1, 4.12.1+ds1-1.1build2) | update the Dockerfile ARGs and `check_tools.EXPECTED` together, run the tests |
| C29 | (a) With `#<tag>` in `workshop.conf`: `claude plugin marketplace list`. (b) The move to another tag, which is not verified: with the plugin installed from that tag, change `workshop.conf` to a second ref of the same repository (a tag or branch you make for this check), run `python3 -m workshop.plugin install`, then `claude plugin marketplace list` and `claude plugin list`; then `claude plugin marketplace remove mcp-anything`, `claude plugin list` again, and `python3 -m workshop.plugin install`, `claude plugin marketplace list`, `claude plugin list` | (a) the marketplace was added at that ref (documented: "`owner/repo`. Add `#ref` to pin a branch or tag", code.claude.com/docs/en/plugins/install). (b) `install` prints `workshop.conf names …`, then that the plugin was installed already and is not updated; the marketplace is still at the old ref (this is why the Troubleshooting row for an existing codespace exists); after the remove and the second `install` it is at the new ref and `python3 -m workshop.plugin status` exits 0. Note whether the remove also took the plugin out | (a) use the full git URL with `#<tag>`, or drop the tag and publish `main` exactly as tagged. (b) the sequence does not work: find the one that does (for example `claude plugin uninstall mcp-anything@mcp-anything` first, or `claude plugin marketplace update mcp-anything`), and write it into the Troubleshooting row and into `not_updated_note()` in `workshop/plugin.py` |
| C30 | Time the C7 dry run of 01 end to end with a Pro account | fits the 70-minute slot without hitting the usage limit | shorten 01, or tell participants to have the API-key fallback ready |
| C31 | In the C4 run with `--keep "$WORKSHOP_ROOT/work/verify"`: a successful ccx exit code, and the `.dat` layout of one displacement and one total-force block (01: the `displacements (vx,vy,vz) for set TIPC` block and the `total force (fx,fy,fz) for set FIX` block) | exit 0; headers and rows as `ccxdat` expects | correct `ccxdat` and its tests to the real layout; never loosen the comparison |
| C32 | If Gmsh writes `CPS6`/`T3D3` blocks in 02, or `T3D3` in 04 (C5 fails) | — (this row applies only when C5 fails) | read how `GModelIO_INP.cpp` at `gmsh_4_12_1` selects elements, adjust the `.geo` options, re-run C4; never drop blocks silently in `to_plane_strain`. For 04, `Mesh.SaveGroupsOfElements = -100` keeps the `T3D3` line elements out of the cable mesh; without it `plane-strain` refuses the mesh |

### More checks (C33-C42)

Detached runs, the image, headless Gmsh, the secret, the beam mesh, the manual outage, the move to a new tag, the
timing of 02 and 03 and the permission prompts:

| Id | Check | Expected | If different |
|---|---|---|---|
| C33 | Detached jobs survive Claude Code. On the C7 server (exercise 01), run a deck that takes about a minute ("C33: a slower deck"): (1) start it with the core action; (2) quit Claude Code (`/exit`) while it runs; (3) reopen `claude` in the server's folder; (4) ask for `job_status` | `job_status` shows `finished`: the run went on without Claude Code, which is what the 01 run-time answer ("keep going after I close Claude Code") promises | A lost or failed job: the run was not detached (a job's record says whether it is `detached`). Do not tell participants that runs survive; report it to MCP-Anything, and rewrite the 01 run-time answer |
| C34 | The image, as `vscode`: `uv python find 3.12`; `uv cache dir`; `du -sh "$(uv cache dir)"`; `echo "[$DEBIAN_FRONTEND]"` | `/usr/bin/python3.12`; a path under `/home/vscode`, with a cache that is not empty (the warm-up filled it); `[]` (DEBIAN_FRONTEND is empty: the Dockerfile sets it as a build argument only) | A path under `~/.local/share/uv/python`: uv downloaded its own Python instead of using Ubuntu's `python3` (`uv python find` itself never downloads, so the path is the signal; see C1). `uv cache dir` reports the directory of the current user: run it as `vscode`, and a tiny `du` means the warm-up failed (C1). `DEBIAN_FRONTEND` set: it leaked into the participants' shells (look for an `ENV` line in the Dockerfile) |
| C35 | The placeholder, in your own codespace: put the placeholder back in `workshop.conf` (its value is `PLACEHOLDER` in `workshop/config.py`), then run `python3 -m workshop.plugin install` and `python3 -m workshop.check_tools --ready` (note each exit code with `echo $?`), `bash .devcontainer/post-create.sh` and `cat ~/workshop-setup.txt`. Finish with `git checkout workshop.conf`, run `bash .devcontainer/post-create.sh` again and check that the setup file again ends with `SETUP OK` | `plugin` exits 2 and names `workshop.conf`; `check_tools --ready` exits 1 with a FAIL row `workshop.conf`; the setup file ends with `SETUP INCOMPLETE`. With the real value (step 3) it ends with `SETUP OK` (C1) | A codespace that opens with the placeholder gives every participant `SETUP INCOMPLETE`: step 3 was skipped |
| C36 | Gmsh runs headless: `env -u DISPLAY gmsh --help > /dev/null; echo $?`, then a batch mesh with no display: `env -u DISPLAY gmsh "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam.geo" -3 -format inp -o /tmp/headless.inp; echo $?` | both exit 0, without a window or a display error | Read the error: exercises 02 and 04 and the Gmsh server cannot work until Gmsh runs headless |
| C37 | The Codespaces user secret, with a second GitHub account that does not own the repository and a test key: **Settings** > **Codespaces** > **New secret**, name `ANTHROPIC_API_KEY`; select this repository under **Repository access**; restart the codespace; `[ -n "$ANTHROPIC_API_KEY" ] && echo set` | the account can select the repository, and the secret is set in the new codespace after a restart | The repository cannot be selected: the participant needs a fork of the repository (and creates the codespace from the fork), or uses the `read -rs` route of the README; update the README |
| C38 | 02 by hand: "C5, C32 and C38: the Gmsh meshes by hand". Time `ccx -i beam_selfweight` on 4 cores (the 4-core codespace), on the L = 1000 mesh `beam_mesh.inp`, and note its memory (`top` while it runs) | the `TIP` nodes have x = 1000 and the `FIXED` nodes x = 0 (this confirms the order of `out[]` after `Extrude` in `beam.geo`); `-setnumber L 500` gives a 500 mm beam (meshed into `beam_mesh_500.inp`, never over `beam_mesh.inp`, which the deck includes); the mean U_y over `TIP` is about -1.375 mm (2 %), read from the `02 beam L=1000` rows of the table in "Verify the decks" (C4) or from `beam_selfweight.dat` in the `02-beam-L1000` folder of the `--keep` folder; note the time and the memory: the study of 02 runs the deck at four lengths | `TIP` and `FIXED` swapped: correct the `Physical` lines of `beam.geo` (and the tests that pin it); a long time or a lot of memory: use a larger `LC` in the exercise |
| C39 | A manual outage drill, in a fresh codespace: make the manual's site unreachable (for example `echo '127.0.0.1 www.dhondt.de' \| sudo tee -a /etc/hosts`, and remove that line afterwards), run `python3 -m workshop.manual html`, then get your copy into the codespace the way you will hand it out ("C18 and C39: the manual from your own copy") and run `python3 -m workshop.manual html --archive <file>`. Also give it the PDF instead of the archive | the download ends with `error:` and exit 1 and leaves nothing under `~/calculix-manual`; `--archive` prints `Using your copy …`, exits 0 and prints the folder to give MCP-Anything; the PDF given as the HTML archive ends with `error:` (size) and exit 1, and extracts nothing | The hand-out route does not work from a participant's side (a link that needs a login, a file that cannot be dropped into the codespace): choose another, and write the exact command for the day on the hand-out. The option itself fails: the tests of `workshop/manual.py` (`tests/test_manual.py`) say what is checked |
| C40 | The Troubleshooting row for an existing codespace, followed literally in a codespace that was created before a change of `workshop.conf` (create it from a branch, then commit a corrected `workshop.conf` or a new tag to that branch): `git pull`; `python3 -m workshop.plugin install`; if that says the plugin was installed already, `claude plugin marketplace remove mcp-anything` and `python3 -m workshop.plugin install` again; then `python3 -m workshop.check_tools --ready` | `git pull` brings the new `workshop.conf`; the plugin comes from the new ref (C29 (b) says how to see that); `check_tools --ready` exits 0. Note anything a participant would not guess (a prompt, a restart of Claude Code) and add it to the row | The row is wrong or incomplete: correct it, and `not_updated_note()` in `workshop/plugin.py` with it. If it cannot be made to work, say in the welcome that codespaces are created only after the last change to `workshop.conf` (step 4) |
| C41 | Time exercises 02 and 03 in the C7 dry run, as a participant does them, against their slots in the Timeline (C30 times 01): 02 with both parts and the study, 03 with the knowledge build and the questions. Note the minutes of each | 02 fits its 45 minutes and 03 its 25 | Too long: shorten the exercise (for example the study of 02 at two lengths, or 03 as a demo) or move time from 04, and change the Timeline table together with the tests that pin it (`test_instructor_timeline_adds_up`) |
| C42 | Count Claude Code's own permission prompts during `/mcp-anything` in the C7 dry run, with the permission hook that `post-create.sh` installs (`python3 -m workshop.permissions`: it copies `extras/allow_mcp_anything_scripts.py` from the installed plugin to `~/.claude/hooks/` and adds one `Bash` entry to `hooks.PreToolUse` in `~/.claude/settings.json`). First check that it is there: `grep 'permission hook' ~/workshop-setup.txt` and `grep -c allow_mcp_anything_scripts ~/.claude/settings.json`. The hook approves a Bash call only when it has the form `uv run --no-project --python ">=3.11" python "<plugin root>/scripts/<x>.py" …`, with no shell metacharacters and a script inside the installed plugin. Then count the prompts, and note which repeat. Without the hook each such `uv run … scripts/*.py` Bash call of the plugin may ask, besides the plugin's own consent questions. The local dry run of 2026-10-27 counted the shell commands a participant's Claude runs, not the prompts: about 70 for exercise 01, and about 65 (part A) plus about 25 (part B) for exercise 02, so a run without the hook may raise about 70 to 90 prompts | The log line is `permission hook installed: ~/.claude/hooks/allow_mcp_anything_scripts.py, entry added to ~/.claude/settings.json` (a second run says `entry already in`), and the `grep -c` prints 1. The plugin's own `uv run … scripts/*.py` calls run with no prompt. Other commands (`ccx`, `gmsh`, any `uv run` that is not one of the plugin's scripts) still prompt, and so do the plugin's own consent questions in the chat. Note both counts: the plugin script calls that still asked (expected 0), and the other prompts, which is the number you tell participants (and which of them repeat). Record here whether the 01 README should tell participants how to answer these remaining prompts | The log says `permission hook not installed: <reason>; participants will see the normal prompts`. The reason is one of: the plugin was not found (its install failed: C3); the plugin has no `extras/allow_mcp_anything_scripts.py` (an older release: publish one that has it, steps 1-3, and check C17); `~/.claude/settings.json` is not valid JSON (it was left untouched: fix it, then run `python3 -m workshop.permissions` again, which is safe to repeat). The hook is installed but plugin calls still ask: write down the exact command line of one prompt (the hook allows only the form above, so a call of another shape asks) and report it to MCP-Anything. Many repeating prompts for other commands: add a short paragraph to the 01 README on how to answer (allow once, or allow for the session, for those calls only), and say it in the welcome. Never tell participants to turn permission prompts off: the first of MCP-Anything's rules is that nothing touches the machine without consent |

### Details

#### C4 and C31: the decks by hand

Exercise 01, in a folder of your own:

```bash
mkdir -p "$WORKSHOP_ROOT/work/check-ccx" && cd "$WORKSHOP_ROOT/work/check-ccx"
cp "$WORKSHOP_ROOT/exercises/01-cantilever/cantilever.inp" "$WORKSHOP_ROOT/exercises/01-cantilever/broken/bad_modulus.inp" .
ccx -i cantilever > cantilever.log 2>&1; echo "exit $?"
grep -n -e '\*WARNING' -e 'Card image' cantilever.log
grep -A3 'displacements (vx,vy,vz) for set TIPC' cantilever.dat
grep -A3 'total force (fx,fy,fz) for set FIX' cantilever.dat
ccx -i bad_modulus > bad_modulus.log 2>&1; echo "exit $?"
grep -n 'ERROR' bad_modulus.log
```

Expected:

- `ccx -i cantilever` exits 0, with no `*WARNING` and no "Card image cannot be interpreted".
- u_y at node 1211 (the set `TIPC`) is about -2.49 to -2.50 mm. An independent solve gave -2.4948.
- The total force of `FIX` is about (0, +21, 0) N.
- The 16 + 5 element records (each C3D20R element is written on two lines, 16 values and then 5) are read correctly. A
  misread shows as Jacobian errors or a wild u_y.
- `ccx -i bad_modulus` prints `*ERROR reading *ELASTIC` and exits non-zero (201).
- The layout of the `displacements (vx,vy,vz) for set TIPC` block and of the `total force (fx,fy,fz) for set FIX` block
  is the one `workshop/ccxdat.py` reads (C31). If a header or a row differs, correct `ccxdat` and its tests.

Exercise 02, L = 1000: the mean U_y over `TIP` is about -1.375 mm (within 2 %). Record the RF total of `FIXED`: expect
about 30.77 N, not 30.80, because the printed total includes the `FIXED` nodes' own self-weight share (hence the
reference's 1 % tolerance).

Exercise 04: the pressure is signed. `CABLE_PRESSURE = +10` is external pressure, and the inward reference displacement
at `P_OUTER` is -0.003571 mm. A wrong sign convention fails loudly here: u_r_outer would come out positive.

#### C5, C32 and C38: the Gmsh meshes by hand

```bash
mkdir -p "$WORKSHOP_ROOT/work/check-gmsh" && cd "$WORKSHOP_ROOT/work/check-gmsh"
cp "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam.geo" "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam_selfweight.inp" .
cp "$WORKSHOP_ROOT/exercises/04-cable-section/cable_quarter.geo" "$WORKSHOP_ROOT/exercises/04-cable-section/cable_pressure.inp" .
gmsh --version
gmsh beam.geo -3 -format inp -o beam_mesh.inp
grep '^\*' beam_mesh.inp | sort | uniq -c
gmsh beam.geo -3 -format inp -o beam_mesh_500.inp -setnumber L 500
gmsh cable_quarter.geo -2 -format inp -o cable_mesh_gmsh.inp
grep '^\*' cable_mesh_gmsh.inp | sort | uniq -c
```

`gmsh --version` prints 4.12.1. The beam mesh (02) holds:

- one `*ELEMENT, type=C3D10, ELSET=Volume1`;
- `*ELSET,ELSET=BEAM`, `*NSET,NSET=FIXED` and `*NSET,NSET=TIP`;
- no CPS6 and no T3D3.

The cable mesh (04) holds:

- four `*ELEMENT, type=CPS6` blocks and no T3D3;
- the ELSETs CORE, INSULATION, SHEATH, ARMOUR and CABLE;
- the NSETs P_CORE and P_OUTER (one node each), SYMX, SYMY, OUTER, plus the five surface names.

Real Gmsh writes CPS6 for the cable mesh, and `Mesh.SaveGroupsOfElements = -100` at the end of `cable_quarter.geo` keeps
T3D3 line elements out. Otherwise `plane-strain` refuses the mesh (C32). Then run the by-hand pipeline of the 04 README
(with `PYTHONPATH`) and `ccx -i cable_pressure`: it exits 0. That shows that ccx accepts:

- an NSET and an ELSET with the same name;
- the `1.` thickness line of `*SOLID SECTION`;
- `*INCLUDE` inside `*STEP`;
- Gmsh's trailing ", " on set lines.

U_x at `P_CORE` is about -9.113e-05 mm and at `P_OUTER` about -0.003571 mm, within 2 %.

For C38, time the L = 1000 run first, in `work/check-gmsh` (the deck includes `beam_mesh.inp`): run
`time ccx -i beam_selfweight` and note its time and its memory. Then check where the sets lie in both meshes (run from
the repository folder):

```bash
cd "$WORKSHOP_ROOT" && python3 -c "
from workshop.gmshinp import node_coordinates, node_sets
for name in ('beam_mesh.inp', 'beam_mesh_500.inp'):
    mesh = open('work/check-gmsh/' + name).read()
    xyz, sets = node_coordinates(mesh), node_sets(mesh)
    for group in ('FIXED', 'TIP'):
        print(name, group, sorted({xyz[node][0] for node in sets[group]}))
"
```

It prints `FIXED [0.0]` and `TIP [1000.0]` for `beam_mesh.inp`, and `FIXED [0.0]` and `TIP [500.0]` for
`beam_mesh_500.inp`: `-setnumber L 500` after the file name gives a 500 mm beam. The mean U_y over `TIP` comes from the
verify table (C4), or from `beam_selfweight.dat` in the `02-beam-L1000` folder of a `--keep` run.

#### C5, C6, C22, C23, C36 and C38: confirmed beforehand with Gmsh

These Gmsh results were checked before the workshop, with the same Gmsh package (4.12.1 from Ubuntu 24.04, the version
the Dockerfile pins). They are not a reason to skip the rows: the ccx parts of the same rows (a ccx run, the `.dat`
layout, the values of the verify table) were not run, and still need your codespace.

- C5: the element blocks and the set lists are the ones the row names.
- C36: the headless runs exit 0 (`gmsh --help` and the batch mesh, with no display).
- C22, the Gmsh part: `gmsh --help` exits 0 and lists `-3`, `-format`, `-o` and `-setnumber`, in 93 lines;
  `gmsh --version` prints 4.12.1; `-setnumber L 500` given after `-o` takes effect.
- C38, the geometry: the `FIXED` nodes lie at x = 0, and the `TIP` nodes at x = 1000 (x = 500 with
  `-setnumber L 500`). The beam mesh has 32 126 nodes and is byte-identical across runs.
- C6 and C23, up to ccx: `plane-strain` accepts Gmsh's triangle orientation and writes 4 `CPE6` blocks; `dload` finds
  48 faces on `OUTER`; `P_CORE` is node 2 at (10, 0) and `P_OUTER` node 8 at (24, 0).
- The real Gmsh file starts with a banner line of asterisks, `**`. For ccx it is a comment, and for the participant's
  schema it is one as long as `**` is declared a comment prefix (01 README, Phase 6: lines that start with `**` are
  comments).

#### C33: a slower deck

The workshop decks finish in seconds, and a detached run only shows itself on a run that outlasts the time you need to
quit Claude Code. The server of exercise 01 should accept a finer cantilever of the same shape, because it uses the
same keywords. Make one in a folder of your own, and check its size first (a finer mesh needs more memory and a bigger
file; the default is 40 x 2 x 2 divisions, 1221 nodes, and 80 x 8 x 8 gives 24705 nodes and a deck of about 1.6 MB):

```bash
mkdir -p "$WORKSHOP_ROOT/work/slow" && cd "$WORKSHOP_ROOT" && python3 -c "
from workshop.beam import Cantilever, c3d20r_mesh, cantilever_deck
beam = Cantilever(n_length=80, n_height=8, n_width=8)
mesh = c3d20r_mesh(beam)
print(len(mesh.nodes), 'nodes', len(mesh.elements), 'elements')
open('work/slow/cantilever.inp', 'w').write(cantilever_deck(beam))
"
```

Raise the divisions step by step (`n_height` and `n_width` must stay even), time `ccx -i cantilever` by hand in
`work/slow`, and watch the memory with `top`, until a run takes about a minute. Copy that deck into the server's
`inputs/` folder (the agent asks before it reads files outside the project) and start it with the core action. Once
`/mcp-anything:expand` exists, the 02 deck is the alternative: lower LC step by step until a run takes about a minute,
and watch the memory.

#### C18 and C39: the manual from your own copy

`workshop.manual` deletes its download after it has extracted it, so fetch the two files yourself, once, the evening
before. Both come from one site, which is why a copy of your own is the only fallback. Check each copy with the option
the participants will use:

```bash
mkdir -p ~/manual-copy && cd ~/manual-copy
curl -fLO https://www.dhondt.de/ccx_2.21.htm.tar.bz2
curl -fLO https://www.dhondt.de/ccx_2.21.pdf
cd "$WORKSHOP_ROOT"
python3 -m workshop.manual html --archive ~/manual-copy/ccx_2.21.htm.tar.bz2 --dest ~/manual-check
python3 -m workshop.manual pdf --archive ~/manual-copy/ccx_2.21.pdf --dest ~/manual-check
```

- Each command prints `Using your copy …` and then `Saved: …`. A copy with another size or checksum (a page that says
  the site is down, a half-finished download) ends with `error:`, exit code 1, and extracts nothing: the check and the
  extraction are the ones of a download, only the download is skipped.
- The file may lie anywhere the participant can read it. If it lands in the repository folder (dragged into the
  Explorer, say), `.gitignore` keeps `*.tar.bz2` and `*.pdf` out of git. The extracted manual still never goes into the
  repository.
- Which way you hand the file out is your decision: a shared drive, or a release asset of this repository (a public
  link then works with `curl -fL -o ~/ccx_2.21.htm.tar.bz2 <link>`). Try the way you chose in a codespace (C39).

#### C13: the prebuild decision

Without a Codespaces prebuild, every participant's codespace builds the whole image at the same moment. That means the
Ubuntu archive, NodeSource and about 290 MB of Claude Code from npm are all fetched by everyone at once. With a
prebuild, the image is built once, ahead of time, and a codespace opens from it.

| | Without a prebuild | With a prebuild |
|---|---|---|
| Time until `SETUP OK` | the whole image build, for every participant (C25 times it for one) | the image is ready; only `post-create.sh` runs |
| Load on the sources | all participants hit the Ubuntu archive, NodeSource and npm together | once, ahead of time |
| Cost to you | none | the repository owner pays the prebuild's storage and Actions minutes |
| Upkeep | none | rebuild after a change to `.devcontainer/`, and check that the prebuild covers `main`, the branch participants choose |

`post-create.sh` (the plugin install and the uv warm-up) runs for each participant either way. This is your decision; the
repository does not make it for you. C25 gives the time for one codespace; if it is well under 20 minutes, create three
or four codespaces at the same moment to see whether the sources slow down.

## ccx -v exits 201

`ccx -v` prints `This is Version 2.21` and then exits with code 201, not 0.

- **The cause.** ccx prints the version line and calls `stop` (`ccx_2.21.c`, line 127); `stop.f` ends with
  `call exit(201)`. ccx also ends an input error with 201 (as with `bad_modulus.inp`), so 201 does not mean "failed"
  by itself: the exit code alone cannot tell a version line from a rejected deck.
- **Why it matters.** MCP-Anything's version gate used to raise `BACKEND_FAILED` on any non-zero exit
  (`templates/common/version.py`, `runner.py`). That would stop every participant at METHOD Phase 6.
- **How MCP-Anything handles it.** The gate gains `version_exit_codes: Sequence[int] = (0,)` on
  `VersionGate`, `CliBackend` and `SolverBackend`. The agent sets it in the generated server's `get_backend()` from the
  Phase 2 evidence: a `help_output` run with `-v` that printed `This is Version 2.21` and exited 201 gives
  `version_exit_codes=(0, 201)`. METHOD Phase 6 documents it (C17).
- **What participants should see.** In Phase 2, `help_output` with `-v` records exit 201 with the version line (that is
  evidence, not a failed probe). In Phase 6, `version_exit_codes=(0, 201)` is set from exactly that, and `server_status`
  shows `version` `2.21` and `version_error` `None`. There is no wrapper: they use the real `/usr/bin/ccx` from the
  `calculix-ccx` package.
- **Elsewhere in this repository.** In `python3 -m workshop.check_tools` the `ccx` row is OK when `ccx -v` prints the
  version line and exits 201 (or 0), and FAIL when no `This is Version` line is printed. `scripts/verify_decks.sh`
  checks `ccx -v` the same way.
- **If it goes wrong:** C16, C17 and the Troubleshooting row. If the MCP-Anything in use has no `version_exit_codes`
  support, do not work around it in the workshop (no wrapper script, no changed `PATH`): publish a release that has it
  first (steps 1-3).

## Authentication

- **First choice: the participant's own subscription.** They run `claude` and log in through the browser (Pro, Max,
  Team, Enterprise or a Console account). The free claude.ai plan does not include Claude Code access.
- **The API-key fallback.** In a dedicated Console workspace with a spend limit, create one key per participant and
  hand it out on paper or in a private message. The participant stores it as their own Codespaces secret
  `ANTHROPIC_API_KEY` (README, "Log in"). Archiving the workspace afterwards archives its keys.
- **Usage limits.** A Pro plan may hit its usage limit during a long build. C30 measures it. Keep the API-key fallback
  ready.
- **Cerebras.** The conclusion is: "not supported as a drop-in". Anthropic doesn't support routing Claude Code to
  non-Claude models through any gateway (code.claude.com/docs/en/llm-gateway). LiteLLM documents a proxy for
  non-Anthropic models, but shows no Cerebras setup and was not tested. Do not offer it to participants. If you try it
  before the workshop, it is at your own risk.

## Troubleshooting

| Symptom | What to do |
|---|---|
| The browser shows a code after login, and the terminal waits | Copy the code and paste it at `Paste code here if prompted` (README, "Log in") |
| `claude` does not start, or behaves oddly | Run `claude doctor` and read what it reports. `claude --version` should be 2.1.308 and `echo "$DISABLE_AUTOUPDATER"` should print 1 (C1) |
| The manual download fails (`python3 -m workshop.manual html` ends with `error:`) | Retry once. If it fails again, or the size or checksum does not match, the site or the network is the problem: hand out your copy and have the participant run `python3 -m workshop.manual html --archive <file>` (C18, C39). The copy is checked against the same pinned size and SHA-256 as a download. As a last resort, in Phase 1 of exercise 01 name the 01 README's keyword table (`exercises/01-cantilever/README.md`, "The keywords in the deck") as the documentation |
| An existing codespace has to move to a corrected `workshop.conf` or a new plugin tag | Three steps, in this order: (1) `git pull` in the workshop repository (`cd "$WORKSHOP_ROOT"`); (2) `python3 -m workshop.plugin install`, which prints which ref `workshop.conf` names; (3) if an older tag was already added (the install says the plugin was installed already, or the plugin is still the old one), run `claude plugin marketplace remove mcp-anything` first, then `python3 -m workshop.plugin install` again. Step 2 alone is not enough: `install` only checks that the plugin is installed, and an installed plugin is not updated (it says so). This sequence is not verified: C29 (b) and C40 confirm it in a real codespace |
| The plugin is missing: `claude plugin list` has no `mcp-anything@mcp-anything` | `python3 -m workshop.plugin install` prints why. The placeholder is still in `workshop.conf` (exit 2, step 3, C35); the repository is private, so the clone fails (step 2); the tag does not exist (C29). Then `python3 -m workshop.plugin print` and type the two lines (C3) |
| `~/workshop-setup.txt` ends with `SETUP INCOMPLETE` | Read the WARN and FAIL rows above it. A plugin row: the previous row. A tool row: C1, C28. `SETUP OK (uv cache not pre-filled: …)` is not a failure (C1). A `permission hook not installed` line is not one either (next row) |
| `~/workshop-setup.txt` has `permission hook not installed: …`, or the plugin's script calls still prompt | The line names the reason (C42): the plugin was not found, the plugin release has no `extras/allow_mcp_anything_scripts.py`, or `~/.claude/settings.json` is not valid JSON and was left untouched. The hook is optional, so the setup still ends with `SETUP OK` and participants see the normal prompts. Fix the cause, run `python3 -m workshop.permissions` (safe to repeat; it also upgrades an entry that lacks the `\|\| true` of the next row), and restart `claude` so that it reads its settings again |
| The permission hook has to be turned off | Open `~/.claude/settings.json` and delete the object in `hooks.PreToolUse` whose `command` is `python3 "$HOME/.claude/hooks/allow_mcp_anything_scripts.py" \|\| true` (the whole `{"matcher": "Bash", …}` block), then restart `claude`. Removing the entry is what turns the hook off. A missing or broken script is harmless: the `\|\| true` ends the command with exit code 0 and no decision, so Claude Code asks as usual and blocks nothing (without it, `python3` exits with code 2 for a missing script, which Claude Code treats as a block of the call). Running `post-create.sh` again installs the hook again |
| ccx prints `*ERROR` lines and exits 201 | 201 is also how ccx ends an input error (and `-v`). Read the `*ERROR` line in the log: it names the card, as with `*ERROR reading *ELASTIC`. `solver_accepted` must look at the log as well as the exit code (exercise 01) |
| The server reports `ccx exited with code 201` or `UNKNOWN_VERSION` | `version_exit_codes=(0, 201)` is not set in `get_backend()`, or the MCP-Anything in use predates its `version_exit_codes` support (C16, C17). Ask the agent to set it from the Phase 2 `help_output -v` evidence; otherwise update MCP-Anything |
| MCP-Anything refuses a folder that is not empty | It builds only in an empty folder. Use a new folder under `work/` (README, "Where you work"); the folder of a failed attempt is the participant's own to delete |
| Plane stress instead of plane strain (`CPS6` in the deck), or `nonpositive jacobian` | `CPS6` is plane stress: ccx solves it without an error and gives a wrong result. `python3 -m workshop.gmshinp plane-strain` renames it to `CPE6`. `nonpositive jacobian` after that means clockwise triangles (next row) |
| All triangles clockwise (C6 fails) | `plane-strain` lists them and writes nothing. Reverse the curve loops in the `.geo` |
| Gmsh writes extra `CPS6`/`T3D3` blocks (C5 fails) | Check `Mesh.SaveGroupsOfElements` and `Mesh.SaveGroupsOfNodes` at the end of the `.geo` (C32) |
| apt reports "unmet dependencies" for a pinned version | `apt-cache policy calculix-ccx gmsh libgmsh4.12`, then update the Dockerfile ARGs and `check_tools.EXPECTED` together and run the tests (C28) |
| The golden check reports missing value names | The result tool uses other names than `reference.json` (`tip_displacement_y`, `support_reaction_y`, `u_r_core_edge`, `u_r_outer`). Ask the agent to use exactly those names: the check fails loudly by design |
| `ANTHROPIC_API_KEY` is set but unwanted | `unset ANTHROPIC_API_KEY` in the terminal and start `claude` again. If it returns in every new terminal it is a Codespaces secret: delete the secret and restart the codespace. Or turn the key off with the `/config` toggle (C9) |
| Disk space runs out | `df -h /`, then `du -sh "$(uv cache dir)" "$WORKSHOP_ROOT"/work/*`. Delete the finished folders under `work/`; `uv cache clean` only as a last resort, it removes the pre-filled cache |

## After the workshop

When the workshop is over: archive the Console workspace (that archives its keys), delete the codespaces, remove the
secrets.

- **Console:** archive the workspace you made in step 7.
- **Codespaces:** delete your own, and ask participants to delete theirs (README, "What you need").
- **Secrets:** remove the Codespaces secret `ANTHROPIC_API_KEY` from your account and ask participants to remove theirs.
- **Repository:** if you keep it, the dry-run server of C7 can become a `solutions/` folder later. Nothing in this
  repository holds a finished server.
