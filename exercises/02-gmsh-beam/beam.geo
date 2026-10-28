// Workshop exercise 02: a parametric cantilever for CalculiX (our own geometry). Units: mm.
// Mesh and export:  gmsh beam.geo -3 -format inp -o beam_mesh.inp
// Other values:     add for example  -setnumber L 500   (also H, B, LC)
DefineConstant[ L = {1000, Name "Parameters/Length L [mm]"} ];
DefineConstant[ H = {20, Name "Parameters/Height H [mm]"} ];
DefineConstant[ B = {20, Name "Parameters/Width B [mm]"} ];
DefineConstant[ LC = {5, Name "Parameters/Element size LC [mm]"} ];
Point(1) = {0, 0, 0, LC};
Point(2) = {0, H, 0, LC};
Point(3) = {0, H, B, LC};
Point(4) = {0, 0, B, LC};
Line(1) = {1, 2};
Line(2) = {2, 3};
Line(3) = {3, 4};
Line(4) = {4, 1};
Curve Loop(1) = {1, 2, 3, 4};
Plane Surface(1) = {1};
out[] = Extrude {L, 0, 0} { Surface{1}; };
Physical Volume("BEAM") = {out[1]};
Physical Surface("FIXED") = {1};
Physical Surface("TIP") = {out[0]};
Mesh.ElementOrder = 2;
Mesh.SaveGroupsOfElements = -1000;
Mesh.SaveGroupsOfNodes = -100;
