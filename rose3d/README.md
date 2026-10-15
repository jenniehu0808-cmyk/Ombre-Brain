# rose3d — procedural, printable replica of the spiral rose

A parametric rebuild of the reference rose (cream outer petals, six black
"camera-iris" crescent petals, hexagonal centre bud, stem and leaf) as
watertight meshes for FDM printing.

## Files

| file | what it is |
|---|---|
| `out/rose_head.stl` | flower head, one solid body, 60 mm across, with a 5.5 mm socket underneath for the stem |
| `out/rose_head_cream.stl` + `out/rose_head_black.stl` | the same head split by colour for a multi-material print (AMS / MMU). Load both into one object. |
| `out/rose_head_2colour.3mf` | the two bodies above already grouped as one object with colours |
| `out/rose_stem_leaf.stl` | stem (120 mm) with leaf and a peg that plugs into the head socket |
| `out/rose_full.stl` | head + stem + leaf fused as one piece (for display or resin printing) |
| `out/rose_all_parts.3mf` | every body in one file |
| `out/rose_viewer.html` | interactive 3D viewer (open in a browser) |
| `out/*.png`, `out/compare.png` | preview renders and the comparison sheet against the reference |
| `out/print_report.txt` | watertightness, wall thickness and overhang report |

## Rebuilding / changing the design

```bash
pip install trimesh manifold3d scipy pillow      # once
python3 rose.py --render                           # full-resolution build + previews into out/
python3 rose.py --R 40                             # bigger rose (80 mm head); everything scales
python3 rose.py --params my.json                   # override any LAYERS / STEM / RECEPTACLE value
./build_all.sh                                     # everything: STLs, 3MF, previews, report, viewer
```

`rose.py` holds the flower head as parameters (`LAYERS`, `RECEPTACLE`, `COLORS`);
`stemleaf.py` builds the stem, peg and veined leaf. Each petal is a surface in cylindrical coordinates (a Bezier
centreline in the radius/height plane, an angular width profile, cupping,
imbricate spiral offset, rolled-back rim, ripples) thickened into a solid by
`roselib.thick_surface`. All petals are boolean-unioned (manifold3d) into the
receptacle so the head is one body. `render.js` renders previews with
three.js in headless Chromium; `compare.py` builds the contact sheet.

## Printing

* **Head**: print face-up (as exported). 0.12–0.16 mm layers, 3 walls, 15 %
  infill, tree supports (the flared outer petals and the undersides of the
  inner whorls overhang). Petals are 1.2–1.4 mm thick: slow outer walls
  (≤40 mm/s) and part cooling at 100 %.
* **Two colours**: import `rose_head_cream.stl` and `rose_head_black.stl` as
  parts of one object (Bambu Studio: *Import → load as single object with
  multiple parts*; PrusaSlicer: *Add part*), or open `rose_head_2colour.3mf`.
  The black whorl is embedded in the cream body, so no manual painting is needed.
* **Stem + leaf**: print lying flat with the leaf facing up; the peg fits the
  socket under the head with ~0.2 mm clearance (glue if loose).
* **Scale**: the model is in millimetres. Scaling the head below ~45 mm makes
  the petals thinner than a 0.4 mm nozzle likes; rebuild with `--R` instead,
  which keeps petal thickness constant.
