"""mod_statues_site.py - the 12 zinc apostles, the grand stairs and the Senate Square ground.

Statues: four base variants (robe = lathe body flattened front-to-back, shoulders, neck, head with hair
cap/hood, a partial-revolution cloak hanging asymmetrically over one shoulder, thin fold ridges, two arms
built from tapered limb segments, an attribute: chalice / staff-cross / book+pointing / hand cross+scroll,
and a thin plinth under the feet). Each variant is joined into ONE mesh; the 12 figures are linked
duplicates placed with their feet at spec.statues[i].pos and rotation_euler.z = -yaw (modelled facing +Y).
Stairs: one step box duplicated spec.stairs.n_steps times (riser k = 1..n stands at
y = bottom_y + (k-1)*run, its foot at z = bottom_z + (k-1)*rise, so riser 1 is at the foot of the flight and the
top tread ends flush with the podium edge at top_y / top_z), a granite wedge under the flight, two sloping granite
side walls (x_outer / thickness / height_above_steps from the spec) with a coping and a newel block. Each step has
a rounded nosing (NOSING_H bevel, 3 segments) and a second material slot 'granite_nosing' (worn light edge,
NOSING_GAIN x granite) on the bevel + the first NOSING_D of the tread: from the photo viewpoint (almost along the
flight) every tread edge is a thin lighter line as in the photo. The risers/treads use 'granite_step': the spec
granite colour (one RGB node, re-tinted by mod_look) x a slight blue reduction (shaded flight B/R 1.24 in the photo)
x a per-block tone (Brick texture, one course per step keyed on the step's z location so the joints stagger, blocks
BLOCK_W long) x fine grain, with a mild foot->nosing gradient and a joint/grain bump.
Ground: 4 km square plane at square_ground_z with a 'ground' material that gets a Voronoi+Noise bump
(cobble-ish) added to its node tree. Two 1.75 m dark human figures stand on the top steps near the door.
"""
from common import *

PFX = 'site'

MATERIAL_SPECS.setdefault('dark_cloth', {'Base Color': (0.02, 0.02, 0.025, 1), 'Roughness': 0.9})

# stairs polish (tuned from the spec camera against ref/crop_stairs.jpg: photo stairs region mean (29,34,37) sRGB,
# B/R 1.24, per-pixel std 8.5 of which ~3 is the step banding and ~8 the block texture; the flat slab before this
# measured (33,37,44), B/R 1.33, std 1.7)
NOSING_H = 0.035                    # rounded nosing: bevel radius on the tread front edge (m)
NOSING_D = 0.05                     # tread strip behind the front edge that carries 'granite_nosing' (m)
NOSING_GAIN = (2.2, 2.17, 2.03)     # worn light edge: x granite (a touch warmer than the riser); 2.6 x 0.045 m drew
                                    # a solid bright line on every step, 2.0 x 0.035 m was too faint in the full frame
NOSING_ROUGH = 0.65                 # worn edge smoother than the riser (0.85): catches the sky at grazing angles
STEP_TINT = (1.0, 0.98, 0.87)       # shaded flight B/R 1.33 -> ~1.24 (photo)
STEP_GRAD = (0.74, 0.90)            # riser foot -> below the nosing multiplier (object z)
BLOCK_W = 1.3                       # granite block length along the flight (m); one course per step
JOINT_W = 0.012                     # joint width (m)
BLOCK_TONE = (0.55, 1.50)           # per-block random multiplier range (photo: light blocks ~1.7x the dark ones)
BLOCK_JOINT = 0.55                  # joint multiplier
GRAIN_TONE = (0.92, 1.08)           # fine noise grain
PATCH_TONE = (0.84, 1.16)           # 5-10 m lighter / darker patches across the flight (world-space noise)


# ----------------------------------------------------------------------------- local mesh helpers
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


def _join(objects, name):
    bpy.context.view_layer.update()
    return join(objects, name)


def _segment(name, p0, p1, r0, r1, segments=12, material=None, collection=None, scale_y=1.0):
    """Tapered capped cylinder from p0 (radius r0) to p1 (radius r1) - limbs, staffs."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=r0, radius2=r1, depth=L)
    bmesh.ops.translate(bm, vec=Vector((0, 0, L / 2)), verts=bm.verts)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=d.to_track_quat('Z', 'Y').to_matrix(), verts=bm.verts)
    bmesh.ops.translate(bm, vec=p0, verts=bm.verts)
    return _mesh_ob(name, bm, material, collection, smooth_angle=40)


def _ellipsoid(name, radii, center, material=None, collection=None, segments=20, rings=12):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    bmesh.ops.scale(bm, vec=Vector(radii), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _mesh_ob(name, bm, material, collection, smooth_angle=60)


def _spin(name, profile, a0_deg, a1_deg, segments=24, center=(0, 0, 0), scale=(1, 1, 1), closed=True,
          material=None, collection=None, smooth_angle=35):
    """Partial surface of revolution (angles counter-clockwise from +X, degrees) of a CLOSED (r,z) outline,
    capped at both ends: cloaks, mantles, hoods. `scale` is baked into the mesh (flatten front/back)."""
    bm = bmesh.new()
    vs = [bm.verts.new((float(r), 0.0, float(z))) for r, z in profile]
    es = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    if closed:
        es.append(bm.edges.new((vs[-1], vs[0])))
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1), dvec=(0, 0, 0),
                   angle=math.radians(a1_deg - a0_deg), steps=segments, use_merge=False,
                   use_normal_flip=False, use_duplicate=False)
    if closed:
        bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(a0_deg), 3, 'Z'), verts=bm.verts)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _mesh_ob(name, bm, material, collection, smooth_angle)


def _lathe_scaled(name, profile, scale, segments=28, material=None, collection=None):
    """common.lathe() with a non-uniform scale baked in (elliptical section)."""
    ob = lathe(name, profile, segments=segments, material=material, collection=collection)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def _plane(name, size, z, material=None, collection=None):
    bm = bmesh.new()
    h = size / 2
    vs = [bm.verts.new(p) for p in ((-h, -h, z), (h, -h, z), (h, h, z), (-h, h, z))]
    bm.faces.new(vs)
    return _mesh_ob(name, bm, material, collection)


def _rot_box(name, size, center, rot, material=None, collection=None):
    """Box rotated (euler, radians) about its own centre, baked into the mesh."""
    return add_box(name, size, center, material=material, collection=collection, rotation=rot)


# ----------------------------------------------------------------------------- statues
def _robe_r(z, H):
    """x-radius of the robe lathe at height z (figure of height H), used to seat folds."""
    s = H / 3.1
    pts = [(0.0, 0.40), (0.06, 0.41), (0.3, 0.38), (0.8, 0.35), (1.3, 0.33), (1.6, 0.31), (1.9, 0.325),
           (2.15, 0.345), (2.3, 0.34), (2.42, 0.30), (2.52, 0.18)]
    zz = z / s
    for (z0, r0), (z1, r1) in zip(pts, pts[1:]):
        if z0 <= zz <= z1:
            return s * (r0 + (r1 - r0) * (zz - z0) / (z1 - z0))
    return s * pts[-1][1]


def _statue_variant(idx, H, col, material='zinc'):
    """One apostle, feet at the origin, facing +Y (its right hand is +X). Returns a single joined object.
    Variants: 0 chalice raised, 1 tall cross-staff + hand on heart, 2 book at hip + pointing,
    3 small cross held up + scroll. Total height ~H (plinth 0.1 + figure)."""
    s = H / 3.1
    P = 0.10 * s              # plinth height
    parts = []
    nm = lambda t: f'{PFX}_stv{idx}_{t}'
    kw = dict(material=material, collection=col)
    FY = 0.82                 # front-to-back flattening of the round body parts

    # plinth (part of the figure; the architectural pedestal belongs to mod_portico)
    parts.append(add_box_on(nm('plinth'), (0.95 * s, 0.8 * s, P), (0, 0, 0), **kw))
    # robe / body (surface of revolution, flattened in Y)
    prof = [(0.0, 0.0), (0.40, 0.0), (0.41, 0.06), (0.38, 0.3), (0.35, 0.8), (0.33, 1.3), (0.31, 1.6),
            (0.325, 1.9), (0.345, 2.15), (0.34, 2.3), (0.30, 2.42), (0.18, 2.52), (0.0, 2.52)]
    prof = [(r * s, z * s + P) for r, z in prof]
    parts.append(_lathe_scaled(nm('robe'), prof, (1, FY, 1), segments=28, **kw))
    # shoulders (ellipsoid), neck, head, hair cap
    z_sh = 2.40 * s + P
    # sloping shoulders (taller ellipsoid set a little lower so it blends into the robe top instead of a shelf)
    parts.append(_ellipsoid(nm('shoulders'), (0.42 * s, 0.26 * s, 0.21 * s), (0, 0.0, z_sh - 0.06 * s), **kw))
    parts.append(_segment(nm('neck'), (0, 0.01 * s, z_sh), (0, 0.01 * s, 2.72 * s + P), 0.10 * s, 0.09 * s, **kw))
    z_hd = 2.80 * s + P
    rh = 0.165 * s
    parts.append(_ellipsoid(nm('head'), (rh, rh * 1.05, rh * 1.12), (0, 0.0, z_hd), **kw))
    if idx == 1:      # hood: bigger shell around the back of the head, open to the front
        hood = [(0.19, -0.05), (0.21, 0.05), (0.19, 0.17), (0.12, 0.23), (0.0, 0.25),
                (0.0, 0.19), (0.11, 0.17), (0.16, 0.11), (0.165, 0.0), (0.15, -0.06)]
        parts.append(_spin(nm('hood'), [(r * s, z * s) for r, z in hood], 125, 415, segments=20,
                           center=(0, -0.02 * s, z_hd), **kw))
    else:             # hair cap
        parts.append(_ellipsoid(nm('hair'), (rh * 1.08, rh * 1.1, rh * 0.95), (0, -0.035 * s, z_hd + 0.05 * s),
                                segments=16, rings=10, **kw))
    if idx in (0, 3):  # beard
        parts.append(_ellipsoid(nm('beard'), (0.085 * s, 0.07 * s, 0.13 * s), (0, 0.10 * s, z_hd - 0.12 * s),
                                segments=12, rings=8, **kw))

    # cloak: partial revolution hanging from the shoulders, thrown over one shoulder (asymmetric)
    # outer face 5-6.5 cm proud of the robe, inner face 2 cm INSIDE it (no slot between cloak and body),
    # rolled collar over the shoulders
    rr = lambda z: _robe_r(z * s, H) / s
    cz = [0.22, 0.6, 1.0, 1.4, 1.8, 2.1, 2.33]
    cl = [(rr(z) + 0.05 + 0.015 * (1 - z / 2.33), z) for z in cz] + [(0.40, 2.38), (0.37, 2.50), (0.26, 2.56), (0.22, 2.52), (0.31, 2.45)]
    cl += [(rr(z) - 0.02, z) for z in reversed(cz)]
    cl = [(r * s, z * s + P) for r, z in cl]
    spans = {0: (110, 330), 1: (200, 420), 2: (150, 300), 3: (230, 430)}
    a0, a1 = spans[idx]
    parts.append(_spin(nm('cloak'), cl, a0, a1, segments=22, scale=(1, FY, 1), **kw))

    # fold ridges on the robe: narrow partial-revolution shells hugging the lathe profile (they follow the
    # taper of the robe), plus one heavier mantle fold per figure; (angle, span, z0, z1, relief)
    folds = {0: [(72, 6, 0.1, 1.7, 0.035), (96, 5, 0.1, 2.0, 0.03), (118, 7, 0.1, 1.35, 0.04), (42, 16, 0.3, 1.5, 0.025),
                 (300, 6, 0.1, 1.8, 0.03), (84, 26, 0.1, 2.3, 0.06)],
             1: [(80, 6, 0.1, 2.05, 0.03), (104, 5, 0.1, 1.55, 0.035), (60, 14, 0.25, 1.2, 0.025), (132, 6, 0.1, 1.7, 0.04),
                 (20, 10, 0.2, 1.5, 0.03), (108, 24, 0.1, 2.3, 0.06)],
             2: [(75, 6, 0.1, 1.75, 0.035), (100, 5, 0.1, 2.0, 0.03), (126, 12, 0.2, 1.3, 0.04), (55, 6, 0.1, 1.1, 0.03),
                 (340, 10, 0.2, 1.6, 0.025), (66, 22, 0.1, 2.25, 0.06)],
             3: [(86, 6, 0.1, 1.85, 0.03), (112, 5, 0.1, 1.45, 0.035), (64, 14, 0.3, 1.6, 0.025), (146, 6, 0.1, 1.2, 0.04),
                 (10, 10, 0.2, 1.4, 0.03), (120, 24, 0.1, 2.3, 0.06)]}
    for j, (ang, span, z0, z1, relief) in enumerate(folds[idx]):
        zs = [z0 + (z1 - z0) * t / 6 for t in range(7)]
        outer = [(_robe_r(z * s, H) / s + relief, z) for z in zs]
        inner = [(_robe_r(z * s, H) / s - 0.03, z) for z in reversed(zs)]
        prof = [(r * s, z * s + P) for r, z in outer + inner]
        parts.append(_spin(nm(f'fold{j}'), prof, ang - span / 2, ang + span / 2, segments=3, scale=(1, FY, 1), **kw))

    # arms: shoulder joint -> elbow -> hand (right = +X)
    def arm(side, elbow, hand, tag):
        sh = Vector((side * 0.36 * s, 0.03 * s, 2.38 * s + P))
        el, hd = Vector(elbow) * s + Vector((0, 0, P)), Vector(hand) * s + Vector((0, 0, P))
        parts.append(_ellipsoid(nm(f'{tag}_sh'), (0.13 * s, 0.12 * s, 0.13 * s), sh, segments=12, rings=8, **kw))
        parts.append(_segment(nm(f'{tag}_up'), sh, el, 0.115 * s, 0.10 * s, **kw))
        parts.append(_ellipsoid(nm(f'{tag}_el'), (0.10 * s,) * 3, el, segments=12, rings=8, **kw))
        parts.append(_segment(nm(f'{tag}_fore'), el, hd, 0.135 * s, 0.075 * s, **kw))   # wide sleeve -> wrist
        parts.append(_ellipsoid(nm(f'{tag}_hand'), (0.075 * s, 0.065 * s, 0.10 * s), hd, segments=12, rings=8, **kw))
        return hd

    if idx == 0:   # right arm raised with a chalice at head height, left arm holds a book to the chest
        hd = arm(+1, (0.56, 0.16, 2.02), (0.46, 0.26, 2.74), 'R')
        cup = [(0.0, 0.0), (0.09, 0.0), (0.09, 0.02), (0.03, 0.04), (0.03, 0.16), (0.07, 0.19), (0.10, 0.30), (0.0, 0.30)]
        parts.append(lathe(nm('chalice'), [(r * s, z * s) for r, z in cup], segments=16,
                           center=(hd.x, hd.y, hd.z + 0.06 * s), **kw))
        hd2 = arm(-1, (-0.47, 0.06, 1.93), (-0.18, 0.33, 2.02), 'L')
        parts.append(_rot_box(nm('book'), (0.27 * s, 0.07 * s, 0.21 * s), (-0.12 * s, 0.40 * s, 2.05 * s + P), (0.25, 0, -0.3), **kw))
    elif idx == 1:  # tall cross-staff in the right hand (at hip), left hand on the heart
        hd = arm(+1, (0.50, 0.08, 1.90), (0.44, 0.28, 1.50), 'R')
        parts.append(_segment(nm('staff'), (hd.x, hd.y + 0.02 * s, 0.12 * s + P), (hd.x, hd.y + 0.02 * s, 3.25 * s + P), 0.035 * s, 0.03 * s, segments=10, **kw))
        parts.append(add_box(nm('staff_bar'), (0.36 * s, 0.06 * s, 0.06 * s), (hd.x, hd.y + 0.02 * s, 3.0 * s + P), **kw))
        arm(-1, (-0.50, 0.04, 1.95), (-0.05, 0.34, 2.18), 'L')
    elif idx == 2:  # book at the left hip, right arm pointing forward/outward
        hd = arm(+1, (0.52, 0.12, 1.95), (0.42, 0.58, 2.12), 'R')
        parts.append(_segment(nm('finger'), hd, hd + Vector((0.06 * s, 0.16 * s, 0.03 * s)), 0.025 * s, 0.018 * s, segments=8, **kw))
        hd2 = arm(-1, (-0.49, 0.02, 1.90), (-0.44, 0.22, 1.52), 'L')
        parts.append(_rot_box(nm('book'), (0.08 * s, 0.22 * s, 0.30 * s), (-0.50 * s, 0.26 * s, 1.50 * s + P), (0, 0.15, 0.1), **kw))
    else:           # small cross held up in the right hand, scroll hanging in the left
        hd = arm(+1, (0.57, 0.10, 2.10), (0.50, 0.18, 2.86), 'R')
        parts.append(add_box(nm('cross_v'), (0.05 * s, 0.05 * s, 0.62 * s), (hd.x, hd.y + 0.02 * s, hd.z + 0.22 * s), **kw))
        parts.append(add_box(nm('cross_h'), (0.34 * s, 0.05 * s, 0.05 * s), (hd.x, hd.y + 0.02 * s, hd.z + 0.36 * s), **kw))
        hd2 = arm(-1, (-0.47, 0.0, 1.88), (-0.42, 0.18, 1.45), 'L')
        parts.append(_segment(nm('scroll'), hd2 + Vector((0.02 * s, 0.04 * s, -0.22 * s)), hd2 + Vector((-0.02 * s, 0.04 * s, 0.18 * s)), 0.045 * s, 0.045 * s, segments=10, **kw))

    return _join(parts, nm('figure'))


def build_statues(spec, col):
    """The 12 apostles as linked duplicates of 4 variants, feet at statues[i].pos, facing yaw_deg."""
    out = []
    stats = spec['statues']
    H = float(stats[0].get('height', 3.1))
    bases = [_statue_variant(i, H, col) for i in range(4)]
    # variant per statue: the three S figures and the two E figures seen in the photo all differ
    assign = {'S_apex': 0, 'S_west': 3, 'S_east': 1, 'E_apex': 2, 'E_south': 3, 'E_north': 0,
              'W_apex': 1, 'W_south': 2, 'W_north': 3, 'N_apex': 2, 'N_west': 0, 'N_east': 1}
    for i, st in enumerate(stats):
        v = assign.get(st['name'], i % 4)
        yaw = float(st.get('yaw_deg', st.get('facing_deg', 0.0)))
        ob = duplicate(bases[v], f"{PFX}_statue_{st['name']}", location=tuple(st['pos']),
                       rotation=(0, 0, math.radians(-yaw)), scale=(1, 1, 1), collection=col)
        out.append(ob)
    for b in bases:
        bpy.data.objects.remove(b, do_unlink=True)
    return out


# ----------------------------------------------------------------------------- stairs
class _StairGeom:
    """Shared stair arithmetic (steps, wedge, walls and the scale-reference people all use it).
    Riser k (1..n) stands at y = bottom_y + (k-1)*run with its foot at z = bottom_z + (k-1)*rise; its tread runs
    from there to riser k+1; the top tread (k = n) ends at top_y flush with the podium top (top_z)."""
    def __init__(self, st):
        self.rise, self.run, self.n = float(st['step_rise']), float(st['step_run']), int(st['n_steps'])
        self.half_w = float(st.get('half_w', st['width'] / 2))
        self.top_y, self.top_z = float(st['top_y']), float(st.get('top_z', 0.0))
        self.bottom_z = float(st.get('bottom_z', self.top_z - self.n * self.rise))
        self.bottom_y = float(st.get('bottom_y', self.top_y - self.n * self.run))

    def riser_y(self, k):
        return self.bottom_y + (k - 1) * self.run

    def foot_z(self, k):
        return self.bottom_z + (k - 1) * self.rise

    def tread_top_z(self, k):
        return self.foot_z(k) + self.rise


def _granite_palette(spec):
    """Spec granite colour/roughness (spec.materials.granite when present, else MATERIAL_SPECS) as a mat() spec."""
    g = spec.get('materials', {}).get('granite', {})
    base = MATERIAL_SPECS.get('granite', MATERIAL_SPECS['default'])
    return {'Base Color': tuple(g['rgb'])[:3] + (1.0,) if 'rgb' in g else tuple(base['Base Color']),
            'Roughness': float(g.get('roughness', base.get('Roughness', 0.85)))}


def _mix_mul(nt, a_socket, b, location, fac=1.0):
    """Mix(MULTIPLY, RGBA) of a socket with a constant colour / float (held in the node, NOT an RGB node, so
    mod_look._retint_derived - which resets every ShaderNodeRGB to the palette - leaves it alone). Returns the
    result socket. `b` may be a socket too."""
    mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.location = location
    mx.inputs['Factor'].default_value = fac
    nt.links.new(a_socket, mx.inputs[6])
    if hasattr(b, 'is_output'):
        nt.links.new(b, mx.inputs[7])
    else:
        b = tuple(b)
        mx.inputs[7].default_value = (b + (1.0,)) if len(b) == 3 else ((b[0],) * 3 + (1.0,)) if len(b) == 1 else b
    return mx.outputs[2]


def _granite_block_graph(nt, rise, y0=0):
    """Granite block texture shared by 'granite_step' / 'granite_nosing': a Brick texture in WORLD x with the row
    taken from the step object's z location (+ rise/2, i.e. the course centre), so every step is exactly one
    course of BLOCK_W-long blocks and the joints stagger from step to step (Brick offset 0.5 on alternate rows),
    tread and riser of a step sharing the same joints as real step blocks do. Per-block random tone
    BLOCK_TONE[0]..[1], joints BLOCK_JOINT x, fine grain noise GRAIN_TONE. Returns (tone multiplier socket (RGBA),
    bump height socket (float), noise factor socket (float))."""
    geo = nt.nodes.new('ShaderNodeNewGeometry'); geo.location = (-1700, y0)
    oi = nt.nodes.new('ShaderNodeObjectInfo'); oi.location = (-1700, y0 - 250)
    sp = nt.nodes.new('ShaderNodeSeparateXYZ'); sp.location = (-1500, y0)
    nt.links.new(geo.outputs['Position'], sp.inputs['Vector'])
    so = nt.nodes.new('ShaderNodeSeparateXYZ'); so.location = (-1500, y0 - 250)
    nt.links.new(oi.outputs['Location'], so.inputs['Vector'])
    row = nt.nodes.new('ShaderNodeMath'); row.operation = 'ADD'; row.location = (-1300, y0 - 250)
    row.inputs[1].default_value = 0.5 * float(rise)
    nt.links.new(so.outputs['Z'], row.inputs[0])
    # per-step random shift of the joints along x (Object Info 'Random' is per object instance): a strict
    # half-block stagger drew a regular chevron pattern over the flight; real courses have varying block lengths
    shift = nt.nodes.new('ShaderNodeMath'); shift.operation = 'MULTIPLY'; shift.location = (-1300, y0 - 450)
    shift.inputs[1].default_value = 3.0 * BLOCK_W
    nt.links.new(oi.outputs['Random'], shift.inputs[0])
    xs = nt.nodes.new('ShaderNodeMath'); xs.operation = 'ADD'; xs.location = (-1300, y0)
    nt.links.new(sp.outputs['X'], xs.inputs[0]); nt.links.new(shift.outputs['Value'], xs.inputs[1])
    cb = nt.nodes.new('ShaderNodeCombineXYZ'); cb.location = (-1100, y0 - 100)
    nt.links.new(xs.outputs['Value'], cb.inputs['X'])
    nt.links.new(row.outputs['Value'], cb.inputs['Y'])
    brick = nt.nodes.new('ShaderNodeTexBrick'); brick.location = (-900, y0)
    brick.offset = 0.0; brick.offset_frequency = 2; brick.squash = 1.0
    brick.inputs['Scale'].default_value = 1.0
    brick.inputs['Brick Width'].default_value = BLOCK_W
    brick.inputs['Row Height'].default_value = float(rise)
    brick.inputs['Mortar Size'].default_value = JOINT_W
    brick.inputs['Mortar Smooth'].default_value = 0.15
    brick.inputs['Bias'].default_value = 0.0
    brick.inputs['Color1'].default_value = (BLOCK_TONE[1],) * 3 + (1.0,)
    brick.inputs['Color2'].default_value = (BLOCK_TONE[0],) * 3 + (1.0,)
    brick.inputs['Mortar'].default_value = (BLOCK_JOINT,) * 3 + (1.0,)
    nt.links.new(cb.outputs['Vector'], brick.inputs['Vector'])
    noi = nt.nodes.new('ShaderNodeTexNoise'); noi.location = (-900, y0 - 350)
    noi.inputs['Scale'].default_value = 9.0; noi.inputs['Detail'].default_value = 3.0
    noi.inputs['Roughness'].default_value = 0.6
    nt.links.new(geo.outputs['Position'], noi.inputs['Vector'])
    grain = nt.nodes.new('ShaderNodeMapRange'); grain.location = (-700, y0 - 350)
    grain.inputs['To Min'].default_value = GRAIN_TONE[0]; grain.inputs['To Max'].default_value = GRAIN_TONE[1]
    nt.links.new(noi.outputs['Fac'], grain.inputs['Value'])
    big = nt.nodes.new('ShaderNodeTexNoise'); big.location = (-900, y0 - 750)          # ~6 m patches
    big.inputs['Scale'].default_value = 0.16; big.inputs['Detail'].default_value = 2.0
    nt.links.new(geo.outputs['Position'], big.inputs['Vector'])
    patch = nt.nodes.new('ShaderNodeMapRange'); patch.location = (-700, y0 - 750)
    patch.inputs['To Min'].default_value = PATCH_TONE[0]; patch.inputs['To Max'].default_value = PATCH_TONE[1]
    nt.links.new(big.outputs['Fac'], patch.inputs['Value'])
    tone = _mix_mul(nt, brick.outputs['Color'], grain.outputs['Result'], (-500, y0))
    tone = _mix_mul(nt, tone, patch.outputs['Result'], (-500, y0 - 200))
    # bump height: joints recessed (1 - mortar factor) + grain
    inv = nt.nodes.new('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.location = (-700, y0 - 550)
    inv.inputs[0].default_value = 1.0
    nt.links.new(brick.outputs['Factor'], inv.inputs[1])
    hgt = nt.nodes.new('ShaderNodeMath'); hgt.operation = 'MULTIPLY_ADD'; hgt.location = (-500, y0 - 550)
    hgt.inputs[1].default_value = 0.35
    nt.links.new(noi.outputs['Fac'], hgt.inputs[0])
    nt.links.new(inv.outputs['Value'], hgt.inputs[2])
    return tone, hgt.outputs['Value'], noi.outputs['Fac']


def _granite_bump(nt, height, bsdf, strength, distance, location):
    bp = nt.nodes.new('ShaderNodeBump'); bp.location = location
    bp.inputs['Strength'].default_value = strength; bp.inputs['Distance'].default_value = distance
    nt.links.new(height, bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], bsdf.inputs['Normal'])


def _step_material(spec, rise):
    """'granite_step' (risers + treads): spec granite colour (ONE ShaderNodeRGB, which mod_look._retint_derived
    points at the palette) x STEP_TINT (less blue: the shaded flight is B/R 1.24 in the photo, 1.33 in the render
    before this) x per-block tone / joints / grain (_granite_block_graph) x a mild object-z gradient (riser foot
    STEP_GRAD[0] -> nosing STEP_GRAD[1]; the old 0.72->1.38 ramp is replaced by the real nosing material).
    Roughness varies with the grain, joints and grain are bumped. The mean stays at the old level."""
    MATERIAL_SPECS['granite_step'] = _granite_palette(spec)
    m = mat('granite_step')
    nt = m.node_tree
    if any(n.type == 'TEX_BRICK' for n in nt.nodes):
        return m
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return m
    rough = float(MATERIAL_SPECS['granite_step']['Roughness'])
    tone, height, nfac = _granite_block_graph(nt, rise)
    tc = nt.nodes.new('ShaderNodeTexCoord'); tc.location = (-1300, 400)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); sep.location = (-1100, 400)
    nt.links.new(tc.outputs['Object'], sep.inputs['Vector'])
    grad = nt.nodes.new('ShaderNodeMapRange'); grad.location = (-900, 400); grad.clamp = True
    grad.inputs['From Min'].default_value = 0.0; grad.inputs['From Max'].default_value = float(rise) - NOSING_H
    grad.inputs['To Min'].default_value = STEP_GRAD[0]; grad.inputs['To Max'].default_value = STEP_GRAD[1]
    nt.links.new(sep.outputs['Z'], grad.inputs['Value'])
    rgb = nt.nodes.new('ShaderNodeRGB'); rgb.location = (-700, 600)
    rgb.outputs[0].default_value = MATERIAL_SPECS['granite_step']['Base Color']
    c = _mix_mul(nt, rgb.outputs[0], STEP_TINT, (-500, 600))
    c = _mix_mul(nt, c, grad.outputs['Result'], (-350, 500))
    c = _mix_mul(nt, c, tone, (-200, 400))
    nt.links.new(c, bsdf.inputs['Base Color'])
    rr = nt.nodes.new('ShaderNodeMapRange'); rr.location = (-200, -100)
    rr.inputs['To Min'].default_value = rough - 0.06; rr.inputs['To Max'].default_value = min(1.0, rough + 0.06)
    nt.links.new(nfac, rr.inputs['Value'])
    nt.links.new(rr.outputs['Result'], bsdf.inputs['Roughness'])
    _granite_bump(nt, height, bsdf, 0.3, 0.005, (-200, -350))
    return m


def _nosing_material(spec, rise):
    """'granite_nosing': the worn front edge of each tread (bevel + the first NOSING_D of the tread). Same palette
    RGB node (re-tinted by mod_look) x STEP_TINT x NOSING_GAIN x the same block tone (so the light line breaks
    per block as in the photo), smoother than the riser (worn) - roughness via a Value node so the retint, which
    only touches UNLINKED Principled sockets, keeps it."""
    MATERIAL_SPECS['granite_nosing'] = _granite_palette(spec)
    m = mat('granite_nosing')
    nt = m.node_tree
    if any(n.type == 'TEX_BRICK' for n in nt.nodes):
        return m
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return m
    tone, height, nfac = _granite_block_graph(nt, rise)
    rgb = nt.nodes.new('ShaderNodeRGB'); rgb.location = (-700, 600)
    rgb.outputs[0].default_value = MATERIAL_SPECS['granite_nosing']['Base Color']
    c = _mix_mul(nt, rgb.outputs[0], STEP_TINT, (-500, 600))
    c = _mix_mul(nt, c, NOSING_GAIN, (-350, 500))
    c = _mix_mul(nt, c, tone, (-200, 400))
    nt.links.new(c, bsdf.inputs['Base Color'])
    val = nt.nodes.new('ShaderNodeValue'); val.location = (-200, -100)
    val.outputs[0].default_value = NOSING_ROUGH
    nt.links.new(val.outputs[0], bsdf.inputs['Roughness'])
    _granite_bump(nt, height, bsdf, 0.2, 0.004, (-200, -350))
    return m


def build_stairs(spec, col):
    st = spec['stairs']
    G = _StairGeom(st)
    rise, run, n, half_w = G.rise, G.run, G.n, G.half_w
    top_y, top_z, bottom_y, bottom_z = G.top_y, G.top_z, G.bottom_y, G.bottom_z
    step_mat = _step_material(spec, rise)
    nosing_mat = _nosing_material(spec, rise)
    out = []
    # one step: box (2*half_w x run x rise), origin at the riser foot, with a rounded nosing (NOSING_H bevel, 3
    # segments) on the front-top edge; the bevel faces + the first NOSING_D of the tread go to material slot 1
    # ('granite_nosing'): the thin light line per step seen from the foot of the flight in the photo
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((2 * half_w, run, rise)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, run / 2, rise / 2)), verts=bm.verts)
    nos = [e for e in bm.edges if all(abs(v.co.y) < 1e-6 and abs(v.co.z - rise) < 1e-6 for v in e.verts)]
    bmesh.ops.bevel(bm, geom=nos + [v for e in nos for v in e.verts], offset=NOSING_H, offset_type='OFFSET',
                    segments=3, profile=0.6, affect='EDGES', clamp_overlap=True)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                           plane_co=(0.0, NOSING_D, 0.0), plane_no=(0.0, 1.0, 0.0))
    for f in bm.faces:
        c = f.calc_center_median()
        f.material_index = 1 if (c.z > rise - NOSING_H - 1e-4 and c.y < NOSING_D + 1e-4) else 0
    step0 = _mesh_ob(f'{PFX}_step_01', bm, step_mat, col)
    step0.data.materials.append(nosing_mat)
    # riser k (1..n) stands at y = riser_y(k) with its foot at foot_z(k); the top tread (k = n) ends at top_y
    # flush with the podium top, so nothing of the flight lies inside the podium slab (body) and no face is
    # coplanar with the podium's south face
    for k in range(1, n + 1):
        y_k, z_k = G.riser_y(k), G.foot_z(k)
        if k == 1:
            place(step0, location=(0, y_k, z_k))
            out.append(step0)
        else:
            out.append(duplicate(step0, f'{PFX}_step_{k:02d}', location=(0, y_k, z_k), rotation=(0, 0, 0), collection=col))
    # granite wedge closing the underside of the flight along the line of the riser feet (riser 1 at the foot,
    # riser n one run in front of the podium edge); its back face stays 2 mm in front of the podium's south face
    e = 0.002
    wedge = prism(f'{PFX}_stair_fill', [(top_y - e, top_z - rise - e), (G.riser_y(n), top_z - rise - e),
                                        (bottom_y + e, bottom_z - e), (top_y - e, bottom_z - e)],
                  2 * half_w - 0.02, material='granite', collection=col)
    place(wedge, location=(-half_w + 0.01, 0, 0))
    out.append(wedge)
    # side walls: sloping granite parapet height_above_steps over the nosing line, x from half_w to x_outer
    sw = st.get('side_walls', {})
    if sw.get('present', True):
        x_out = float(sw.get('x_outer', half_w + 0.8))
        th = float(sw.get('thickness', x_out - half_w))
        h = float(sw.get('height_above_steps', 0.45))
        x_in = x_out - th
        z_bot_top = bottom_z + h
        for side, tag in ((1, 'E'), (-1, 'W')):
            prof = [(top_y, top_z + h), (bottom_y, z_bot_top), (bottom_y, bottom_z - 0.3), (top_y, bottom_z - 0.3)]
            w = prism(f'{PFX}_stair_wall_{tag}', prof, th, material='granite', collection=col)
            place(w, location=(min(side * x_in, side * x_out), 0, 0))
            out.append(w)
            # coping slab 0.12 thick, 0.06 overhang each side, along the slope
            cp = prism(f'{PFX}_stair_coping_{tag}', [(top_y, top_z + h + 0.12), (bottom_y - 0.06, z_bot_top + 0.12),
                                                      (bottom_y - 0.06, z_bot_top - 0.02), (top_y, top_z + h - 0.02)],
                       th + 0.12, material='granite', collection=col)
            place(cp, location=(min(side * x_in, side * x_out) - 0.06, 0, 0))
            out.append(cp)
            # newel block at the foot
            out.append(add_box_on(f'{PFX}_stair_newel_{tag}', (th + 0.4, th + 0.6, h + 0.45),
                                  (side * (x_in + th / 2), bottom_y - 0.1, bottom_z - 0.01), material='granite', collection=col))
    return out


# ----------------------------------------------------------------------------- ground
def _ground_material():
    """'ground' material (colour from MATERIAL_SPECS) + cobble-ish Voronoi/Noise bump and tone variation."""
    m = mat('ground')
    nt = m.node_tree
    if any(n.type == 'TEX_VORONOI' for n in nt.nodes):
        return m
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        return m
    tc = nt.nodes.new('ShaderNodeTexCoord'); tc.location = (-1300, 0)
    vor = nt.nodes.new('ShaderNodeTexVoronoi'); vor.location = (-1050, 150)
    vor.feature = 'DISTANCE_TO_EDGE'; vor.inputs['Scale'].default_value = 6.0          # setts ~ 0.17 m
    vor.inputs['Randomness'].default_value = 0.35
    noi = nt.nodes.new('ShaderNodeTexNoise'); noi.location = (-1050, -150)
    noi.inputs['Scale'].default_value = 14.0; noi.inputs['Detail'].default_value = 4.0
    noi.inputs['Roughness'].default_value = 0.6
    big = nt.nodes.new('ShaderNodeTexNoise'); big.location = (-1050, -400)
    big.inputs['Scale'].default_value = 0.08; big.inputs['Detail'].default_value = 2.0   # ~12 m tone patches
    nt.links.new(tc.outputs['Object'], vor.inputs['Vector'])
    nt.links.new(tc.outputs['Object'], noi.inputs['Vector'])
    nt.links.new(tc.outputs['Object'], big.inputs['Vector'])
    # joints: clamp the edge distance -> grooves between setts
    ramp = nt.nodes.new('ShaderNodeMapRange'); ramp.location = (-800, 150)
    ramp.inputs['From Min'].default_value = 0.0; ramp.inputs['From Max'].default_value = 0.045
    ramp.clamp = True
    nt.links.new(vor.outputs['Distance'], ramp.inputs['Value'])
    mix = nt.nodes.new('ShaderNodeMath'); mix.operation = 'MULTIPLY_ADD'; mix.location = (-600, 100)
    mix.inputs[1].default_value = 0.5
    nt.links.new(noi.outputs['Fac'], mix.inputs[0])
    nt.links.new(ramp.outputs['Result'], mix.inputs[2])
    bump = nt.nodes.new('ShaderNodeBump'); bump.location = (-350, -100)
    bump.inputs['Strength'].default_value = 0.18; bump.inputs['Distance'].default_value = 0.015
    nt.links.new(mix.outputs['Value'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    # tone variation around the spec colour (+-12 %)
    base = tuple(bsdf.inputs['Base Color'].default_value)
    rgb = nt.nodes.new('ShaderNodeRGB'); rgb.location = (-800, -300); rgb.outputs[0].default_value = base
    mul = nt.nodes.new('ShaderNodeMapRange'); mul.location = (-800, -500)
    mul.inputs['To Min'].default_value = 0.88; mul.inputs['To Max'].default_value = 1.12
    nt.links.new(big.outputs['Fac'], mul.inputs['Value'])
    mixc = nt.nodes.new('ShaderNodeMix'); mixc.data_type = 'RGBA'; mixc.blend_type = 'MULTIPLY'; mixc.location = (-550, -300)
    mixc.inputs['Factor'].default_value = 1.0
    nt.links.new(rgb.outputs[0], mixc.inputs[6])
    nt.links.new(mul.outputs['Result'], mixc.inputs[7])
    # darken the joints slightly
    mixj = nt.nodes.new('ShaderNodeMix'); mixj.data_type = 'RGBA'; mixj.blend_type = 'MULTIPLY'; mixj.location = (-350, -300)
    mixj.inputs['Factor'].default_value = 0.15
    nt.links.new(mixc.outputs[2], mixj.inputs[6])
    nt.links.new(ramp.outputs['Result'], mixj.inputs[7])
    nt.links.new(mixj.outputs[2], bsdf.inputs['Base Color'])
    return m


def build_ground(spec, col):
    m = _ground_material()
    gz = float(spec.get('square_ground_z', -7.04))
    # 40 km so the plane reaches the horizon from elevated check cameras (spec minimum is 400 m); the
    # photo camera's clip_end (2 km) still cuts it far below the frame bottom.
    return [_plane(f'{PFX}_ground', 40000.0, gz, material=m, collection=col)]


# ----------------------------------------------------------------------------- scale-reference people
def _person(name, pos, yaw_deg, h, col, material='dark_cloth'):
    s = h / 1.75
    x, y, z = pos
    parts = []
    kw = dict(material=material, collection=col)
    for sd in (-1, 1):
        parts.append(_segment(f'{name}_leg{sd}', (x + sd * 0.09 * s, y, z), (x + sd * 0.08 * s, y, z + 0.82 * s), 0.07 * s, 0.075 * s, segments=8, **kw))
    parts.append(_segment(f'{name}_torso', (x, y, z + 0.78 * s), (x, y, z + 1.45 * s), 0.15 * s, 0.19 * s, segments=10, **kw))
    parts.append(_ellipsoid(f'{name}_shoulders', (0.22 * s, 0.12 * s, 0.07 * s), (x, y, z + 1.45 * s), segments=10, rings=6, **kw))
    for sd in (-1, 1):
        parts.append(_segment(f'{name}_arm{sd}', (x + sd * 0.21 * s, y, z + 1.42 * s), (x + sd * 0.24 * s, y + 0.05 * s, z + 0.80 * s), 0.05 * s, 0.04 * s, segments=8, **kw))
    parts.append(_segment(f'{name}_neck', (x, y, z + 1.42 * s), (x, y, z + 1.55 * s), 0.05 * s, 0.05 * s, segments=8, **kw))
    parts.append(_ellipsoid(f'{name}_head', (0.10 * s, 0.11 * s, 0.12 * s), (x, y, z + 1.64 * s), segments=12, rings=8, **kw))
    ob = _join(parts, name)
    # yaw about the figure's own axis
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.rotate(bm, cent=Vector((x, y, z)), matrix=Matrix.Rotation(math.radians(-yaw_deg), 3, 'Z'), verts=bm.verts)
    bm.to_mesh(ob.data); bm.free()
    return ob


def build_people(spec, col):
    G = _StairGeom(spec['stairs'])
    # standing mid-tread on the second and third treads from the top (k = n-1, n-2), left of the door as in the photo
    k = G.n - 1
    y, z = G.riser_y(k) + G.run * 0.5, G.tread_top_z(k)
    return [_person(f'{PFX}_person_1', (-2.3, y, z), 165, 1.75, col),
            _person(f'{PFX}_person_2', (-3.2, y - G.run, z - G.rise), 200, 1.68, col)]


# ----------------------------------------------------------------------------- module entry
def build(spec, col):
    objs = []
    objs += build_ground(spec, col)
    objs += build_stairs(spec, col)
    objs += build_statues(spec, col)
    objs += build_people(spec, col)
    return objs


# ----------------------------------------------------------------------------- standalone test
if __name__ == '__main__':
    spec = load_spec()
    for k, v in spec.get('materials', {}).items():          # spec palette (mod_look owns this in the final scene)
        if isinstance(v, dict) and 'rgb' in v:
            d = {'Base Color': tuple(v['rgb']) + (1,), 'Roughness': v.get('roughness', 0.6)}
            if 'metallic' in v:
                d['Metallic'] = v['metallic']
            MATERIAL_SPECS[k] = d
    sc = reset_scene()
    col = get_collection('Cathedral')
    t0 = time.time()
    objs = build(spec, col)
    print(f'[statues_site] built {len(objs)} objects in {time.time() - t0:.1f}s; scene (objects, polys) = {count_scene()}')

    # ---- context massing for the previews only (NOT part of build): podium, core, arms, attic, towers,
    # simplified porticos (columns, entablature, pediment) and the acroteria pedestals the statues stand on
    ctx = get_collection('Context')
    pod = spec['podium']
    add_box('ctx_podium', (2 * pod['half_w'], pod['y_range'][1] - pod['y_range'][0], pod['height']),
            (0, (pod['y_range'][0] + pod['y_range'][1]) / 2, -pod['height'] / 2), material='granite', collection=ctx)
    core = spec['core']
    add_box_on('ctx_core', (2 * core['half_w'], 2 * core['half_d'], core['parapet_top_z']), (0, 0, 0), material='wall', collection=ctx)
    at = core['attic']
    add_box_on('ctx_attic', (2 * at['arm_half_w'], 2 * at['half_d'], at['top_z'] - at['z_base']), (0, 0, at['z_base']), material='wall', collection=ctx)
    add_box_on('ctx_attic2', (2 * at['half_w'], 2 * at['arm_half_d'], at['top_z'] - at['z_base']), (0, 0, at['z_base']), material='wall', collection=ctx)
    tw = spec['towers']
    for (tx, ty), tn in zip(tw['positions'], tw['names']):
        add_box_on(f'ctx_tower_{tn}', (6.4, 6.4, 13.5), (tx, ty, tw['z_base']), material='white_paint', collection=ctx)
    add_cylinder('ctx_drum', spec['drum']['radius'], spec['drum']['top_z'] - spec['drum']['z_base'], (0, 0, spec['drum']['z_base']), material='white_paint', collection=ctx)
    lathe('ctx_dome', dome_profile(spec['dome']['radius'], spec['dome']['rise'], spec['dome']['z_base']), material='copper_green', collection=ctx)
    for key in ('south', 'north', 'east', 'west'):
        a = spec['arms'][key]
        xr, yr = a['x_range'], a['y_range']
        add_box_on(f'ctx_arm_{key}', (xr[1] - xr[0], yr[1] - yr[0], spec['arms']['common']['parapet']['z_top']),
                   ((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2, 0), material='wall', collection=ctx)
    po = spec['portico']
    ent, ped, acr = po['entablature'], po['pediment'], po['acroteria_pedestals']
    for inst in po['instances']:
        fac = math.radians(inst['facing_deg'])
        R = Matrix.Rotation(-fac, 3, 'Z')          # local frame: x = offset along the facade, +y toward the wall, facing +Y when facing_deg=0 ... build S (facing 180) then rotate
        cl, wall = inst['column_line'], inst['wall']
        depth = abs(wall - cl)
        def W(ox, oy, oz):          # local (offset, toward-outside, z) -> world; the facade normal points to facing_deg
            n = Vector((math.sin(fac), math.cos(fac), 0))
            t = Vector((math.cos(fac), -math.sin(fac), 0))
            base = n * abs(cl)
            p = base + t * ox + n * oy
            return (p.x, p.y, oz)
        for off in po['column_offsets']:
            add_cylinder(f"ctx_col_{inst['name']}_{off}", po['r_bottom'], po['column_h'], W(off, 0, 0), segments=20, material='white_paint', collection=ctx)
        eb = add_box(f"ctx_ent_{inst['name']}", (2 * ent['half_w'], depth + ent['projection'], ent['z_top'] - ent['z_bottom']),
                     W(0, (ent['projection'] - depth) / 2, (ent['z_top'] + ent['z_bottom']) / 2), rotation=(0, 0, -fac), material='white_paint', collection=ctx)
        tri = extrude_polygon(f"ctx_ped_{inst['name']}", [(-ped['half_w'], 0), (ped['half_w'], 0), (0, ped['apex_z'] - ped['base_z'])], 0.6, 0,
                              material='white_paint', collection=ctx)
        tri.rotation_euler = Euler((math.pi / 2, 0, -fac)) if False else Euler((math.pi / 2, 0, 0))
        # rotate about Z after tilting: compose matrices
        tri.matrix_world = Matrix.Translation(Vector(W(0, 0.3, ped['base_z']))) @ Matrix.Rotation(-fac, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'X')
        add_box_on(f"ctx_apexped_{inst['name']}", (acr['apex']['size'], acr['apex']['size'], acr['apex']['z_top'] - acr['apex']['z_base']),
                   W(0, 0, acr['apex']['z_base']), rotation=(0, 0, -fac), material='white_paint', collection=ctx)
        for sgn in (-1, 1):
            add_box_on(f"ctx_cped_{inst['name']}_{sgn}", (acr['corners']['size'], acr['corners']['size'], acr['corners']['z_top'] - acr['corners']['z_base']),
                       W(sgn * acr['corners']['offset_along_facade'], 0, acr['corners']['z_base']), rotation=(0, 0, -fac), material='white_paint', collection=ctx)
    # a lineup of the four variants on the square for the close-up (context only)
    H = spec['statues'][0]['height']
    gz = spec['square_ground_z']
    lineup = [_statue_variant(i, H, ctx) for i in range(4)]
    for i, ob in enumerate(lineup):
        place(ob, location=((i - 1.5) * 1.7, -70.0, gz), rotation=(0, 0, math.radians(-180)))
    _person('ctx_person_ref', (3.6, -69.5, gz), 180, 1.75, ctx)
    bpy.context.view_layer.update()

    setup_sun_sky(**spec['sun'])
    cam = spec['camera']
    res = tuple(cam.get('preview_resolution', [480, 640]))
    # (1) photo viewpoint
    setup_camera(cam['location'], cam['target'], lens=cam['lens'], shift_y=cam.get('shift_y', 0.0))
    for ob in lineup:
        ob.hide_render = True
    bpy.data.objects['ctx_person_ref'].hide_render = True
    p1 = render(os.path.join(PREVIEWS, 'mod_statues_site_1.png'), res=res, samples=32)
    compare_with_photo(p1)
    # (2) close-up of the statue lineup (3-4 figures) from ~12 m, slightly below eye level of the figures
    for ob in lineup:
        ob.hide_render = False
    bpy.data.objects['ctx_person_ref'].hide_render = False
    setup_camera((1.5, -70.0 - 12.0, gz + 1.6), (0.3, -70.0, gz + 1.7), lens=40)
    render(os.path.join(PREVIEWS, 'mod_statues_site_2.png'), res=res, samples=32)
    # (3) the stairs from the square at eye level, three-quarter from the south-east
    for ob in lineup:
        ob.hide_render = True
    bpy.data.objects['ctx_person_ref'].hide_render = True
    setup_camera((26.0, -82.0, gz + 1.6), (2.0, -44.0, -1.0), lens=30)
    render(os.path.join(PREVIEWS, 'mod_statues_site_3.png'), res=res, samples=32)
    print('[statues_site] final count (objects, polys):', count_scene())
