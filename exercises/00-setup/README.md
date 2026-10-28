# Exercise 00: Setup

The goal: a codespace in which every tool answers, you are logged in to Claude Code, the MCP-Anything plugin is
installed, and the CalculiX manual is downloaded. Start with the [README](../../README.md) ("Start") if you have no
codespace yet.

## Steps

1. **Check the tools.** In a terminal:

   ```
   cd "$WORKSHOP_ROOT"
   python3 -m workshop.check_tools
   ```

   Every row should say OK. The `ccx` row shows `2.21 (exit 201)` and a note: ccx ends its version output with exit
   code 201, and that is normal (exercise 01 comes back to it). A WARN for the plugin is fixed in step 3. For a FAIL,
   see [If something is missing](../../README.md#if-something-is-missing).

2. **Log in.** Run `claude` and follow [Log in](../../README.md#log-in) in the README.

3. **Check the plugin.** Either way works:
   - in Claude Code, type `/plugin` and open the **Installed** tab: `mcp-anything` is listed;
   - in a terminal, run `claude plugin list`: it lists `mcp-anything@mcp-anything`.

   Not there? Run `python3 -m workshop.plugin install` from the repository folder, or follow the manual step in
   [If something is missing](../../README.md#if-something-is-missing).

4. **Download the manual.** In a terminal:

   ```
   cd "$WORKSHOP_ROOT"
   python3 -m workshop.manual html
   ```

   It downloads the CalculiX 2.21 manual from www.dhondt.de, checks its size and SHA-256 checksum, and unpacks the HTML
   pages into `~/calculix-manual/2.21/html`. At the end it prints the folder to give MCP-Anything.

   You need it in exercise 01: every rule of the input schema that MCP-Anything drafts there cites a section of the
   manual, and the agent reads the pages it cites (after asking you). In exercise 03 the server learns to answer from
   the manual. If you also want the PDF, run `python3 -m workshop.manual pdf`.

   If the download fails, tell the instructor.

   The manual comes with CalculiX (GPL). It is for your own use in the codespace: never commit it.

## Done when

In Claude Code, typing `/` lists `/mcp-anything` (it may appear as `/mcp-anything:mcp-anything`).

Do not start it yet: in exercise 01 you start it in a new, empty folder.
