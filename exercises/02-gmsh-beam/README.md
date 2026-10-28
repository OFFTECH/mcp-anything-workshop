# Exercise 02: a Gmsh-meshed beam, and a second server

You mesh a parametric beam with Gmsh and let CalculiX bend it under its own weight. Gmsh gets a server of its own
(part A). The CalculiX server from exercise 01 learns the keywords of the new deck and gets tools that read it (part B). Then you compare a small
parametric study with beam theory.

**Before you start:** exercise 01 is done: the server in `work/beam-ccx` passes `/mcp-anything:check`. Part B needs
MCP-Anything with `/mcp-anything:expand`.

## The materials

| File | What it holds |
|---|---|
| `beam.geo` | Gmsh geometry of a cantilever with the parameters `L` = 1000, `H` = 20, `B` = 20 and the element size `LC` = 5 (all in mm). Second-order tetrahedra, which Gmsh writes as `C3D10`. Physical groups: `BEAM` (the volume), `FIXED` (the face at x = 0) and `TIP` (the face at x = L). |
| `beam_selfweight.inp` | The CalculiX deck. It includes the mesh `beam_mesh.inp`, makes `BEAM` steel with a density, holds `FIXED`, loads the beam with its own weight, and prints the displacements of `TIP` and the total reaction of `FIXED`. |
| `reference.json` | Beam theory for L = 1000: `tip_displacement_y` = -1.375 mm and `support_reaction_y` = 30.80 N. |

## The Gmsh commands

```
gmsh beam.geo -3 -format inp -o beam_mesh.inp
gmsh beam.geo -3 -format inp -o beam_mesh_500.inp -setnumber L 500
```

- `-3`: mesh the volume.
- `-format inp`: write the INP format that CalculiX reads.
- `-o beam_mesh.inp`: the output file. `beam_selfweight.inp` includes exactly this name. The mesh of the other length
  gets another name, `beam_mesh_500.inp`, so that it never overwrites the first; "The study" below copies it under
  the name the deck includes.
- `-setnumber L 500`: give the parameter `L` another value. `H`, `B` and `LC` work the same way.

Two lines at the end of `beam.geo` choose what Gmsh writes into the INP file. Their meaning comes from Gmsh's source
(`src/geo/GModelIO_INP.cpp`, tag `gmsh_4_12_1`): each digit of the negative number stands for one dimension, counted
from the right (points, curves, surfaces, volumes).

- `Mesh.SaveGroupsOfElements = -1000;` writes only the volume elements, plus the ELSETs of physical volumes (`BEAM`).
- `Mesh.SaveGroupsOfNodes = -100;` writes NSETs for physical surfaces only (`FIXED` and `TIP`).

Two more things in the file are not in your `.geo`:

- The element block is `*ELEMENT, type=C3D10, ELSET=Volume1`, so the elements are also in an element set `Volume1`,
  named after the volume, next to `BEAM` (the same elements).
- The line under `*Heading` is the absolute path of the output file. It differs from folder to folder, so no check
  should compare it.

## MCP-Anything's rules: one program, one server

Gmsh is a second program, so it gets a second server, never a tool in the CalculiX server. MCP-Anything builds one
server per program and route; an area of work that needs another program becomes a second server, made with
`/mcp-anything` in a new empty folder. The two servers do not call each other: you hand the mesh over as a file.

## Part A: the Gmsh server

```
mkdir -p "$WORKSHOP_ROOT/work/gmsh-mesher" && cd "$WORKSHOP_ROOT/work/gmsh-mesher" && claude
```

Type `/mcp-anything`, and answer:

| Phase | What to answer |
|---|---|
| 1: the software | Gmsh 4.12.1, from the Ubuntu package `gmsh`. If you do not know its path, say "please look": the agent proposes a `which` check. |
| 1: a typical task | "mesh a .geo file into a CalculiX .inp mesh with `gmsh <file>.geo -3 -format inp -o <mesh>.inp`, optionally with other parameter values (`-setnumber L 500`)" |
| 1: run time | "A mesh takes seconds, and nothing must keep running after I close Claude Code." |
| 1: materials | the exercise folder, with `beam.geo` (`echo "$WORKSHOP_ROOT/exercises/02-gmsh-beam"` prints its path) |
| 1: what must never happen | Your choice, for example: "Never change the files in the exercise folder, and never report a mesh as good when Gmsh failed." |
| 2: the checks | Approve `sniff_files` on the exercise folder (it only reads). Approve `help_output` with `--help`: Gmsh prints its usage text and exits 0, which is the ✔ Command line evidence the `cli` route needs, showing `-3`, `-format`, `-o` and `-setnumber`. Also approve it with `--version` (`4.12.1`, exit 0): the evidence for the version check. `--version` alone is no evidence for a command line (MCP-Anything's METHOD, Phase 2; `cli.md`, "When it applies"). |
| 3: the route | A mesh takes seconds, so Phase 3 recommends `cli`. Confirm it. |
| 4: documentation | "No documentation for now." |
| 5: the tools | For example `mesh_geometry`: it takes a `.geo` file from `inputs/` and values for `L`, `H`, `B` and `LC`, and writes the mesh into `outputs/`. It is the core action: turn it on. A tool that passes free-form options to Gmsh is never part of it. |
| 5: the input files | It asks: "Can your program's input files run commands or open other files?" Answer: "Yes: a .geo file can (`SystemCall`, `OnelabRun`, `Merge`, `Include`, `Save`, `Printf` to a file, `CreateDir`). Refuse them." `beam.geo` uses none of these (its `Mesh.SaveGroups...` lines are options, not the `Save` command), so the refusal does not touch it. |
| Before 6: may it run Gmsh? | "Yes, you may run it." |
| 6: the build | The executable from Phase 2, the version from `--version` (exit 0). `beam.geo` has to be in the server's `inputs/`, the only place the mesh tool reads geometry from: the agent asks before it copies it there from the exercise folder. Answer yes. |
| 7: the golden check | Mesh `beam.geo` and check what matters: only `C3D10` elements, the element sets `BEAM` and `Volume1`, the NSETs `FIXED` and `TIP`, and the node and element counts that you confirm when you first see them. Leave the heading out of the check: it holds a path. |
| 8: register | "Only this folder". The server cannot be used yet: restart Claude Code in this folder (`/exit`, then `claude`) and approve the new server when asked. `/mcp` shows whether it is connected. |

Then ask the new server for the mesh of `beam.geo` as `beam_mesh.inp`. (For the study at the end, you will also ask for
L = 500 as `beam_mesh_500.inp`. The Gmsh server works only in its own folder, so ask for that mesh now, while you are
here, or come back to `work/gmsh-mesher` later: "The study" says how.)

## Part B: the CalculiX server grows

> Part B needs MCP-Anything with `/mcp-anything:expand`. Type `/` in Claude Code: if it is not listed, run the study by
> hand (below) and ask the instructor.

**1. The hand-off, first.** The agent drafts the new rules from the deck and the mesh it includes, so both must be in
place before you start. Copy `beam_mesh.inp` (the end of part A) from the Gmsh server's `outputs/` to the CalculiX
server's `inputs/`, next to `beam_selfweight.inp`, for example in `inputs/golden/selfweight/`:

```
mkdir -p "$WORKSHOP_ROOT/work/beam-ccx/inputs/golden/selfweight"
cd "$WORKSHOP_ROOT/work/beam-ccx/inputs/golden/selfweight"
cp "$WORKSHOP_ROOT/work/gmsh-mesher/outputs/beam_mesh.inp" .
cp "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam_selfweight.inp" "$WORKSHOP_ROOT/exercises/02-gmsh-beam/reference.json" .
```

Keep them out of `inputs/examples/`: that keeps the self-weight runs out of the cross-check that runs at every check.

**2. Expand the CalculiX server.** Open Claude Code in its folder and name the area after the command:

```
cd "$WORKSHOP_ROOT/work/beam-ccx" && claude
```

```
/mcp-anything:expand self-weight runs: read the mean tip displacement over node set TIP and compare it with a reference
```

`/mcp-anything:expand` never changes the tools you already have. Exercise 01's result tool and comparison
(`read_results` and `compare_to_reference`, if yours got those names) keep reading the block of the single node set
`TIPC`, which `beam_selfweight.inp` does not print. So the area needs new tools:

- a tool that reads an ended self-weight run: `tip_displacement_y` as the mean y-displacement over node set `TIP`, and
  `support_reaction_y` as the y-component of the total force of `FIXED`, with exactly these names, as in
  `reference.json`;
- a comparison built on it, which compares those values with a reference file.

Their known-good check is the L = 1000 deck in `inputs/golden/selfweight/` against the `reference.json` next to it.
Starting runs stays with exercise 01's core action.

**3. New keywords and forms.** `beam_selfweight.inp` and the Gmsh mesh it includes use
keywords and forms your 01 schema does not have:

| Keyword | New | Where | Manual |
|---|---|---|---|
| `*INCLUDE` with `INPUT` | keyword | the deck includes `beam_mesh.inp`, an included deck | §7.75 |
| `*DENSITY` | keyword | steel, 7.85E-9 t/mm³ | §7.35 |
| `*DLOAD` with `GRAV` | keyword | the self-weight: 9810 mm/s² in -y | §7.43 |
| `*ELEMENT` with `TYPE=C3D10` | form: another element type | Gmsh's 10-node tetrahedra | §7.49; C3D10: §6.2.7 |
| `*Heading` | form: Gmsh's spelling of `*HEADING` | the first block of Gmsh's file | §7.71 |
| `*ELSET` | keyword | Gmsh's element set `BEAM` | §7.53 |
| `*NSET` | form: Gmsh's layout of the set lines | Gmsh's node sets `FIXED` and `TIP` | §7.100 |

The three rows marked "form" may already be allowed by your 01 rules; check (ask the agent to validate the deck in
`inputs/golden/selfweight/`), and add a rule only where the check refuses. Ask the agent to add cited rules for the
rest. Three hints:

- Declare `INPUT` of `*INCLUDE` as an `include` parameter. The deck check then makes sure the mesh file exists, and a
  run copies it into its run folder.
- The data line of `*DLOAD` mixes names and numbers: only its third to sixth fields are numbers.
- Gmsh writes `*Heading` in mixed case: the schema's format must stay case-insensitive, which is its default.

Every schema change shows the review card again and records a new `schema_reviewed` (METHOD Phase 6);
`/mcp-anything:check` fails until then.

## The study

For a cantilever under its own weight, beam theory gives the tip deflection

δ = q·L⁴/(8·E·I), with q = ρ·g·B·H and I = B·H³/12.

Units (manual §3): ρ = 7.85E-9 t/mm³ and g = 9810 mm/s², so q comes out in N/mm. With E = 210000 MPa and
H = B = 20 mm:

| L (mm) | δ (mm) | support reaction q·L (N) |
|---|---|---|
| 500 | 0.08595 | 15.40 |
| 750 | 0.4351 | 23.10 |
| 1000 | 1.375 | 30.80 |
| 1500 | 6.962 | 46.21 |

δ grows with L⁴: twice the length gives 16 times the deflection. The tip moves in -y, so `tip_displacement_y` is -δ.

The reaction is compared within 1 %, not exactly. CalculiX's printed total force of `FIXED` is the sum over those nodes
of the reaction plus the loads applied there (manual §7.98), and the `FIXED` nodes carry a small part of the beam's own
weight themselves. So the printed total differs from q·L, by well under 1 %.

**Reporting.** Report `tip_displacement_y` as the mean over node set `TIP`, and `support_reaction_y` as the y-component
of the total force of `FIXED`. For L = 1000, compare with `reference.json`. For another length, write a reference file
from the repository's own formulas into that length's folder, for example for L = 500:

```
mkdir -p "$WORKSHOP_ROOT/work/beam-ccx/inputs/L500"
cd "$WORKSHOP_ROOT" && python3 -c "import json; from workshop.beam import selfweight_reference; print(json.dumps(selfweight_reference(500.0), indent=2))" > "$WORKSHOP_ROOT/work/beam-ccx/inputs/L500/reference.json"
```

That folder also needs `beam_selfweight.inp` and the mesh of that length. Each length needs its own folder, because the
deck includes `beam_mesh.inp` by name, so the L = 500 mesh goes in under that name. Ask the Gmsh server for the mesh of
`beam.geo` with L = 500 as `beam_mesh_500.inp`; it lands in the server's `outputs/`. Each server is registered for its
own folder only, so this is a second session: in a second terminal run
`cd "$WORKSHOP_ROOT/work/gmsh-mesher" && claude`, ask there, and then carry on in the CalculiX server's folder
(`work/beam-ccx`). (By hand, the second Gmsh command above writes that file into the folder you run it in: copy it from
there instead.) Then copy the deck and the mesh:

```
cp "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam_selfweight.inp" "$WORKSHOP_ROOT/work/beam-ccx/inputs/L500/"
cp "$WORKSHOP_ROOT/work/gmsh-mesher/outputs/beam_mesh_500.inp" "$WORKSHOP_ROOT/work/beam-ccx/inputs/L500/beam_mesh.inp"
```

**By hand**, without the servers (for example when `/mcp-anything:expand` is missing):

```
mkdir -p "$WORKSHOP_ROOT/work/beam-by-hand" && cd "$WORKSHOP_ROOT/work/beam-by-hand"
cp "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam.geo" "$WORKSHOP_ROOT/exercises/02-gmsh-beam/beam_selfweight.inp" .
gmsh beam.geo -3 -format inp -o beam_mesh.inp
ccx -i beam_selfweight
```

The results are in `beam_selfweight.dat`.

## Done when

- The Gmsh server passes `/mcp-anything:check`.
- With part B: the CalculiX server passes `/mcp-anything:check` with the new rules (a new `schema_reviewed`) and the
  new tools, and the new comparison of the L = 1000 run in `inputs/golden/selfweight/` with its `reference.json`
  reports `matches: true`.

## Discussion

- Why does a second program get a second server, instead of one more tool?
- A `.geo` file is itself a program that can run commands, write files and read files, so confining the paths the
  server is given does not confine what the file does: why must the server refuse such commands, and what does the
  refusal cost?
- The mesh travels as a file from one server to the other. What does the CalculiX server check about it before a run?
  What would it do with a mesh of other elements?
- How does the result change with the element size (`-setnumber LC 2.5`)?
