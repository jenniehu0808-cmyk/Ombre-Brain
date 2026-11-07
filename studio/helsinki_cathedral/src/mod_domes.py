"""mod_domes.py - everything above the core attic of Helsinki Cathedral.

DRUM (tholobate, spec['drum'], z 25.2 -> 47.5): pedestal cylinder, stepped base ring with cornice, sloping foot,
shaft wall with 12 engaged Corinthian columns (lathe shaft + astragal + leafy bell + square abacus), a recessed tall
4x6-pane window in every bay, a small 2x3-pane window above it in every bay except the south one, which
carries the CLOCK (black dial, white marks/hands as in the photo), architrave/frieze ring, dentil cornice,
white attic ring.
white attic ring. The base ring and the pedestal carry 24 shallow panel strips (one under every column and bay centre).
MAIN DOME (spec['dome']): smooth copper lathe of dome_profile(R 7.15, rise 7.0), 16 standing-seam ribs
(swept strips conformed to the meridian, 10 cm proud, own lighter material 'copper_rib'), no stars, a dark fluted
CUP lantern (1.85 m body with a waist, flared 2.1 m rim, 12 flutes) with a gold cone and knob, gold orb and gold cross.
TOWERS (spec['towers'], 4 x from z 16.5): pedestal with two small windows per face, balustrade, square shaft
with L-shaped corner pilasters, a RECESSED round-headed panel per face (C-shaped wall plate over a slimmer
core, no boolean) holding a white archivolt ring, imposts, the louvred window and a sill, dentil entablature,
a pediment per face whose raking cornice is flush with the entablature cornice (tympanum set back, raking
dentils), plain upper block, cornice, small copper dome with 8 ribs and 42 gold 8-point 0.4 m
stars in 4 staggered rings (oriented along the surface normal), gold orb and gold cross.
The drum window pockets are cut with a boolean that is applied immediately (no modifier/cutter left behind).

One tower is built at the origin, joined into a handful of meshes, and the other three are linked duplicates.
"""
from common import *

PFX = 'domes'

MATERIAL_SPECS.setdefault('clock_black', {'Base Color': (0.012, 0.012, 0.015, 1), 'Roughness': 0.4})
MATERIAL_SPECS.setdefault('louvre', {'Base Color': (0.30, 0.31, 0.31, 1), 'Roughness': 0.7})

# polish r4: re-measured on ref/crop_dome_drum.jpg (44.5 px/m) and ref/crop_tower_left.jpg (70 px/m)
RIB_T, RIB_W = 0.10, 0.28          # main-dome seam ribs: 10 cm proud, 28 cm wide (were 3.5 cm / 20 cm: invisible at frame scale)
RIB_TONE, RIB_ROUGH = 1.7, 0.45    # 'copper_rib' = copper_green base x1.7, roughness 0.45
LANTERN_R = 0.925                  # cup body radius (diameter 1.85; rim 2.1, waist 1.77)
LANTERN_FLUTES = 12
STAR_SIZE = 0.40                   # spec 0.3 re-measured: ~55 px at 140 px/m in the 2x tower crop
STAR_RELIEF = 0.06                 # >= 6 cm so the stars catch the 6.5 deg sun
# (elevation deg, count, azimuth offset deg) per row: 42 stars in 4 staggered rows, none centred on a rib (ribs every 45 deg)
STAR_ROWS = ((12.0, 16, 11.25), (31.0, 12, 7.5), (50.0, 8, 22.5), (68.0, 6, 22.5))
DENTILS_PER_BAY = 11               # 132 dentils, pitch 0.374 m, 0.18 wide x 0.20 high (were 84 at 0.58, 0.22 x 0.32)
BASE_STRIPS = 24                   # panel joints of the drum base, ~1.9 m apart in the photo: under every column and bay centre


def _rib_material():
    """'copper_rib' for the main-dome seams: MATERIAL_SPECS['copper_green'] copied at CALL time (main.py copies
    spec['materials'] into MATERIAL_SPECS after this module is imported) with a lighter tone and a smoother finish.
    Specular level kept low (0.2) + warm tint so the smoother lobe does not mirror the blue sky at the limbs (see
    mod_look's copper notes). mod_look's upgrade pass only touches the names it knows, so this one keeps its colour."""
    if 'copper_rib' not in MATERIAL_SPECS:
        cg = dict(MATERIAL_SPECS['copper_green'])
        r, g, b = cg['Base Color'][:3]
        cg['Base Color'] = (r * RIB_TONE, g * RIB_TONE, b * RIB_TONE, 1.0)
        cg['Roughness'] = RIB_ROUGH
        cg['Specular IOR Level'] = 0.2
        cg['Specular Tint'] = (1.0, 0.85, 0.55, 1.0)
        MATERIAL_SPECS['copper_rib'] = cg
    return mat('copper_rib')


# ----------------------------------------------------------------------------- helpers
def _join(objects, name):
    """common.join() reads matrix_world; headless it is stale for freshly placed objects -> update first."""
    objects = [o for o in objects if o is not None]
    if not objects:
        return None
    bpy.context.view_layer.update()
    return join(objects, name)


def _mesh_ob(name, bm, material=None, collection=None, smooth_angle=None):
    if smooth_angle is not None:
        r = math.radians(smooth_angle)
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > r:
                e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (collection if collection is not None else get_collection('Cathedral')).objects.link(ob)
    if material is not None:
        me.materials.append(mat(material) if isinstance(material, str) else material)
    return ob


def _boxes_mesh(name, boxes, material=None, collection=None):
    """One mesh made of many axis boxes: boxes = [(center(x,y,z), size(sx,sy,sz), rot_z_rad), ...]."""
    bm = bmesh.new()
    for center, size, rz in boxes:
        r = bmesh.ops.create_cube(bm, size=1.0)
        vs = r['verts']
        bmesh.ops.scale(bm, vec=Vector(size), verts=vs)
        if rz:
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(rz, 3, 'Z'), verts=vs)
        bmesh.ops.translate(bm, vec=Vector(center), verts=vs)
    return _mesh_ob(name, bm, material, collection)


def _ring_boxes(n, r, size, z, az0=0.0):
    """boxes on a circle (radial size[0], tangential size[1], height size[2]), bottom at z."""
    out = []
    for k in range(n):
        az = az0 + k * 2 * math.pi / n
        out.append(((r * math.sin(az), r * math.cos(az), z + size[2] / 2), (size[1], size[0], size[2]), -az))
    return out


def _square_boxes(half, n_side, size, z):
    """boxes along the 4 sides of a square of half size `half` (face centres at +-half), n per side."""
    out = []
    for i in range(n_side):
        t = -half + (i + 0.5) * (2 * half / n_side)
        for ang in (0, 0.5 * math.pi, math.pi, 1.5 * math.pi):
            c = Matrix.Rotation(ang, 3, 'Z') @ Vector((t, -half, z + size[2] / 2))
            out.append(((c.x, c.y, c.z), (size[1], size[0], size[2]), ang))
    return out


def _orb_profile(r, zc, n=18):
    return [(r * math.sin(i / n * math.pi), zc - r * math.cos(i / n * math.pi)) for i in range(n + 1)]


def _rib(name, profile, w, t, r_min, collection, material, sink=0.02):
    """Thin seam rib following a lathe (r,z) meridian from the rim up to radius r_min (local X-Z plane)."""
    pts = [(r, z) for r, z in profile if r >= r_min]
    bm = bmesh.new()
    rings = []
    for i, (r, z) in enumerate(pts):
        r0, z0 = pts[max(i - 1, 0)]
        r1, z1 = pts[min(i + 1, len(pts) - 1)]
        tr, tz = r1 - r0, z1 - z0
        L = math.hypot(tr, tz) or 1.0
        nr, nz = tz / L, -tr / L          # outward normal
        ring = [bm.verts.new((r + nr * s, y, z + nz * s)) for s, y in ((-sink, -w / 2), (-sink, w / 2), (t, w / 2), (t, -w / 2))]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for j in range(4):
            bm.faces.new((a[j], a[(j + 1) % 4], b[(j + 1) % 4], b[j]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mesh_ob(name, bm, material, collection, smooth_angle=40)


def _plate(name, pts_xz, thick, collection, material, y_face, outward=-1):
    """Vertical plate from an (x,z) polygon in the plane y=y_face, extruded `thick` outward
    (outward=-1 -> toward -Y, the south). Object origin (0,0,0), so z-rotations turn it about the axis."""
    ob = extrude_polygon(name, pts_xz, thick, 0.0, material=material, collection=collection)
    # rotate about X: local (x, y, h) -> (x, -h, y); mirror for +Y extrusion
    ob.rotation_euler = (math.pi / 2, 0, 0) if outward < 0 else (-math.pi / 2, 0, 0)
    ob.location = (0, y_face, 0)
    return ob


def _arch_outline(half_w, z_bot, z_spring, n=14):
    pts = [(-half_w, z_bot), (half_w, z_bot)]
    for i in range(n + 1):
        a = i / n * math.pi
        pts.append((half_w * math.cos(a), z_spring + half_w * math.sin(a)))
    return pts


def _arc(half_w, z_spring, n=14, left_to_right=True):
    """points of a semicircle of radius half_w centred on (0, z_spring), from the left springer to the right one."""
    pts = [(half_w * math.cos(a), z_spring + half_w * math.sin(a)) for a in (i / n * math.pi for i in range(n + 1))]
    return pts if not left_to_right else list(reversed(pts))


def _arch_band_outline(r_out, r_in, z_bot, z_spring, n=14):
    """Closed archivolt band (round head + two jambs) as ONE simple polygon: outer outline up and over, inner back."""
    return ([(-r_out, z_bot)] + _arc(r_out, z_spring, n, True) + [(r_out, z_bot), (r_in, z_bot)]
            + _arc(r_in, z_spring, n, False) + [(-r_in, z_bot)])


def _wall_with_arch(half_w, z0, z1, r_arch, z_spring, n=14):
    """Rectangular wall outline (x,z) with a round-headed opening of radius r_arch (spring at z_spring) that is open
    at the bottom edge -> still one simple polygon (a 'C' shape), no boolean needed."""
    return ([(-half_w, z0), (-r_arch, z0)] + _arc(r_arch, z_spring, n, True) + [(r_arch, z0), (half_w, z0), (half_w, z1), (-half_w, z1)])


def _star_pts(size, points=8, inner=0.45):
    R = size / 2
    return [((R if k % 2 == 0 else R * inner) * math.cos(k * math.pi / points),
             (R if k % 2 == 0 else R * inner) * math.sin(k * math.pi / points)) for k in range(2 * points)]


def _cross(name, z_base, h, w, t, collection, material='gold'):
    bar_z = z_base + h * 0.52
    a = add_box(f'{name}_v', (t, t, h), (0, 0, z_base + h / 2), material=material, collection=collection)
    b = add_box(f'{name}_h', (w, t, t), (0, 0, bar_z), material=material, collection=collection)
    c = add_box(f'{name}_top', (t * 2.0, t * 1.6, t * 1.6), (0, 0, z_base + h - t * 0.8), material=material, collection=collection)
    return _join([a, b, c], name)


# ----------------------------------------------------------------------------- drum + main dome
def _interp_r(profile, z):
    """radius of a lathe (r,z) profile at height z (piecewise linear on the outer outline)."""
    pts = [(r, zz) for r, zz in profile if r > 0]
    if z <= pts[0][1]:
        return pts[0][0]
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return pts[-1][0]


def _drum_leaf(name, z0, h, out, w_base, r_at, collection, material='white_paint', thick=0.03, N=8, K=4):
    """One acanthus leaf hugging a bell of radius r_at(z): a thin, tapered, outward-curling closed shell, built at
    angle 0 (+X radial) around the local Z axis (same construction as the portico capitals, coarser: 8 x 4)."""
    L = 1.0
    ds = L / N
    z, r = 0.0, 0.0
    raw = []
    for i in range(N + 1):
        t = i / N
        raw.append((z, r, t))
        phi = math.radians(118.0 * (t ** 1.9))
        z += ds * math.cos(phi)
        r += ds * math.sin(phi)
    zmax = max(p[0] for p in raw)
    rmax = max(p[1] for p in raw)
    rows = [(z0 + zz * (h / zmax), r_at(z0 + zz * (h / zmax)) + 0.012 + rr * (out / rmax), t) for (zz, rr, t) in raw]
    bm = bmesh.new()
    front, back = [], []
    for (zw, rc, t) in rows:
        u = max(0.0, (t - 0.5) / 0.5)
        w = w_base * (0.80 + 0.55 * t) * ((1.0 - u) ** 0.8 * 0.93 + 0.07)
        w *= 1.0 + 0.12 * math.sin(2 * math.pi * 3.0 * t + 0.6)
        fr, bk = [], []
        for k in range(K):
            sdx = k / (K - 1) - 0.5
            ang = sdx * w / max(rc, 0.3)
            cup = 0.04 * (1 - (2 * sdx) ** 2) * (0.25 + 0.75 * (1 - t))
            rk = rc - 0.04 * (0.25 + 0.75 * (1 - t)) + cup
            fr.append(bm.verts.new((rk * math.cos(ang), rk * math.sin(ang), zw)))
            bk.append(bm.verts.new(((rk - thick) * math.cos(ang), (rk - thick) * math.sin(ang), zw)))
        front.append(fr)
        back.append(bk)
    for i in range(N):
        for k in range(K - 1):
            bm.faces.new((front[i][k], front[i][k + 1], front[i + 1][k + 1], front[i + 1][k]))
            bm.faces.new((back[i + 1][k], back[i + 1][k + 1], back[i][k + 1], back[i][k]))
        bm.faces.new((front[i][0], front[i + 1][0], back[i + 1][0], back[i][0]))
        bm.faces.new((back[i][K - 1], back[i + 1][K - 1], front[i + 1][K - 1], front[i][K - 1]))
    for k in range(K - 1):
        bm.faces.new((front[0][k + 1], front[0][k], back[0][k], back[0][k + 1]))
        bm.faces.new((front[N][k], front[N][k + 1], back[N][k + 1], back[N][k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bm.calc_volume(signed=True) < 0:          # the curled shell fools recalc_face_normals: force outward normals
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    return _mesh_ob(name, bm, material, collection)


def _drum_column(spec, col):
    """One engaged Corinthian column (base, tapered shaft, astragal, bell with two tiers of 8 acanthus leaves,
    square abacus) at the origin, z absolute. Fixer r1: the photo's drum capitals are big bushy Corinthian knobs
    ~1.45 m wide (1.3 x the 1.1 shaft) under a heavy shadowed soffit; the old lathe cap read Tuscan."""
    dc = spec['drum']['columns']
    r0, r1 = dc['radius'], dc.get('radius_top', 0.48)
    zb, zs, zt = dc['z_base'], dc['shaft_top_z'], dc['z_top']        # 34.0, 40.8, 42.2
    bh = dc['base_h']
    ab_h = 0.25
    bell_top = zt - ab_h                                              # 41.95
    r_ast, h_ast = r1 + 0.04, 0.08                                    # astragal ring r 0.52 h 0.08 at 40.8
    bell = [(r1, zs + h_ast + 0.02), (r1 + 0.01, zs + 0.40), (r1 + 0.05, zs + 0.70), (r1 + 0.12, zs + 0.95),
            (r1 + 0.19, bell_top - 0.05), (r1 + 0.22, bell_top)]     # r 0.48 -> 0.70 over 40.9 -> 41.95
    prof = [(0, zb), (r0 + 0.12, zb), (r0 + 0.12, zb + bh * 0.3), (r0 + 0.07, zb + bh * 0.55), (r0 + 0.1, zb + bh * 0.75),
            (r0, zb + bh), (r0, zb + bh + 0.1), (r0, zs - 2.0), (r1, zs - 0.12), (r_ast, zs - 0.1), (r_ast, zs),
            (r_ast, zs + h_ast), (r1, zs + h_ast)] + bell + [(0, bell_top)]
    shaft = lathe(f'{PFX}_drum_col_proto', prof, segments=28, material='white_paint', collection=col)
    r_at = lambda z: _interp_r(bell, z)
    # two tiers of 8 acanthus leaves: lower 40.9-41.5 (tip out 0.18), upper 41.3-41.9 (tip out 0.25), offset 22.5 deg
    lower = _drum_leaf(f'{PFX}_drum_leafA', zs + 0.10, 0.60, 0.20, 0.42, r_at, col, thick=0.04)
    upper = _drum_leaf(f'{PFX}_drum_leafB', zs + 0.50, 0.60, 0.27, 0.44, r_at, col, thick=0.04)
    parts = [shaft, lower, upper]
    for i in range(8):
        a = math.radians(45 * i)
        if i:
            parts.append(duplicate(lower, f'{PFX}_drum_leafA{i}', location=(0, 0, 0), rotation=(0, 0, a)))
        parts.append(duplicate(upper, f'{PFX}_drum_leafB{i}', location=(0, 0, 0), rotation=(0, 0, a + math.radians(22.5))))
    aw = 2 * r1 * 1.0 + 0.49                                          # 1.45 = 1.3 x the shaft diameter 1.1
    ab = add_box(f'{PFX}_drum_col_abacus', (aw, aw, ab_h), (0, 0, bell_top + ab_h / 2), material='white_paint', collection=col)
    parts.append(ab)
    return _join(parts, f'{PFX}_drum_col_proto')


def _tall_window(spec, col):
    """Tall 4x6-pane window group for the north bay (+Y), recessed into the wall. Origin (0,0,0)."""
    d = spec['drum']
    w = d['windows']['tall']
    R = d['radius']
    W, H, z0 = w['width'], w['height'], w['z_bottom']
    rc = R - 0.3                      # recess back face
    objs = []
    objs.append(add_box(f'{PFX}_tw_glass', (W, 0.04, H), (0, rc + 0.07, z0 + H / 2), material='glass', collection=col))
    fr = 0.15
    for nm, sz, c in (('sill', (W + 2 * fr, 0.22, fr), (0, rc + 0.11, z0 - fr / 2)),
                      ('head', (W + 2 * fr, 0.18, fr), (0, rc + 0.09, z0 + H + fr / 2)),
                      ('jl', (fr, 0.18, H), (-W / 2 - fr / 2, rc + 0.09, z0 + H / 2)),
                      ('jr', (fr, 0.18, H), (W / 2 + fr / 2, rc + 0.09, z0 + H / 2)),
                      # mouldings at the wall plane (photo: a cornice-like head and a projecting sill on every tall window);
                      # the wall pocket is W+0.3 x H+0.3, so these sit on the wall just outside the pocket
                      ('headm', (W + 0.5, 0.3, 0.26), (0, R - 0.03, z0 + H + 0.15 + 0.13)),
                      ('headm2', (W + 0.36, 0.22, 0.1), (0, R - 0.03, z0 + H + 0.15 + 0.26 + 0.05)),
                      ('sillm', (W + 0.4, 0.26, 0.14), (0, R - 0.03, z0 - 0.15 - 0.07))):
        objs.append(add_box(f'{PFX}_tw_{nm}', sz, c, material='white_paint', collection=col))
    bars = []
    nx, nz = 4, 6
    # polish r4: horizontals 2 cm behind the verticals and every bar runs 2 cm into the frame -> no coplanar faces at
    # the crossings or against the jambs / head / sill (the backs stay inside the glass slab)
    for i in range(1, nx):
        bars.append(((-W / 2 + i * W / nx, rc + 0.10, z0 + H / 2), (0.07, 0.06, H + 0.04), 0))
    for j in range(1, nz):
        bars.append(((0, rc + 0.085, z0 + j * H / nz), (W + 0.04, 0.05, 0.06), 0))
    objs.append(_boxes_mesh(f'{PFX}_tw_bars', bars, material='white_paint', collection=col))
    return _join(objs, f'{PFX}_tall_window_proto')


def _small_window(spec, col):
    d = spec['drum']
    w = d['windows']['small']
    R = d['radius']
    W, H, z0 = w['width'], w['height'], w['z_bottom']
    rc = R - 0.25
    objs = [add_box(f'{PFX}_sw_glass', (W, 0.04, H), (0, rc + 0.07, z0 + H / 2), material='glass', collection=col)]
    fr = 0.12
    for nm, sz, c in (('sill', (W + 2 * fr, 0.2, fr), (0, rc + 0.1, z0 - fr / 2)),
                      ('head', (W + 2 * fr, 0.16, fr), (0, rc + 0.08, z0 + H + fr / 2)),
                      ('jl', (fr, 0.16, H), (-W / 2 - fr / 2, rc + 0.08, z0 + H / 2)),
                      ('jr', (fr, 0.16, H), (W / 2 + fr / 2, rc + 0.08, z0 + H / 2)),
                      ('sillm', (W + 0.3, 0.22, 0.1), (0, R - 0.03, z0 - 0.12 - 0.05)),
                      ('headm', (W + 0.3, 0.22, 0.12), (0, R - 0.03, z0 + H + 0.12 + 0.06))):
        objs.append(add_box(f'{PFX}_sw_{nm}', sz, c, material='white_paint', collection=col))
    # polish r4: mullion proud of the horizontals, both run 2 cm into the frame (no coplanar faces)
    bars = [((0, rc + 0.09, z0 + H / 2), (0.06, 0.05, H + 0.04), 0)]
    for j in (1, 2):
        bars.append(((0, rc + 0.08, z0 + j * H / 3), (W + 0.04, 0.04, 0.05), 0))
    objs.append(_boxes_mesh(f'{PFX}_sw_bars', bars, material='white_paint', collection=col))
    return _join(objs, f'{PFX}_small_window_proto')


def _clock(spec, col):
    """Clock on the south face (-Y) of the drum wall: white rim, black dial, white marks and hands."""
    d = spec['drum']
    c = d['clock']
    R = d['radius']
    rr = c['diameter'] / 2
    zc = c['z']
    y0 = -R + 0.03                                 # rim starts a little inside the wall
    rim = add_cylinder(f'{PFX}_clock_rim', rr + c.get('rim_w', 0.1), 0.10, (0, 0, 0), segments=48, material='white_paint', collection=col)
    place(rim, location=(0, y0, zc), rotation=(math.pi / 2, 0, 0))       # local z -> -Y
    face = add_cylinder(f'{PFX}_clock_face', rr, 0.06, (0, 0, 0), segments=48, material='clock_black', collection=col)
    place(face, location=(0, y0 - 0.09, zc), rotation=(math.pi / 2, 0, 0))
    marks = []
    yf = y0 - 0.15 - 0.02
    for k in range(12):
        phi = k * math.pi / 6
        big = k % 3 == 0
        L = 0.2 if big else 0.13
        rm = rr - 0.16
        cx, cz = rm * math.sin(phi), rm * math.cos(phi)
        marks.append(((cx, yf, zc + cz), (0.06 if big else 0.04, 0.03, L), 0))   # rotated below by hand
    # boxes need rotation about Y: build them individually
    mk = []
    for (cx, yy, cz), sz, _ in marks:
        phi = math.atan2(cx, cz - zc)
        b = add_box(f'{PFX}_clock_mark', sz, (0, 0, 0), material='white_paint', collection=col)
        place(b, location=(cx, yy, cz), rotation=(0, phi, 0))
        mk.append(b)
    # hands (about 8:17 as in the photo)
    for nm, phi, L, w in (('hour', math.radians(249.0), rr * 0.55, 0.09), ('minute', math.radians(102.0), rr * 0.82, 0.06)):
        b = add_box(f'{PFX}_clock_{nm}', (w, 0.03, L), (0, 0, L / 2 - 0.08), material='white_paint', collection=col)
        place(b, location=(0, yf - 0.03, zc), rotation=(0, phi, 0))
        mk.append(b)
    hub = add_cylinder(f'{PFX}_clock_hub', 0.07, 0.04, (0, 0, 0), segments=16, material='white_paint', collection=col)
    place(hub, location=(0, yf - 0.03, zc), rotation=(math.pi / 2, 0, 0))
    mk.append(hub)
    return _join([rim, face] + mk, f'{PFX}_clock')


def build_drum(spec, col):
    d = spec['drum']
    objs = []
    ped, br, ft = d['pedestal'], d['base_ring'], d['foot']
    # pedestal + stepped base ring with cornice + sloping foot, one lathe
    cp = br['cornice_projection']
    ch = br['cornice_h']
    dc_ledge_r = d['columns']['r_axis'] + d['columns']['radius'] + 0.12 + 0.08   # column base plinth + 8 cm margin
    prof = [(0, ped['z_bottom']), (ped['radius'], ped['z_bottom']), (ped['radius'], ped['z_top']),
            (br['radius'], ped['z_top']), (br['radius'], br['z_top'] - ch),
            (br['radius'] + cp * 0.45, br['z_top'] - ch + 0.05), (br['radius'] + cp * 0.45, br['z_top'] - ch * 0.55),
            (br['radius'] + cp, br['z_top'] - ch * 0.4), (br['radius'] + cp, br['z_top']),
            (ft['radius_bottom'] + 0.25, br['z_top']), (ft['radius_bottom'] + 0.25, br['z_top'] + 0.3),
            (ft['radius_bottom'], br['z_top'] + 0.3), (ft['radius_bottom'], ft['z_bottom'] + 0.35),
            # sloping foot, then a continuous ledge (torus course) at the shaft bottom that carries the column
            # bases (base plinth r = axis 7.05 + 0.67 = 7.72 > wall 7.1: without it the bases would float over the slope)
            (ft['radius_top'] + 0.25, ft['z_top'] - 0.3), (dc_ledge_r, ft['z_top'] - 0.3),
            (dc_ledge_r, ft['z_top']), (ft['radius_top'] - 0.3, ft['z_top'])]
    objs.append(lathe(f'{PFX}_drum_base', prof, segments=96, material='white_paint', collection=col))
    # polish r4: the base is panelled in the photo (crop_dome_drum, bottom: flat strips ~1.9 m apart under the base-ring
    # cornice, one under every column and every bay centre). 24 shallow strips (5 cm proud, 0.4 wide) on the base ring,
    # which is the part that shows above the attic balustrade from the camera, and the same on the pedestal below it.
    z_ring0, z_ring1 = ped['z_top'] - 0.05, br['z_top'] - ch + 0.02
    strips = (_ring_boxes(BASE_STRIPS, br['radius'] + 0.01, (0.08, 0.40, z_ring1 - z_ring0), z_ring0)
              + _ring_boxes(BASE_STRIPS, ped['radius'] + 0.01, (0.08, 0.40, ped['z_top'] - ped['z_bottom'] - 0.2), ped['z_bottom'] + 0.25))
    objs.append(_boxes_mesh(f'{PFX}_drum_base_strips', strips, material='white_paint', collection=col))
    # shaft wall with recessed windows (boolean)
    R = d['radius']
    z0, z1 = d['shaft_z'][0], d['columns']['z_top']
    wall = add_cylinder(f'{PFX}_drum_wall', R, z1 - z0, (0, 0, z0), segments=96, material='white_paint', collection=col)
    objs.append(wall)
    dc = d['columns']
    n = dc['count']
    az0 = math.radians(dc['azimuth_offset_deg'])
    tw, sw = d['windows']['tall'], d['windows']['small']
    cut = []
    bays = []
    for k in range(n):
        az = k * 2 * math.pi / n           # bay centres on N/S/E/W (clockwise from +Y)
        is_south = abs(az - math.pi) < 1e-6
        bays.append((az, is_south))
        cut.append(((R * math.sin(az), R * math.cos(az), tw['z_bottom'] + tw['height'] / 2),
                    (tw['width'] + 0.3, 0.6, tw['height'] + 0.3), -az))
        if not is_south:
            cut.append(((R * math.sin(az), R * math.cos(az), sw['z_bottom'] + sw['height'] / 2),
                        (sw['width'] + 0.24, 0.5, sw['height'] + 0.24), -az))
    cutter = _boxes_mesh(f'{PFX}_drum_window_cutter', cut, collection=col)
    add_boolean(wall, cutter)
    # bake the pockets into the wall mesh (works headless, 0.05 s) so the wall survives a later join() by the
    # integrator and no hidden cutter is left in the scene; if applying ever fails, keep the modifier instead
    try:
        bpy.context.view_layer.update()
        apply_modifiers(wall)
        bpy.data.objects.remove(cutter, do_unlink=True)
    except Exception as e:
        print('[domes] boolean apply failed, keeping the modifier:', e)
        objs.append(cutter)
    # windows
    twp = _tall_window(spec, col)
    swp = _small_window(spec, col)
    objs += [twp, swp]
    for i, (az, is_south) in enumerate(bays):
        if i == 0:
            twp.rotation_euler = (0, 0, -az)
        else:
            objs.append(duplicate(twp, f'{PFX}_tall_window_{i:02d}', location=(0, 0, 0), rotation=(0, 0, -az)))
    first_small = True
    for i, (az, is_south) in enumerate(bays):
        if is_south:
            continue
        if first_small:
            swp.rotation_euler = (0, 0, -az)
            first_small = False
        else:
            objs.append(duplicate(swp, f'{PFX}_small_window_{i:02d}', location=(0, 0, 0), rotation=(0, 0, -az)))
    objs.append(_clock(spec, col))
    # 12 engaged columns
    proto = _drum_column(spec, col)
    objs.append(proto)
    ra = dc['r_axis']
    for k in range(n):
        az = az0 + k * 2 * math.pi / n
        loc = (ra * math.sin(az), ra * math.cos(az), 0)
        if k == 0:
            place(proto, location=loc, rotation=(0, 0, -az))
        else:
            objs.append(duplicate(proto, f'{PFX}_drum_col_{k:02d}', location=loc, rotation=(0, 0, -az)))
    # entablature + dentil cornice + attic ring (one lathe) and the dentil ring
    en, co, ar = d['entablature'], d['cornice'], d['attic_ring']
    re_, rc0, rc1, rar = en['radius'], co['radius_bottom'], co['radius'], ar['radius']
    prof = [(R - 0.3, en['z_bottom']), (re_ - 0.08, en['z_bottom']), (re_ - 0.08, en['z_bottom'] + 0.7), (re_, en['z_bottom'] + 0.75),
            (re_, en['z_top']),
            (rc0, co['z_bottom']), (rc0, co['z_bottom'] + 0.45),                 # dentil band backing
            (rc0 + 0.3, co['z_bottom'] + 0.45), (rc0 + 0.3, co['z_bottom'] + 0.7),
            (rc0 + 0.45, co['z_bottom'] + 0.8), (rc0 + 0.45, co['z_bottom'] + 1.45),
            (rc1, co['z_bottom'] + 1.6), (rc1, co['z_top']),
            (rar, ar['z_bottom']), (rar, ar['z_top'] - 0.25), (rar + 0.15, ar['z_top'] - 0.2), (rar + 0.15, ar['z_top']),
            (spec['dome']['radius'] - 0.2, ar['z_top'])]
    objs.append(lathe(f'{PFX}_drum_crown', prof, segments=96, material='white_paint', collection=col))
    if co.get('dentils', True):
        # polish r4: ~11 small square dentils per bay (0.18 x 0.20 at 0.374 pitch), hanging just under the band step
        nd = DENTILS_PER_BAY * n
        # (centre r +0.06 with 0.22 radial: back 7 cm inside the band, front 15 cm proud)
        objs.append(_boxes_mesh(f'{PFX}_drum_dentils', _ring_boxes(nd, rc0 + 0.06, (0.22, 0.18, 0.2), co['z_bottom'] + 0.2),
                                material='white_paint', collection=col))
    return objs


def build_dome(spec, col):
    dm = spec['dome']
    objs = []
    prof = dome_profile(dm['radius'], dm['rise'], dm['z_base'], steps=32)
    objs.append(lathe(f'{PFX}_dome', prof, segments=96, material=dm.get('material', 'copper_green'), collection=col, smooth_angle=60))
    # standing-seam ribs (polish r4): 10 cm proud, 28 cm wide, own lighter material -> they read as the photo's light
    # seams on both the lit W limb and the shaded E side
    la = dm['lantern']
    rib = _rib(f'{PFX}_dome_rib_00', prof, RIB_W, RIB_T, LANTERN_R + 0.08, col, _rib_material())
    # second (unused) slot named copper_green: mod_look light-links its copper sun to every object that carries a
    # 'copper_green' slot, and the seams must get the same lit-limb boost as the sheet they sit on
    rib.data.materials.append(mat('copper_green'))
    objs.append(rib)
    nr = dm['ribs']
    for k in range(1, nr):
        objs.append(duplicate(rib, f'{PFX}_dome_rib_{k:02d}', location=(0, 0, 0), rotation=(0, 0, k * 2 * math.pi / nr)))
    # lantern (polish r4, crop_dome_drum at 44.5 px/m): a dark FLUTED CUP, rim 2.1 m wide with a 0.3 m flat flared band,
    # body 1.85 m with a slight waist (1.77 m), ~1.7 m showing above the dome silhouette from the camera, 12 flutes;
    # above it a gold cone (0.9 m -> 0.3 m over 0.6 m), a stem and a gold knob under the orb. Orb centre and cross untouched.
    # Derived: foot r 1.145 at z0-0.2..z0+0.05 (covers the rib ends), rim top z_rim = lantern z_top - 0.4 = 56.8
    # (57.0 showed 2.1 m of cup above the silhouette against the photo's 1.6 m).
    orb = dm['orb']
    zl0 = la['z_bottom']                                  # 54.5 = dome apex
    z_rim = la['z_top'] - 0.4                             # 56.8 = top of the cup rim
    z_orb_bot = orb['z'] - orb['r']                       # 57.68
    rb = LANTERN_R
    body = [(rb + 0.045, zl0 + 0.5), (rb, zl0 + 0.9), (rb - 0.04, zl0 + 1.3), (rb - 0.01, zl0 + 1.7), (rb + 0.03, z_rim - 0.35)]
    cup = ([(0, zl0 - 0.2), (rb + 0.22, zl0 - 0.2), (rb + 0.22, zl0 + 0.05), (rb + 0.12, zl0 + 0.3)] + body
           + [(rb + 0.11, z_rim - 0.3), (rb + 0.135, z_rim - 0.27), (rb + 0.135, z_rim - 0.04), (rb + 0.09, z_rim),
              (0.47, z_rim), (0, z_rim)])
    objs.append(lathe(f'{PFX}_lantern', cup, segments=48, material=la.get('material', 'copper_green'), collection=col, smooth_angle=40))
    if la.get('fluted', True):
        # 12 convex fillets hugging the waisted body: the grooves between them read as the photo's dark flutes
        fl = _rib(f'{PFX}_lantern_flute_00', body, 0.22, 0.07, 0.0, col, la.get('material', 'copper_green'), sink=0.03)
        objs.append(fl)
        for k in range(1, LANTERN_FLUTES):
            objs.append(duplicate(fl, f'{PFX}_lantern_flute_{k:02d}', location=(0, 0, 0), rotation=(0, 0, k * 2 * math.pi / LANTERN_FLUTES)))
    cone = [(0, z_rim - 0.02), (0.45, z_rim - 0.02), (0.45, z_rim + 0.05), (0.40, z_rim + 0.10), (0.17, z_rim + 0.56),
            (0.14, z_rim + 0.6), (0.14, z_orb_bot - 0.1), (0, z_orb_bot - 0.1)]
    objs.append(lathe(f'{PFX}_lantern_cone', cone, segments=32, material=orb.get('material', 'gold'), collection=col, smooth_angle=40))
    objs.append(lathe(f'{PFX}_lantern_knob', _orb_profile(0.15, z_orb_bot - 0.07, n=12), segments=24, material=orb.get('material', 'gold'),
                      collection=col, smooth_angle=60))
    objs.append(lathe(f'{PFX}_orb', _orb_profile(orb['r'], orb['z']), segments=48, material=orb.get('material', 'gold'), collection=col, smooth_angle=60))
    cr = dm['cross']
    objs.append(_cross(f'{PFX}_cross', cr['z_base'], cr['h'], cr['w'], cr['thickness'], col, cr.get('material', 'gold')))
    # small neck between orb top and cross base
    objs.append(add_cylinder(f'{PFX}_cross_neck', 0.1, max(cr['z_base'] - (orb['z'] + orb['r']) + 0.1, 0.1), (0, 0, orb['z'] + orb['r'] - 0.1),
                             segments=12, material='gold', collection=col))
    return objs


# ----------------------------------------------------------------------------- towers
def _baluster_side(t, col):
    """One balustrade side (south side, y<0) of a tower pedestal: rails, corner posts, balusters -> one mesh."""
    bal = t['balustrade']
    hw = t['pedestal']['half_w']
    zb, zt = bal['z_bottom'], bal['top_z']
    rail_w = 0.32
    yc = -(hw - rail_w / 2)
    post = 0.42
    objs = []
    # bottom rail, top rail (full length including posts)
    objs.append(add_box('b_rail0', (2 * hw, rail_w, 0.14), (0, yc, zb + 0.07), material='white_paint', collection=col))
    objs.append(add_box('b_rail1', (2 * hw, rail_w + 0.04, 0.14), (0, yc, zt - 0.07), material='white_paint', collection=col))
    # corner posts (shared by two sides: each side carries its own half-post box; overlap is fine)
    for sx in (-1, 1):
        objs.append(add_box('b_post', (post, post, zt - zb), (sx * (hw - post / 2), yc, (zb + zt) / 2), material='white_paint', collection=col))
    # balusters
    h = (zt - 0.14) - (zb + 0.14)
    z0 = zb + 0.14
    prof = [(0, z0), (0.07, z0), (0.07, z0 + 0.06), (0.045, z0 + 0.09), (0.075, z0 + 0.22), (0.07, z0 + 0.3),
            (0.045, z0 + 0.5), (0.04, z0 + h - 0.12), (0.06, z0 + h - 0.08), (0.06, z0 + h), (0, z0 + h)]
    bproto = lathe('b_bal', prof, segments=10, collection=col, material='white_paint')
    pitch = bal['baluster_pitch']
    clear = 2 * hw - 2 * post
    nb = int(clear / pitch)
    pitch = clear / nb
    bals = [bproto]
    for i in range(nb):
        x = -hw + post + (i + 0.5) * pitch
        if i == 0:
            place(bproto, location=(x, yc, 0))
        else:
            bals.append(duplicate(bproto, 'b_bal', location=(x, yc, 0)))
    one = _join(bals, 'b_balusters')
    return _join(objs + [one], f'{PFX}_tower_balustrade_S')


def _tower_face(t, col):
    """Everything that is per-face on a tower, built for the SOUTH face (-Y) at the tower origin -> one mesh."""
    objs = []
    hw = t['shaft']['half_w']
    ped = t['pedestal']
    # pedestal small windows (2 per face)
    swd = ped['small_windows']
    for sx in (-1, 1):
        x = sx * swd['spacing'] / 2
        objs.append(add_box('f_pw_frame', (swd['size'][0] + 0.16, 0.06, swd['size'][1] + 0.16),
                            (x, -ped['half_w'] - 0.02, swd['z_bottom'] + swd['size'][1] / 2), material='white_paint', collection=col))
        objs.append(add_box('f_pw_glass', (swd['size'][0], 0.06, swd['size'][1]),
                            (x, -ped['half_w'] - 0.045, swd['z_bottom'] + swd['size'][1] / 2), material='glass', collection=col))
    # corner pilasters (2 per face) with base and capital. Each box runs past the corner by the projection so the
    # pilasters of two adjacent faces wrap the corner as one L (no notch at the arris).
    cp = t['corner_pilasters']
    pw, pp = cp['width'], cp['projection']
    zs0, zs1 = t['shaft']['z_bottom'], t['shaft']['z_top']
    for sx in (-1, 1):
        for nm, extra, h, zc in (('f_pil', 0.0, zs1 - zs0, (zs0 + zs1) / 2), ('f_pil_base', 0.06, 0.55, zs0 + 0.275),
                                 ('f_pil_cap', 0.12, 0.7, zs1 - 0.35), ('f_pil_cap2', 0.05, 0.25, zs1 - 0.85)):
            depth = pp + extra
            # +1 cm past the corner: the end face must NOT coincide with the adjacent face's pilaster front
            # (coincident faces render as black speckle at distance)
            x_in, x_out = hw - pw - extra, hw + depth + 0.01
            objs.append(add_box(nm, (x_out - x_in, depth, h), (sx * (x_in + x_out) / 2, -hw - depth / 2, zc), material='white_paint', collection=col))
    # arched window in a recessed round-headed panel (spec panel_recess): the face WALL is a 'C'-shaped plate
    # (rectangle minus the arch field, open at the bottom) over a slimmer core box, so the field is truly recessed;
    # inside it a white archivolt ring with jambs, imposts, the louvred window at the back, and a sill.
    aw = t['arch_window']
    whw = aw['width'] / 2
    band = 0.28
    rec = aw.get('panel_recess', 0.15)
    r_field = whw + band + 0.3                      # recess outline radius (concentric with the window head)
    r_field = min(r_field, hw - pw - 0.08)          # keep clear of the pilasters
    z_sill = aw['z_bottom'] - 0.15
    back_y = -(hw - rec)                            # recess back plane (= core box face)
    objs.append(_plate('f_wall', _wall_with_arch(hw, zs0, zs1, r_field, aw['spring_z']), rec, col, 'wall', back_y))
    # fill the field below the sill (the balustrade hides most of it)
    objs.append(add_box('f_field_fill', (2 * r_field + 0.02, rec + 0.02, z_sill - zs0), (0, back_y - rec / 2, (z_sill + zs0) / 2), material='wall', collection=col))
    # archivolt ring + jambs, 0.12 proud of the recess back (its face ends 3 cm inside the wall plane)
    objs.append(_plate('f_archivolt', _arch_band_outline(whw + band, whw, z_sill, aw['spring_z']), rec - 0.03, col, 'white_paint', back_y))
    # louvred window: grey plate at the back of the recess + slats + central mullion
    objs.append(_plate('f_arch_louvre', _arch_outline(whw, aw['z_bottom'], aw['spring_z']), 0.03, col, 'louvre', back_y))
    slats = []
    z = aw['z_bottom'] + 0.2
    while z < aw['z_top'] - 0.3:
        half = whw - 0.02
        if z > aw['spring_z']:
            half = math.sqrt(max(whw ** 2 - (z - aw['spring_z']) ** 2, 0.0)) - 0.02
        slats.append(((0, back_y - 0.05, z), (2 * half, 0.04, 0.05), 0))
        z += 0.25
    slats.append(((0, back_y - 0.055, (aw['z_bottom'] + aw['z_top']) / 2), (0.08, 0.05, aw['z_top'] - aw['z_bottom']), 0))
    objs.append(_boxes_mesh('f_slats', slats, material='white_paint', collection=col))
    # imposts at the springing (on the archivolt), sill across the field at the wall plane
    for sx in (-1, 1):
        objs.append(add_box('f_impost', (band + 0.2, rec + 0.08, 0.16), (sx * (whw + band / 2 + 0.05), back_y - (rec + 0.08) / 2, aw['spring_z'] - 0.08),
                            material='white_paint', collection=col))
    objs.append(add_box('f_sill', (2 * r_field + 0.1, rec + 0.1, 0.15), (0, back_y - (rec + 0.1) / 2, z_sill - 0.075), material='white_paint', collection=col))
    # pediment: raking cornice band flush with the entablature cornice face (ehw + 0.12), tympanum (wall colour)
    # set back to the frieze/pilaster plane, as in crop_tower_left/right where the pediment base IS the cornice.
    pd = t['pediments']
    ehw = t['entablature']['half_w']
    phw, zb, za, chh = pd['half_w'], pd['base_z'], pd['apex_z'], pd['cornice_h']
    pf = hw + pp                                    # pilaster / frieze face
    cornice_face = ehw + 0.12                       # outer face of the entablature cornice (see _tower_proto)
    objs.append(_plate('f_tympanum', [(-phw, zb), (phw, zb), (0, za - chh * 0.4)], pf - (ehw - 0.5), col, 'wall', -(ehw - 0.5)))
    slope = (za - zb) / phw
    dx = chh / slope
    band_pts = [(-phw - 0.12, zb), (0, za + 0.12 * slope), (phw + 0.12, zb), (phw - dx, zb), (0, za - chh), (-phw + dx, zb)]
    objs.append(_plate('f_rake', band_pts, cornice_face - (ehw - 0.5), col, 'white_paint', -(ehw - 0.5)))
    # raking dentils under the band (photo: small dentils along the raking cornice)
    dent = []
    L = math.hypot(phw - dx, za - chh - zb)
    nd = int(L / 0.36)
    for sx in (-1, 1):
        for k in range(nd):
            s = (k + 0.5) / nd
            x = sx * (phw - dx) * (1 - s)
            zz = zb + (za - chh - zb) * s
            dent.append(((x, -(cornice_face - 0.14), zz - 0.06), (0.16, 0.2, 0.14), 0))
    objs.append(_boxes_mesh('f_rake_dentils', dent, material='white_paint', collection=col))
    return _join(objs, f'{PFX}_tower_face_S')


def _tower_proto(spec, col):
    """One complete tower at the origin (z absolute). Returns the list of objects (all with origin (0,0,0))."""
    t = spec['towers']
    objs = []
    ped = t['pedestal']
    # pedestal with a thin coping
    objs.append(add_box(f'{PFX}_tower_pedestal', (2 * ped['half_w'], 2 * ped['half_w'], ped['z_top'] - ped['z_bottom']),
                        (0, 0, (ped['z_top'] + ped['z_bottom']) / 2), material='wall', collection=col))
    objs.append(mitered_frame(f'{PFX}_tower_ped_coping', [(0, -0.22), (0.06, -0.2), (0.06, 0), (-0.4, 0), (-0.4, -0.22)],
                              ped['half_w'], ped['half_w'], (0, 0, ped['z_top']), material='white_paint', collection=col))
    # balustrade (4 sides)
    bs = _baluster_side(t, col)
    objs.append(bs)
    for k, nm in ((1, 'E'), (2, 'N'), (3, 'W')):
        objs.append(duplicate(bs, f'{PFX}_tower_balustrade_{nm}', location=(0, 0, 0), rotation=(0, 0, k * math.pi / 2)))
    # shaft core: the faces (with the recessed arch panels) are 'rec' thick plates built in _tower_face, so the core
    # box stops at the recess back plane (+5 mm overlap to avoid coplanar faces)
    sh = t['shaft']
    hw = sh['half_w']
    rec = t['arch_window'].get('panel_recess', 0.15)
    core_hw = hw - rec + 0.005
    objs.append(add_box(f'{PFX}_tower_shaft', (2 * core_hw, 2 * core_hw, sh['z_top'] - sh['z_bottom']), (0, 0, (sh['z_top'] + sh['z_bottom']) / 2),
                        material='wall', collection=col))
    # faces (4)
    fc = _tower_face(t, col)
    objs.append(fc)
    for k, nm in ((1, 'E'), (2, 'N'), (3, 'W')):
        objs.append(duplicate(fc, f'{PFX}_tower_face_{nm}', location=(0, 0, 0), rotation=(0, 0, k * math.pi / 2)))
    # entablature: architrave + frieze block, dentils, cornice
    en = t['entablature']
    ehw = en['half_w']
    pf = hw + t['corner_pilasters']['projection']           # pilaster face
    ze0, ze1 = en['z_bottom'], en['z_top']
    objs.append(add_box(f'{PFX}_tower_architrave', (2 * pf, 2 * pf, 0.62), (0, 0, ze0 + 0.31), material='white_paint', collection=col))
    objs.append(mitered_frame(f'{PFX}_tower_arch_fillet', [(0, 0), (0.05, 0), (0.05, 0.08), (0, 0.08)], pf, pf, (0, 0, ze0 + 0.55),
                              material='white_paint', collection=col))
    if en.get('dentils', True):
        objs.append(_boxes_mesh(f'{PFX}_tower_dentils', _square_boxes(pf - 0.02, 16, (0.14, 0.18, 0.26), ze0 + 0.66), material='white_paint', collection=col))
    cz = ze0 + 0.95
    cprof = [(0, -0.33), (0.06, -0.33), (0.06, -0.2), (ehw - pf + 0.02, -0.1), (ehw - pf + 0.12, 0.0), (ehw - pf + 0.12, ze1 - cz), (-0.3, ze1 - cz), (-0.3, -0.33)]
    objs.append(mitered_frame(f'{PFX}_tower_cornice', cprof, pf, pf, (0, 0, cz), material='white_paint', collection=col))
    # upper block (carried down to the pediment base so the corners behind the pediments are solid white) + cornice.
    # Fixer r3: plain block, no mid-height string course (crop_tower_left/right show a plain band under the cornice).
    pd = t['pediments']
    ub = t['upper_block']
    objs.append(add_box(f'{PFX}_tower_upper', (2 * ub['half_w'], 2 * ub['half_w'], ub['z_top'] - pd['base_z']),
                        (0, 0, (ub['z_top'] + pd['base_z']) / 2), material='white_paint', collection=col))
    co = t['cornice']
    chw = co['half_w']
    cz = co['z_bottom']
    cprof = [(0, 0), (0.08, 0), (0.08, 0.12), (chw - ub['half_w'] - 0.04, 0.2), (chw - ub['half_w'], 0.3), (chw - ub['half_w'], co['z_top'] - cz),
             (-0.2, co['z_top'] - cz), (-0.2, 0)]
    objs.append(mitered_frame(f'{PFX}_tower_cornice2', cprof, ub['half_w'], ub['half_w'], (0, 0, cz), material='white_paint', collection=col))
    # dark floor inside the dome rim (a disc: a square cap would poke its corners out above the cornice)
    dm = t['dome']
    objs.append(add_cylinder(f'{PFX}_tower_cap', dm['r'] - 0.08, 0.1, (0, 0, co['z_top'] - 0.1), segments=32, material='roof_dark', collection=col))
    # dome with ribs
    prof = dome_profile(dm['r'], dm['rise'], dm['z_base'], steps=24)
    objs.append(lathe(f'{PFX}_tower_dome', prof, segments=64, material=dm.get('material', 'copper_green'), collection=col, smooth_angle=60))
    nr = dm.get('ribs', 8)
    rib = _rib(f'{PFX}_tower_rib_00', prof, 0.1, 0.03, 0.25, col, dm.get('material', 'copper_green'))
    objs.append(rib)
    for k in range(1, nr):
        objs.append(duplicate(rib, f'{PFX}_tower_rib_{k:02d}', location=(0, 0, 0), rotation=(0, 0, k * 2 * math.pi / nr)))
    # gold stars in rings between the ribs, oriented along the surface normal
    # polish r4: 42 stars of 0.4 m in 4 staggered rows (16/12/8/6 at 12/31/50/68 deg), relief >= 6 cm; the spec's
    # 30 x 0.3 m / 3 rows read too few and too small against crop_tower_left/right
    gs = t['gold_stars']
    size = max(float(gs.get('size', STAR_SIZE)), STAR_SIZE)
    relief = max(float(gs.get('relief', STAR_RELIEF)), STAR_RELIEF)
    star = extrude_polygon(f'{PFX}_star_proto', _star_pts(size, gs.get('points', 8)), relief, -0.01,
                           material='gold', collection=col)
    R, rise, z0 = dm['r'], dm['rise'], dm['z_base']
    rows = [(math.radians(el), n, math.radians(off)) for el, n, off in STAR_ROWS]
    stars = [star]
    first = True
    for a, n, az0 in rows:
        for k in range(n):
            az = az0 + k * 2 * math.pi / n
            p = Vector((R * math.cos(a) * math.sin(az), R * math.cos(a) * math.cos(az), z0 + rise * math.sin(a)))
            nrm = Vector((math.cos(a) * math.sin(az) / R, math.cos(a) * math.cos(az) / R, math.sin(a) / rise)).normalized()
            rot = nrm.to_track_quat('Z', 'Y').to_euler()
            if first:
                place(star, location=p, rotation=rot)
                first = False
            else:
                stars.append(duplicate(star, f'{PFX}_star', location=p, rotation=rot))
    objs.append(_join(stars, f'{PFX}_tower_stars'))
    # orb neck, orb, cross
    orb = t['orb']
    nk = orb['neck']
    objs.append(lathe(f'{PFX}_tower_neck', [(0, nk[0] - 0.05), (0.22, nk[0] - 0.05), (0.22, nk[0] + 0.1), (0.1, nk[0] + 0.2), (0.07, nk[1] - 0.1),
                                            (0.1, nk[1]), (0, nk[1])], segments=24, material='gold', collection=col))
    objs.append(lathe(f'{PFX}_tower_orb', _orb_profile(orb['r'], orb['z']), segments=32, material='gold', collection=col, smooth_angle=60))
    cr = t['cross']
    objs.append(_cross(f'{PFX}_tower_cross', cr['z_base'], cr['h'], cr['w'], cr['thickness'], col, cr.get('material', 'gold')))
    return objs


def build_towers(spec, col):
    t = spec['towers']
    names = t.get('names', ['T%d' % i for i in range(len(t['positions']))])
    proto = _tower_proto(spec, col)
    objs = []
    for i, (px, py) in enumerate(t['positions']):
        nm = names[i]
        for ob in proto:
            if i == 0:
                ob.location = (px, py, 0)
                ob.name = ob.name.replace(f'{PFX}_', f'{PFX}_{nm}_', 1)
                objs.append(ob)
            else:
                objs.append(duplicate(ob, ob.name.replace(f'{PFX}_{names[0]}_', f'{PFX}_{nm}_', 1), location=(px, py, 0)))
    return objs


# ----------------------------------------------------------------------------- module contract
def build(spec, col):
    objs = []
    objs += build_drum(spec, col)
    objs += build_dome(spec, col)
    objs += build_towers(spec, col)
    return objs


# ----------------------------------------------------------------------------- standalone test
if __name__ == '__main__':
    spec = load_spec()
    for k, v in spec.get('materials', {}).items():
        if isinstance(v, dict) and 'rgb' in v:
            d = {'Base Color': tuple(v['rgb']) + (1,), 'Roughness': v.get('roughness', 0.6)}
            if 'metallic' in v:
                d['Metallic'] = v['metallic']
            MATERIAL_SPECS[k] = d
    sc = reset_scene()
    col = get_collection('Cathedral')
    t0 = time.time()
    objs = build(spec, col)
    print(f'[domes] built {len(objs)} objects in {time.time() - t0:.1f}s; scene (objects, polys) = {count_scene()}')
    # context massing for the previews only (NOT part of build): podium, core, attic, arms, ground
    ctx = get_collection('Context')
    pod = spec['podium']
    add_box('ctx_podium', (2 * pod['half_w'], pod['y_range'][1] - pod['y_range'][0], pod['height']),
            (0, (pod['y_range'][0] + pod['y_range'][1]) / 2, -pod['height'] / 2), material='granite', collection=ctx)
    add_box('ctx_ground', (600, 600, 0.2), (0, 0, spec['square_ground_z'] - 0.1), material='ground', collection=ctx)
    core = spec['core']
    add_box_on('ctx_core', (2 * core['half_w'], 2 * core['half_d'], core['parapet_top_z']), (0, 0, 0), material='wall', collection=ctx)
    at = core['attic']
    add_box_on('ctx_attic', (2 * at['arm_half_w'], 2 * at['half_d'], at['top_z'] - at['z_base']), (0, 0, at['z_base']), material='wall', collection=ctx)
    add_box_on('ctx_attic2', (2 * at['half_w'], 2 * at['arm_half_d'], at['top_z'] - at['z_base']), (0, 0, at['z_base']), material='wall', collection=ctx)
    for key in ('south', 'north', 'east', 'west'):
        a = spec['arms'][key]
        xr, yr = a['x_range'], a['y_range']
        add_box_on(f'ctx_arm_{key}', (xr[1] - xr[0], yr[1] - yr[0], spec['arms']['common']['parapet']['z_top']),
                   ((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2, 0), material='wall', collection=ctx)
    setup_sun_sky(**spec['sun'])
    cam = spec['camera']
    res = tuple(cam.get('preview_resolution', [480, 640]))
    views = sys.argv[1:] or ['1', '2', '3']
    # (1) photo viewpoint
    if '1' in views:
        setup_camera(cam['location'], cam['target'], lens=cam['lens'], shift_y=cam.get('shift_y', 0.0))
        p1 = render(os.path.join(PREVIEWS, 'mod_domes_1.png'), res=res, samples=32)
        compare_with_photo(p1)
    # (2) drum + dome from the south, ~80 m, 20 deg elevation
    if '2' in views:
        tz = 0.5 * (spec['drum']['z_base'] + spec['dome']['cross']['top_z'])
        dist, el = 80.0, math.radians(20)
        setup_camera((0, -dist * math.cos(el), tz + dist * math.sin(el)), (0, 0, tz), lens=50)
        render(os.path.join(PREVIEWS, 'mod_domes_2.png'), res=res, samples=32)
    # (3) SW tower close-up from the south-south-west showing the stars
    if '3' in views:
        px, py = spec['towers']['positions'][1]
        tz = 0.5 * (spec['towers']['z_base'] + spec['towers']['cross']['top_z']) + 1.0
        dist, el, az = 34.0, math.radians(16), math.radians(205)
        setup_camera((px + dist * math.sin(az) * math.cos(el), py + dist * math.cos(az) * math.cos(el), tz + dist * math.sin(el)),
                     (px, py, tz), lens=45)
        render(os.path.join(PREVIEWS, 'mod_domes_3.png'), res=res, samples=32)
    # (debug) SW tower from the west-south-west, low, as the sun sees it
    if 'dbg' in views:
        px, py = spec['towers']['positions'][1]
        tz = 0.5 * (spec['towers']['z_base'] + spec['towers']['cross']['top_z']) + 1.0
        dist, el, az = 30.0, math.radians(8), math.radians(240)
        setup_camera((px + dist * math.sin(az) * math.cos(el), py + dist * math.cos(az) * math.cos(el), tz + dist * math.sin(el)),
                     (px, py, tz), lens=45)
        render(os.path.join(PREVIEWS, 'mod_domes_dbg.png'), res=res, samples=24)
    print('[domes] final count (objects, polys):', count_scene())
