# Build an MCP server for CalculiX with MCP-Anything

In this workshop you give Claude safe, checked access to a finite-element solver. You run MCP-Anything, a plugin for
Claude Code, and answer its questions about the software. It writes, tests and registers a small MCP server for
CalculiX, and later one for the mesher Gmsh. You do not write the server code yourself: you know the software, and the
plugin knows how to build the server.

Everything runs in a GitHub codespace that already has CalculiX, Gmsh, Claude Code and the plugin installed. Nothing is
installed on your own computer.

## What you need

- **A GitHub account** that can create codespaces. A codespace uses your personal Codespaces quota: a 4-core machine
  uses 4 core hours of it per hour, and GitHub Free includes 120 core hours a month (GitHub's Codespaces billing page has
  the current numbers). Stop the codespace during long breaks, and delete it after the workshop.
- **A Claude account with Claude Code access:** Claude Pro, Max, Team or Enterprise, or a Console (API) account.
  The free claude.ai plan does not include Claude Code access (Claude Code's setup documentation).
  - No such account? Tell the instructor before the workshop. They can give you a personal API key for the day, with a
    spending limit (see [Log in](#log-in)).
- A web browser.

## Start

1. On this repository's GitHub page, click **Code**, open the **Codespaces** tab, then click **...** and
   **New with options...**.
2. Choose the branch `main` and a **4-core** machine type (4-core with 16 GB is recommended), then
   **Create codespace**.
3. The first start builds the container and then runs a setup script. This takes a few minutes.
4. The creation log ends with `SETUP OK`. To see the log, open the Command Palette (Ctrl+Shift+P, or Cmd+Shift+P on a
   Mac) and run **Codespaces: View Creation Log**.
   - It does not end with `SETUP OK`? Open a terminal and run `cat ~/workshop-setup.txt`: it says what is missing.
     Then see [If something is missing](#if-something-is-missing).
5. Open a new terminal (**Terminal** > **New Terminal**) and check that `echo "$WORKSHOP_ROOT"` prints the repository
   folder. The setup script sets this variable for new terminals; a terminal opened before setup finished does not have
   it.

The setup script also installs a small Claude Code hook (`~/.claude/hooks/allow_mcp_anything_scripts.py`) that lets the
plugin's own script calls run without a permission prompt each time; every other command still asks, and the plugin
still asks its own questions in the chat. To remove it, delete the entry that names `allow_mcp_anything_scripts.py` from
`hooks.PreToolUse` in `~/.claude/settings.json`.

## Log in

Claude Code needs your Claude account once per codespace.

1. In a terminal, run `claude`.
2. Choose how to log in (your Claude subscription, or a Console account) and open the link it shows. Log in in the
   browser.
3. In a codespace the browser may show a code instead of returning to the terminal. Copy the code and paste it into the
   terminal at `Paste code here if prompted`.
4. Answer the remaining first-start questions. Then continue with exercise 00, or type `/exit`.

**No subscription? Use the instructor's API key.** The instructor hands out one key per participant.

- **Best:** store it as your own Codespaces secret. On github.com, click your profile picture, then **Settings** >
  **Codespaces** > **New secret** (under "Codespaces secrets"). Name: `ANTHROPIC_API_KEY`. Value: the key. Repository
  access: this workshop repository. Then restart the codespace: GitHub hands a new secret to a codespace only when it is
  created or restarted.
- **In a hurry:** in one terminal, run

  ```
  read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY
  ```

  paste the key (nothing is shown) and press Enter. The key then holds in this terminal only: start `claude` from it.
- Either way, Claude Code asks once whether to use the key: at its "Detected a custom API key" question, choose Yes.
- Never paste the key into the chat with Claude, into a file or into a commit.
- **Back to your subscription:** run `unset ANTHROPIC_API_KEY` in the terminal, then start `claude` again (and log in
  with `/login` if you never did). A Codespaces secret comes back in every new terminal: unset it there too, or delete
  the secret and restart the codespace.

## If something is missing

Run these in a terminal, from the repository folder (`cd "$WORKSHOP_ROOT"`):

1. **Check the tools:** `python3 -m workshop.check_tools`. It prints one row per tool: OK, WARN (another version, or
   the plugin not installed) or FAIL (missing, or not answering). The `ccx` row says that ccx exits with code 201 after
   printing its version: that is normal, and exercise 01 explains it.
2. **Install the plugin again:** `python3 -m workshop.plugin install`. It runs the two documented `claude plugin`
   commands with the plugin repository named in `workshop.conf`, then checks that the plugin is installed.
3. **The manual step**, if that does not work either: `python3 -m workshop.plugin print` shows the two lines to type in
   Claude Code. They are

   ```
   /plugin marketplace add <the repository in workshop.conf>
   /plugin install mcp-anything@mcp-anything
   ```

   Start `claude`, type the first line exactly as printed, then the second. When Claude Code asks where to install it,
   choose "Install for you (user scope)", so that the plugin works in every folder. Then restart Claude Code (`/exit`,
   then `claude`).
4. **The permission hook**, if you installed the plugin yourself after logging in (step 2 or 3): run
   `python3 -m workshop.permissions` once to install the hook described under [Start](#start), then restart Claude Code.

If `python3 -m workshop.plugin` asks you to set `MCP_ANYTHING_REPO` in `workshop.conf`, the repository is not prepared
yet: tell the instructor. If `WORKSHOP_ROOT` is not set, open a new terminal.

## Exercises

| # | Exercise | What you do |
|---|---|---|
| 00 | [Setup](exercises/00-setup/README.md) | check the tools, log in, check the plugin, download the manual |
| 01 | [Cantilever beam](exercises/01-cantilever/README.md) | build a CalculiX server with `/mcp-anything` and check it against beam theory |
| 02 | [Gmsh beam](exercises/02-gmsh-beam/README.md) | build a second server for Gmsh, grow the CalculiX server, run a parametric study |
| 03 | [Documentation](exercises/03-documentation/README.md) | let the CalculiX server answer from the manual |
| 04 | [Cable cross-section](exercises/04-cable-section/README.md) | open-ended: a simplified cable section under external pressure |

Part of exercise 02 needs `/mcp-anything:expand`, and exercise 03 needs `/mcp-anything:knowledge`. Type `/` in Claude
Code to see which commands your plugin has. The exercise says what to do when one is missing.

## Where you work

Each server gets its own empty folder under `work/`:

```
mkdir -p "$WORKSHOP_ROOT/work/<name>" && cd "$WORKSHOP_ROOT/work/<name>" && claude
```

- MCP-Anything builds only in an empty folder.
- `work/` is never committed (`.gitignore` keeps it out), but you see it in the editor's file tree.
- The exercise folders hold the materials. MCP-Anything asks before it reads them, and copies what it needs into the
  server's own `inputs/` folder.
- Do not commit what you build, the manual or an API key.

## Software and licences

- **CalculiX** (`ccx` 2.21, GPL-2) and **Gmsh** (4.12.1, GPL) are installed from Ubuntu packages when the container is
  built, and are not stored here.
- **The CalculiX manual** comes with CalculiX (GPL). It is downloaded only by `python3 -m workshop.manual`, into
  `~/calculix-manual/2.21/`, outside this repository.
- **Claude Code** is installed from npm, in a pinned version, when the container is built. Using it needs your own
  Claude account or an API key.
- **MCP-Anything** is installed into Claude Code from its own repository, the one named in `workshop.conf`.
- **This repository** is Apache-2.0 ([LICENSE](LICENSE)). Its decks and geometry files are our own, written from the
  manual's keyword descriptions and cited by section.
