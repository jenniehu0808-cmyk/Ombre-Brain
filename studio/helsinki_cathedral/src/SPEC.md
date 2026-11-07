# SPEC.md — Helsinki Cathedral, BINDING specification for all builders

Source of truth for numbers: `WORK/spec.json` (read it with `load_spec()`; never hard-code different values).
This file explains the massing in words, gives the key z-levels, the key naming of spec.json, and says
exactly which module owns which surface. Metres; z = 0 at the podium top; origin = main dome axis;
+X east, +Y north; the south facade (grand stairs, the photo) faces −Y; the camera is at −Y looking +Y.

Derivation: photo fit (spec_photo.md) anchored at 62.0 m podium→cross top, then refined with
`massing_check.py` (27 photo landmarks projected through the spec camera, rms 10.5 px on the 1512×2016 photo).
`previews/massing_vs_photo.png` and `previews/massing_overlay.png` show the box massing matching the photo.
Verified (adversarial pass): all level interfaces meet, proportions checked (`meas/verify_spec.py`).

## 1. Massing in words

* **Podium**: flat granite terrace at z = 0, X ±44, Y −37.5 … +44, standing 7.04 m above Senate Square
  (`square_ground_z = −7.04`). Its south edge (y = −37.5) is the top step of the **grand stairs**: one flight,
  56 m wide (X ±28), 44 risers × 0.16 m, treads 0.37 m, foot at y = −53.78, z = −7.04; low granite side walls.
* **Core**: a rectangular block **33 × 39 m** (X ±16.5, Y ±19.5), full height. Below z 16.5 it is wrapped by the
  four arms; its exposed corners (|x| ∈ [11,16.5] × |y| ∈ [11,19.5]) are the **corner blocks** (same entablature
  and parapet as the arms, parapet top 16.5). From 16.5 to 25.2 the core continues as the **attic** (clerestory),
  a PLUS-shaped footprint: its south/north faces run at |y| = 19.5 between the tower pedestals (|x| ≤ 10.1), its
  east/west faces at |x| = 16.5 for |y| ≤ 13.1; the four corner rectangles |x| ∈ [10.1,16.5] × |y| ∈ [13.1,19.5]
  are the **towers**. Attic: wall to 24.6, dentil cornice to 25.2, balustrade 25.2–26.4, one segmental
  "thermal" window per face (4.6 w, z 23.0–24.4) + two round-headed louvred windows at ±6.5, flat roof at 25.2.
* **Arms**: four, 22 m wide (±11), z 0 → cornice top 14.2 → plain parapet band to 16.5; low gable roof along
  the arm (eaves 16.3, ridge 18.3, ~10°; it shows as a dark wedge above the raking cornices, as in the photo) dying into the attic wall. South/north arms run from |y| 19.5 to the end
  wall at |y| 33.5; east/west arms from |x| 16.5 to the end wall at |x| 26.5. Walls: Corinthian pilasters
  1.0 w / 0.2 proud every ~4 m (capitals 9.7–11.5), lower window 2.2×3.6 (z 1.0–4.6), upper window 2.2×2.0
  (z 6.6–8.6), relief panel 2.4×1.1 (z 9.9–11.0) between the capitals. Entablature 11.5–14.2
  (architrave 0.75, frieze 0.65, dentil cornice 1.3, projection 0.9) runs continuously around arms and core.
* **Porticos**: hexastyle Corinthian, one per arm, 3.0 m in front of the arm end wall. South/north column
  line |y| = 36.5, east/west |x| = 29.5. Column axes at offsets −10.1, −6.2, −2.3, +2.3, +6.2, +10.1 (centre
  bay 4.6, others 3.9). Column: plinth 1.8 sq, base to 0.75, shaft 0.75→9.7 (r 0.675→0.575), capital
  9.7→11.5 (abacus 1.7), total 11.5 m. Entablature 11.5–14.2 (2.7 m = 23.5 % of the column), half-width 12.0, front face 0.9 in front
  of the column line, 3 m returns on both flanks to the antae (1.3 w pilasters on the end-wall corners); the
  flank between the end column and the anta is open. Pediment: base 14.2, apex 18.4 (height 4.2 = 1:5.7 of the 24 m width, rake 19.3°),
  raking cornice 0.7 h (it stops against the corner pedestals at |x| 10.75), tympanum set back 0.5, plain.
  Acroteria pedestals: apex 17.9→18.8 (1.2 sq, 0.4 m shows above the apex), corners at
  ±11.3 on the cornice 14.2→15.3 (1.1 sq). The south portico's columns stand directly on the podium
  (no stylobate); the back wall carries the door (1.65×4.5, frame 2.75, hood 4.6–5.1), responding pilasters
  and relief panels.
* **Drum (tholobate)**: on the attic roof: pedestal cylinder R 8.3 z 25.2→30.6 (hidden behind the balustrade);
  base ring R 8.7 z 30.6→33.0 with cornice; foot R 7.7→7.1 z 33.0→34.0; shaft WALL R 7.1 z 34.0→42.2 with
  **12 engaged Corinthian columns** (r 0.55, axis R 7.05 → outer face R 7.6 = the silhouette in the photo; shaft 34.0→40.8,
  capital 40.8→42.2; azimuth 15°+30°k, bays centred on N/S/E/W), a tall
  window 2.2×3.3 (z 34.3) in every bay, a small window 1.1×1.2 (z 38.2) in every bay except the south one
  which carries the **clock** (Ø 1.9, centre z 38.9, black face); entablature (architrave+frieze) R 7.75 42.2→43.8,
  dentil cornice R 7.75→8.35 43.8→45.8, white attic ring R 7.3 45.8→47.5.
* **Dome**: copper, 16 ribs, R 7.15, rise 7.0, z 47.5→54.5; fluted lantern 54.5→57.2; gold orb r 0.72 at 58.4;
  gold cross 59.1→62.0 (w 1.2).
* **Towers** (4): centres (±13.3, ±16.3). Pedestal 6.4 sq z 16.5→18.3 (two tiny windows per face), balustrade
  18.3→19.4 around the shaft, shaft 5.6 sq 18.3→24.7 with corner pilasters and a round-headed louvred window
  (2.4 w, 19.7→23.8) per face, entablature 24.7→26.0 (6.0 sq), small pediment per face 26.0→27.4, plain
  upper block 5.4 sq 27.4→29.6, cornice (6.0 sq) 29.6→30.0, star-studded copper dome R 2.8 rise 3.1 → 33.1
  (~30 gold 8-point stars, 0.3 m), gold orb r 0.35 at 34.0, gold cross to 36.1.
* **Statues**: 12 zinc apostles, 3.1 m, on the acroteria pedestals: apex (z 18.8) + two corners (z 15.3) of
  each pediment; they face outward (S ones face south toward the camera).
* **Light/camera**: sun azimuth 264° (clockwise from north: due west is 270°), elevation 6.5°, exposure −3.6,
  dust 1.2 — west faces glow gold, south faces are grazed (pale) or sky-lit grey, shadows run east.
  Camera at (−22, −114, −5.5) looking at (−3.4, −23.4, 33.0), lens 44 mm (36 mm sensor on the long,
  vertical side), portrait 3:4, 1536×2048 final / 480×640 previews.

## 2. Plan (not to scale; numbers = metres)

```
                         N (+Y)
      x=-29.5(W col line)    x=-16.5  -11   0   11  16.5      x=+29.5 (E col line)
                                 |      |    :    |     |
  y=+36.5  N column line . . . . . . [N PORTICO 6 cols, ±12] . . . .
  y=+33.5  N arm end wall        +------+----+----+------+
                                 |NW cb |  N ARM  | NE cb|   cb = corner block (core corner)
  y=+19.5  core north face  +----+------+   ±11   +------+----+
                            | W  | tower|         | tower|  E |
  y=+11    arm north flank  | ARM|(-13.3,+16.3)   |(13.3,16.3)|ARM|
                            |    +------+         +------+    |
  y=0  ----W PORTICO-----   |    |      CORE 33 x 39      |   |  ----E PORTICO----
      (6 cols at x=-29.5)   |    |   drum R 7.1/7.6 at (0,0)|   |  (6 cols at x=+29.5)
                            |    +------+         +------+    |
  y=-11    arm south flank  |    | tower|         | tower|    |
                            +----+(-13.3,-16.3)   |(13.3,-16.3)+----+
  y=-19.5  core south face       |SW cb |  S ARM  | SE cb|
  y=-33.5  S arm end wall        +------+   ±11   +------+
                                        |   door  |
  y=-36.5  S column line  . . . . . [S PORTICO 6 cols, entablature ±12] . . . .
  y=-37.5  podium south edge = top step (0.1 m in front of the plinths)  ==============  (stairs X ±28)
  y=-53.8  foot of the stairs, Senate Square z=-7.04 ... camera at (-22,-114,-5.5)
                         S (-Y)
  arm end walls: S/N |y|=33.5, E/W |x|=26.5; corner blocks |x| in [11,16.5] x |y| in [11,19.5]
```

## 3. Section through the south axis (z-levels)

```
  z 62.0  cross top            (gold cross 59.1-62.0, orb centre 58.4 r 0.72)
  z 57.2  lantern top          (lantern 54.5-57.2)
  z 54.5  dome top             (copper dome R 7.15, rise 7.0, base 47.5)
  z 47.5  drum top = dome base (white attic ring 45.8-47.5, R 7.3)
  z 45.8  drum cornice top     (cornice 43.8-45.8, R 7.75->8.35; entablature 42.2-43.8 R 7.75)
  z 42.2  drum column tops     (shaft 34.0-40.8 + capital to 42.2; wall R 7.1, column faces R 7.6; clock z 38.9 on the S face)
  z 34.0  drum shaft bottom    (foot 33-34 R 7.7->7.1; base ring 30.6-33 R 8.7; pedestal 25.2-30.6 R 8.3)
  z 36.1  tower cross top      (tower dome 30.0-33.1, orb 34.0, upper block 27.4-29.9, pediments 26.0-27.4)
  z 26.4  attic balustrade top (balustrade 25.2-26.4)
  z 25.2  attic cornice top = flat roof = drum z_base   (attic wall 16.5-24.6, cornice 24.6-25.2)
  z 18.8  apex statue feet     (apex pedestal 17.9-18.8; pediment apex 18.4; arm roof ridge 18.3)
  z 16.5  parapet top = corner-block top = tower z_base (tower pedestal 16.5-18.3, balustrade 18.3-19.4)
  z 15.3  corner statue feet   (corner pedestals 14.2-15.3)
  z 14.2  main cornice top     (entablature 11.5-14.2 everywhere: architrave 0.75, frieze 0.65, cornice 1.3)
  z 11.5  column abacus top = entablature bottom (capital 9.7-11.5)
  z  9.7  shaft top / pilaster capital bottom
  z  0.75 column base top      (plinth 1.8 sq, base 0.75)
  z  0.0  podium top (columns stand on it), top step of the stairs at y=-37.5
  z -7.04 Senate Square (44 x 0.16 m risers), camera eye at -5.5
```

## 4. spec.json key naming (top level)

`meta` (total_height_to_cross_top 62.0, key_z_levels, notes) · `sun` (ONLY setup_sun_sky kwargs:
azimuth_deg, elevation_deg, exposure, dust, ozone, air) · `camera` (location, target, lens, shift_y,
resolution [1536,2048], preview_resolution [480,640]) · `podium` (half_w, half_d, south_y, north_y, height,
plinth) · `square_ground_z` · `stairs` (width/half_w, top_y, step_rise, step_run, n_steps, bottom_y,
bottom_z, landings [], side_walls) · `core` (half_w 16.5, half_d 19.5, cornice_top_z, parapet_top_z,
attic{half_w, half_d, arm_half_w 10.1, arm_half_d 13.1, z_base, wall_top_z, cornice_top_z, top_z, balustrade,
thermal_window, side_windows}) · `arms` (common{half_w, entablature, parapet, roof, pilasters, windows_*,
relief_panels} + south/north/east/west{end_wall_*, length_from_core_face, x_range, y_range}) ·
`corner_blocks` (footprints[4], cornice_top_z, top_z 16.5, roof, facade) · `portico` (instances[4]{name,
column_line, wall, facing_deg}, columns 6, column_offsets, column_h, base_h, plinth_w, shaft_z, r_bottom,
r_top, capital_h, abacus_w, stylobate{height 0}, entablature{...half_w 12, projection 0.9, returns},
pediment{base_z, apex_z, half_w, rake_deg, raking_cornice_h, tympanum_setback}, anta, acroteria_pedestals
{apex, corners}, back_wall) · `drum` (z_base 25.2, top_z 47.5, pedestal, base_ring, foot, radius 7.1 (wall),
shaft_z, columns{count 12, azimuth_offset_deg 15, r_axis, radius}, entablature, cornice, attic_ring, windows,
clock{face S, z, diameter}) · `dome` (z_base 47.5, radius, rise, top_z, ribs, lantern, orb{r,z}, cross{z_base,
h, w, thickness, top_z}) · `towers` (positions[4], names [SE,SW,NE,NW], half_w 2.8, z_base 16.5, pedestal,
balustrade, shaft, shaft_h, arch_window, entablature, pediments, upper_block, cornice, dome{z_base, r, rise,
top_z}, orb, cross, gold_stars) · `statues` (12 × {name, pos [x,y,z], facing_deg = yaw_deg, height 3.1, on})
· `statues_notes` · `materials` (linear RGB + roughness/metallic for white_paint, wall, copper_green,
roof_dark, gold, granite, zinc, glass, wood_door, ground) · `ownership`.

Consistency guarantees (checked): towers.z_base == corner_blocks.top_z == arms.common.parapet.z_top == 16.5;
statues[i].pos.z == acroteria pedestal z_top (18.8 apex / 15.3 corners); drum.z_base == core.attic.top_z == 25.2;
dome.z_base == drum.top_z == 47.5; dome.cross.top_z == meta.total_height_to_cross_top == 62.0;
tower pedestal outer faces == core faces (|x| 16.5, |y| 19.5); stairs.top_y == podium.south_y == −37.5;
camera z − square_ground_z == 1.54 m eye height.

Statue orientation: `facing_deg` is the compass direction the figure faces (0 = +Y north, 90 = +X east,
180 = −Y south toward the camera, 270 = −X west). For a figure modelled facing +Y: rotation_euler.z = radians(−facing_deg).

## 5. Ownership — who builds which surface (no overlaps, no gaps)

| module | owns |
|---|---|
| **mod_body** | podium slab (z −7.04→0) and its visible granite walls (not the stairs); core 0→16.5 incl. the four corner blocks; attic (plus-shape 16.5→25.2: walls, pilasters, windows, cornice, balustrade, flat roof); arms (walls, pilasters, windows, relief panels, the continuous entablature 11.5–14.2 around arms + corner blocks — but NOT the portico entablature within |offset| ≤ 12 in front of the end walls), parapet bands 14.2–16.5, arm gable roofs, corner-block flat roofs; the portico back walls = arm end walls incl. doors, hoods, responding pilasters and relief panels. |
| **mod_portico** | per portico (S, N, E, W from `portico.instances`): 6 columns (plinth, base, shaft, capital), the entablature from the column line back to the end wall incl. the two 3 m returns at |offset| = 12, the pediment (raking cornices + tympanum + apex block), the two antae, the three acroteria pedestals. No stylobate, no steps. |
| **mod_domes** | everything in `drum` from z 25.2 up (pedestal, base ring, foot, shaft, 12 columns, windows, clock, entablature, cornice, attic ring), the main dome with ribs, lantern, orb and cross; the four towers from z_base 16.5 up (pedestal, balustrade, shaft, arch windows, entablature, pediments, upper block, cornice, star dome, orb, cross). |
| **mod_statues_site** | the 12 apostles (feet at `statues[i].pos`, on the portico pedestals), the grand stairs (44 steps from y −37.5 / z 0 down to y −53.78 / z −7.04, X ±28) with side walls, the Senate Square ground plane at z −7.04 (≥ 400 m square, material `ground`). |
| **mod_look** | materials (apply `spec.materials` to MATERIAL_SPECS before building), world/sun (`setup_sun_sky(**spec['sun'])`), camera (`setup_camera(location, target, lens, shift_y)`), render settings (resolution, samples). |

Interfaces: the tower pedestal (domes) sits on the corner-block top at 16.5 (body); the drum pedestal (domes)
stands on the attic roof at 25.2 (body); portico entablature returns (portico) meet the arm entablature
(body) at the end-wall corners; statues (statues_site) stand on pedestal tops (portico); the top step
(statues_site) meets the podium edge at y −37.5 (body).

## 6. Photo notes for builders

* Visible in the photo: S portico with 3 statues, W pediment's south-corner statue at the left frame edge,
  E portico's two southern columns end-on + E apex and E south-corner statues at the right edge, both front
  towers with their lit west faces, the attic balustrade between the towers, the drum with the clock, the
  dome and ~30 stair risers. Sky above the cross ≈ the top third of the frame.
* The square, stairs and the portico east of x ≈ +2 are in the shadow of buildings west of the square in the
  photo; the model does not reproduce that (optional for mod_look).
* Palette: white trim vs slightly greyer-tan wall fields (two-tone is clearly visible), dark olive copper,
  gold stars/orbs/crosses, grey granite stairs.
