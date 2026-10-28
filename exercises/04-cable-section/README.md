# Exercise 04: a simplified cable cross-section (open-ended)

> **TEACHING SIMPLIFICATION.** This is not a cable model. It is a round section of four bonded, homogeneous,
> linear-elastic layers in plane strain, under a uniform external pressure, chosen so that an exact solution exists to
> compare with. Every value in this exercise is illustrative and marked "instructor to verify". Do not use the numbers
> for design.

There is no fixed path through this exercise. Use your two servers, or grow them, to mesh, run and check the section,
and compare the result with the analytic solution below.

Both servers are registered with "Only this folder" (exercise 01, Phase 8), so Claude Code sees each one only in its
own folder: work in each server's folder in turn and hand files over with `cp`, or choose "Every folder" in Phase 8
when you register a server.

## The model

A quarter of the round section, with symmetry on the x and y axes. Plane strain: no strain along the cable's axis.

| Layer | Radii (mm) | E (MPa) | ν | Similar to | Status |
|---|---|---|---|---|---|
| `CORE` | 0 to 10 | 110000 | 0.34 | copper | instructor to verify |
| `INSULATION` | 10 to 18 | 1000 | 0.45 | a polymer | instructor to verify |
| `SHEATH` | 18 to 20 | 70000 | 0.33 | aluminium | instructor to verify |
| `ARMOUR` | 20 to 24 | 210000 | 0.30 | steel | instructor to verify |

**The load:** a uniform external pressure of 10 MPa. It is illustrative: about 1000 m of water (instructor to
verify).

## The materials

| File | What it holds |
|---|---|
| `cable_quarter.geo` | Gmsh geometry of the quarter: the layers as the surfaces `CORE`, `INSULATION`, `SHEATH` and `ARMOUR` (`CABLE` is all four), the edge `SYMX` on the y axis, the edge `SYMY` on the x axis, the outer arc `OUTER`, and the points `P_CORE` (r = 10) and `P_OUTER` (r = 24) on the x axis. Second-order triangles. |
| `cable_pressure.inp` | The CalculiX deck: the four materials, `SYMX` held in x and `SYMY` held in y, the pressure from an included file, and the displacements `U` of `P_CORE` and `P_OUTER`. |
| `reference.json` | The analytic radial displacements `u_r_core_edge` (r = 10) and `u_r_outer` (r = 24), with a 2 % tolerance. |

## The pipeline

1. **Gmsh** meshes the quarter: `gmsh cable_quarter.geo -2 -format inp -o cable_mesh_gmsh.inp`.
2. **Rename `CPS6` to `CPE6`.** Gmsh 4.12.1 writes its 6-node triangles as plane-stress `CPS6` (`src/geo/MTriangle.h`),
   and CalculiX would silently solve plane stress: a wrong answer, not an error. The plane-strain element is `CPE6`
   (manual §6.2.25):

   ```
   python3 -m workshop.gmshinp plane-strain cable_mesh_gmsh.inp cable_mesh.inp
   ```

   What `plane-strain` does:
   - It rewrites `type=CPS6` to `type=CPE6` in every `*ELEMENT` line and leaves the rest of the file as it was.
   - It refuses any element type other than `CPS6`, an element whose node count does not fit its type, and a mesh with
     no elements.
   - It then checks that the corner nodes 1-2-3 of every triangle run counter-clockwise in the x-y plane. If any
     triangle does not, it lists them (up to 10) and writes nothing.
3. **The pressure faces.** `*DLOAD` loads one face of an element; a triangle's faces are `P1`, `P2` and `P3`
   (manual §7.43). This writes a `*DLOAD` block with 10 MPa on the outer arc:

   ```
   python3 -m workshop.gmshinp dload cable_mesh.inp OUTER 10 cable_pressure_load.inc
   ```

   What `dload` does:
   - It writes one line `element, P<face>, pressure` for each face of a `CPS6` or `CPE6` element whose three nodes
     (two corners and the mid-node) are all in the node set `OUTER`. Face 1 is the edge from node 1 to node 2, face 2
     from 2 to 3, and face 3 from 3 to 1.
   - A positive pressure presses onto the face.
   - It refuses an unknown node set, a set that touches no face, and a mesh that holds another plane element type,
     whose faces it would miss.

4. **CalculiX** runs the deck: `ccx -i cable_pressure`.

Steps 2 and 3 are tools of this repository. You can run them by hand, or build them as tools into your Gmsh server
(open-ended task 1). By hand, in a folder of your own:

```
mkdir -p "$WORKSHOP_ROOT/work/cable-by-hand" && cd "$WORKSHOP_ROOT/work/cable-by-hand"
cp "$WORKSHOP_ROOT/exercises/04-cable-section/cable_quarter.geo" "$WORKSHOP_ROOT/exercises/04-cable-section/cable_pressure.inp" .
export PYTHONPATH="$WORKSHOP_ROOT"
gmsh cable_quarter.geo -2 -format inp -o cable_mesh_gmsh.inp
python3 -m workshop.gmshinp plane-strain cable_mesh_gmsh.inp cable_mesh.inp
python3 -m workshop.gmshinp dload cable_mesh.inp OUTER 10 cable_pressure_load.inc
ccx -i cable_pressure
```

`export PYTHONPATH="$WORKSHOP_ROOT"` lets `python3 -m workshop...` run from this folder.

**Reading the result.** On the x axis the radial displacement is the x-component of `U`. ccx expands each `CPE6`
element into a 3-D element and may print more than one node for `P_CORE` or `P_OUTER`: take the row whose node number
is in that set in `cable_mesh.inp`.

## The analytic solution

A multi-layer Lamé solution in plane strain, with bonded layers (`workshop/layers.py`). Negative displacements point
inwards.

| Value | Where | Analytic | Status |
|---|---|---|---|
| u_r(10), `u_r_core_edge` | the edge of the core, node `P_CORE` | -9.113e-05 mm | instructor to verify |
| u_r(24), `u_r_outer` | the outside, node `P_OUTER` | -0.003571 mm | instructor to verify |

The pressures between the layers (the radial stress, as a pressure):

| Interface | r (mm) | Pressure (MPa) | Status |
|---|---|---|---|
| core and insulation | 10 | 2.338 | instructor to verify |
| insulation and sheath | 18 | 2.195 | instructor to verify |
| sheath and armour | 20 | 3.704 | instructor to verify |
| outside (the load) | 24 | 10 | instructor to verify |

Only about a quarter of the outside pressure reaches the core: the stiff armour carries most of it as hoop stress.

## What the model leaves out

- **Stranding:** a real conductor is made of twisted wires, not a solid core.
- **Helical armour wires:** real armour is a layer of wires laid in a helix, not a solid tube, so it carries load
  along the wires and couples tension, torsion and pressure.
- **Slip:** real layers are not bonded; they slide against each other and can open gaps.
- **Polymer creep:** insulation and sheath creep and relax over time, and their stiffness depends on temperature.
- **Axial effects:** plane strain allows no strain along the cable, so tension, bending and end effects are missing.

## Open-ended tasks

1. Build steps 2 and 3 of the pipeline into the Gmsh server as tools, with `/mcp-anything:expand`. What must each of
   them refuse?
2. Grow the CalculiX server for this deck: `CPE6` elements (§6.2.25), `*SOLID SECTION` with a thickness line
   (§7.118), `*DLOAD` with `P1` to `P3` (§7.43) and two `*INCLUDE`s (§7.75). Every new rule means a new review card
   and a new `schema_reviewed`.
3. Run the deck through the server and compare `u_r_core_edge` and `u_r_outer` with `reference.json`.
4. Refine the mesh (`-setnumber LC 0.4`). Does the result move?
5. Change a layer's modulus or the pressure, and compute the new reference:

   ```
   cd "$WORKSHOP_ROOT" && python3 -c "from workshop.layers import CABLE_LAYERS, solve_plane_strain; s = solve_plane_strain(CABLE_LAYERS, 10.0); print(s.radial_displacement(10.0), s.radial_displacement(24.0))"
   ```

6. What would a real cable model need, of the list above? Which parts of it would you trust a server to set up for
   you, and which checks would it need?
