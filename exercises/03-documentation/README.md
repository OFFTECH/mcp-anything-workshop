# Exercise 03: let the CalculiX server answer from the manual

> This exercise needs MCP-Anything with `/mcp-anything:knowledge`. Type `/` in Claude Code: if
> `/mcp-anything:knowledge` is not listed, skip this exercise.

You add the CalculiX 2.21 manual to the server from exercise 01. Afterwards Claude can search the manual and quote a
section, with its section number, instead of answering from memory.

**Before you start:** the server in `work/beam-ccx` passes `/mcp-anything:check`, and the manual is in
`~/calculix-manual/2.21/html` (exercise 00, `python3 -m workshop.manual html`).

## Steps

1. Open Claude Code in the CalculiX server's folder:

   ```
   cd "$WORKSHOP_ROOT/work/beam-ccx" && claude
   ```

2. Type `/mcp-anything:knowledge` and choose to add a source. Name the folder `~/calculix-manual/2.21/html`, as an
   absolute path (`echo ~/calculix-manual/2.21/html` prints it).
3. Approve the look at the folder (`doc_structure`) and the copy into the server's `knowledge/sources/`.
4. **The conversion trial.** If the agent runs a conversion trial (MCP-Anything sends an HTML help site there; whether
   it does is the agent's call), it converts the pages and shows you an outline and a sample. Check that the outline
   follows the manual's numbered sections and that the keyword pages keep their keyword. For these pages choose direct
   serving ("Serve it section by section").
5. The pages are UTF-8, so the default encoding works: no `--encoding` is needed.
6. The agent builds the index and runs the check. Then reconnect the server (`/mcp`), so the new sections appear,
   together with `search_docs` and `read_section` if the server did not have them yet.

The PNG figures are not copied, so the Figure 60 node order (§6.2.4) arrives as text only. When you need the picture,
look at the PDF (link below).

## Try it

Ask Claude:

> Which section of the CalculiX manual defines `*CLOAD`, and what does `OP=NEW` do?

Expected: the answer names §7.15 and quotes the section it read.

Then try a question of your own about the deck from exercise 01, for example about `*NODE PRINT` (§7.98) or
`TOTALS=ONLY`.

## Done when

Claude answers the `*CLOAD` question by citing §7.15 from the server's documentation tools.

## Licence

The manual comes with CalculiX (GPL). You downloaded it yourself, for your own use in the codespace, from

- https://www.dhondt.de/ccx_2.21.htm.tar.bz2 (the HTML pages used here)
- https://www.dhondt.de/ccx_2.21.pdf (the same manual as a PDF)

`python3 -m workshop.manual` checks both against pinned SHA-256 checksums. `work/` is never committed, and
MCP-Anything keeps `knowledge/sources/` out of git by default. Do not publish the manual with your server.
