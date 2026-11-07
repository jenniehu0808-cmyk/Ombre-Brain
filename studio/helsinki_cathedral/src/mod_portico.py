"""mod_portico.py - the four hexastyle Corinthian porticos of Helsinki Cathedral.

Per portico (S, N, E, W from spec['portico']['instances']): 6 columns (plinth, Attic base, shaft with
entasis, Corinthian capital with two rows of acanthus leaves, volutes, fleurons and a concave-sided abacus),
the entablature from the column line back to the arm end wall incl. the two returns (open mitred sweep with
body's cornice outline so the returns run seamlessly into the flank entablature; three-fascia architrave,
frieze, cornice with dentils + modillions), the pediment (tympanum, raking cornice with dentils + modillions,
dark roof cap + a dark gable block behind it up to the arm roof eaves), the two L-shaped corner antae and the
three acroteria pedestals.
Cycles note: never let two solids share a coplanar face with the same normal (it renders black); touching
faces with opposite normals are fine.

The south portico is built once in a LOCAL frame (x = offset along the facade, y = 0 on the column line,
+y toward the arm end wall at y = 3.0, -y outward) and then transformed to its world position; N/E/W are
linked duplicates of every object with the composed transform (facing_deg from the spec).
Per spec: no stylobate/steps (stylobate.height == 0, plinths stand on the podium top z = 0); the back wall
(door, responding pilasters) belongs to mod_body.
"""
from common import *

PFX = 'portico'


# ----------------------------------------------------------------------------- small geometry helpers
def _join(objects, name):
    """common.join() reads matrix_world, which is stale for freshly placed objects headless: update first."""
    bpy.context.view_layer.update()
    return join(objects, name)


def _mesh_ob(name, bm, material=None, collection=None, smooth_angle=None):
    """bmesh -> mesh object linked into `collection` (local copy of common's private finisher)."""
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


def _interp(profile, z):
    """radius of a lathe (r,z) profile at height z (piecewise linear on the outer outline)."""
    pts = [(r, zz) for r, zz in profile if r > 0]
    if z <= pts[0][1]:
        return pts[0][0]
    for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return pts[-1][0]


def _leaf(name, z0, h, out, w_base, r_at, collection, material='white_paint', thick=0.035):
    """One acanthus leaf hugging a bell of radius r_at(z): a thin, tapered, outward-curling solid.
    Built at angle 0 (+X radial) around the local Z axis."""
    N, K = 12, 5
    # raw centre line: angle from vertical grows with t, tip droops past horizontal
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
    rows = []
    for (zz, rr, t) in raw:
        zw = z0 + zz * (h / zmax)
        off = rr * (out / rmax)
        rows.append((zw, r_at(zw) + 0.015 + off, t))
    bm = bmesh.new()
    front, back = [], []
    for (zw, rc, t) in rows:
        u = max(0.0, (t - 0.5) / 0.5)
        w = w_base * (0.80 + 0.55 * t) * ((1.0 - u) ** 0.8 * 0.93 + 0.07)
        w *= 1.0 + 0.12 * math.sin(2 * math.pi * 3.0 * t + 0.6)          # acanthus lobes along the edge
        fr, bk = [], []
        for k in range(K):
            s = k / (K - 1) - 0.5           # -0.5 .. 0.5 across the leaf
            ang = s * w / max(rc, 0.3)
            cup = 0.05 * (1 - (2 * s) ** 2) * (0.25 + 0.75 * (1 - t))  # centre bulges outward
            rk = rc - 0.05 * (0.25 + 0.75 * (1 - t)) + cup
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
    if bm.calc_volume(signed=True) < 0:          # the curled shell fools recalc_face_normals: make it outward-facing
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = True
    return _mesh_ob(name, bm, material, collection)


def _torus(name, R, rm, collection, material='white_paint', seg=12, prof=8):
    prof_pts = [(R + rm * math.cos(2 * math.pi * i / prof), rm * math.sin(2 * math.pi * i / prof)) for i in range(prof + 1)]
    return lathe(name, prof_pts, segments=seg, collection=collection, material=material, smooth_angle=60)


def _stalk(name, A, B, r0, r1, collection, material='white_paint'):
    """tapered cylinder from point A to point B."""
    A, B = Vector(A), Vector(B)
    d = B - A
    ob = add_cylinder(name, r0, d.length, base_center=(0, 0, 0), segments=10, radius_top=r1,
                      collection=collection, material=material)
    place(ob, location=A, rotation=d.to_track_quat('Z', 'Y').to_euler())
    return ob


def _abacus_polygon(a_tip, a_mid, n_side=9):
    """Square abacus footprint with concave sides: corner tips at +-a_tip, side centres at +-a_mid."""
    pts = []
    depth = a_tip - a_mid
    for s in range(4):
        ang = math.radians(90 * s)
        c, sn = math.cos(ang), math.sin(ang)
        for i in range(n_side):
            u = 0.06 + 0.88 * i / (n_side - 1)
            # along the side (local frame: outward +x, along +y), then rotate
            x = a_tip - depth * math.sin(math.pi * u)
            y = -a_tip + 2 * a_tip * u
            pts.append((x * c - y * sn, x * sn + y * c))
    return pts


def _gable_moulding(name, profile, x_end, z_apex_base, slope, collection, material='white_paint', smooth_angle=None):
    """Mitred raking moulding for both slopes of a pediment: profile = closed polygon of (y, dz) where dz is the
    vertical offset above the rake base line z = z_apex_base - slope*|x|. Vertical end caps at x = +-x_end."""
    bm = bmesh.new()
    xs = [-x_end, 0.0, x_end]
    V = []
    for (y, dz) in profile:
        V.append([bm.verts.new((x, y, z_apex_base - slope * abs(x) + dz)) for x in xs])
    n = len(profile)
    for j in range(n):
        k = (j + 1) % n
        for q in range(2):
            try:
                bm.faces.new((V[j][q], V[j][q + 1], V[k][q + 1], V[k][q]))
            except ValueError:
                pass
    try:
        bm.faces.new([V[j][0] for j in range(n)])
        bm.faces.new([V[j][2] for j in reversed(range(n))])
    except ValueError:
        pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mesh_ob(name, bm, material, collection, smooth_angle)


# ----------------------------------------------------------------------------- column
def _column_proto(spec, col, name):
    """One complete Corinthian column (plinth, Attic base, shaft, capital) joined into a single mesh, axis at the
    origin, standing on z = 0. Returns the joined object."""
    P = spec['portico']
    plinth_w = P['plinth_w']
    plinth_h = P.get('plinth_h', 0.3)
    base_top = P['base_h']
    z_sh0, z_sh1 = P['shaft_z']
    rb, rt = P['r_bottom'], P['r_top']
    cap0, cap1 = P['capital_z']
    tor = P.get('torus_r', 0.78)
    parts = []
    # plinth
    parts.append(add_box_on(name + '_plinth', (plinth_w, plinth_w, plinth_h), (0, 0, 0), material='white_paint', collection=col))
    # Attic base: lower torus, scotia, upper torus
    zb0 = plinth_h
    H = base_top - zb0
    base_prof = [(0, zb0), (tor + 0.02, zb0), (tor + 0.05, zb0 + 0.14 * H), (tor + 0.02, zb0 + 0.30 * H),
                 (tor - 0.07, zb0 + 0.36 * H), (tor - 0.12, zb0 + 0.46 * H), (tor - 0.12, zb0 + 0.60 * H),
                 (tor - 0.07, zb0 + 0.68 * H), (tor - 0.03, zb0 + 0.80 * H), (tor - 0.03, zb0 + 0.90 * H),
                 (rb + 0.02, base_top), (0, base_top)]
    parts.append(lathe(name + '_base', base_prof, segments=56, material='white_paint', collection=col))
    # shaft with entasis: cylindrical to 1/3 height then straight taper, apophyge at the foot, astragal at the top
    z13 = z_sh0 + (z_sh1 - z_sh0) / 3.0
    shaft_prof = [(0, z_sh0), (rb + 0.06, z_sh0), (rb + 0.045, z_sh0 + 0.04), (rb + 0.015, z_sh0 + 0.14),
                  (rb, z_sh0 + 0.30), (rb, z13), (rb - (rb - rt) * 0.55, z13 + (z_sh1 - z13) * 0.55),
                  (rt, z_sh1 - 0.30), (rt + 0.02, z_sh1 - 0.22), (rt + 0.05, z_sh1 - 0.17), (rt + 0.05, z_sh1 - 0.10),
                  (rt + 0.01, z_sh1 - 0.07), (rt, z_sh1), (0, z_sh1)]
    parts.append(lathe(name + '_shaft', shaft_prof, segments=56, material='white_paint', collection=col))
    # --- capital
    ch = cap1 - cap0
    ab_h = 0.22
    bell_top = cap1 - ab_h
    bell = [(0, cap0), (rt, cap0), (rt + 0.015, cap0 + 0.04), (rt + 0.025, cap0 + 0.2 * ch), (rt + 0.04, cap0 + 0.38 * ch),
            (rt + 0.08, cap0 + 0.56 * ch), (rt + 0.14, cap0 + 0.72 * ch), (rt + 0.22, cap0 + 0.84 * ch),
            (rt + 0.265, bell_top - 0.03), (rt + 0.265, bell_top + 0.02), (0, bell_top + 0.02)]
    cparts = [lathe(name + '_bell', bell, segments=48, material='white_paint', collection=col)]
    r_at = lambda z: _interp(bell, z)
    # two rows of 8 acanthus leaves
    lower = _leaf(name + '_leafA', cap0 + 0.055 * ch, 0.37 * ch, 0.23, 0.50, r_at, col)
    upper = _leaf(name + '_leafB', cap0 + 0.32 * ch, 0.46 * ch, 0.28, 0.52, r_at, col)
    for i in range(8):
        a = math.radians(45 * i)
        if i:
            cparts.append(duplicate(lower, name + f'_leafA{i}', location=(0, 0, 0), rotation=(0, 0, a)))
        cparts.append(duplicate(upper, name + f'_leafB{i}', location=(0, 0, 0), rotation=(0, 0, a + math.radians(22.5))))
    cparts += [lower, upper]
    # volutes: 4 corner scrolls + 8 inner helices + 4 fleurons
    a_tip = P['abacus_w'] / 2 + 0.02                 # 0.87 corner tips (spec abacus 1.7)
    a_mid = a_tip - 0.20
    for i in range(4):
        th = math.radians(45 + 90 * i)
        d = Vector((math.cos(th), math.sin(th), 0))
        A = d * 0.64 + Vector((0, 0, cap0 + 0.58 * ch))
        B = d * (a_tip + 0.02) + Vector((0, 0, bell_top - 0.08))
        cparts.append(_stalk(name + f'_vst{i}', A, B, 0.075, 0.055, col))
        t = _torus(name + f'_vol{i}', 0.10, 0.045, col)
        place(t, location=B, rotation=(math.pi / 2, 0, th))
        cparts.append(t)
        thf = math.radians(90 * i)
        for sgn in (-1, 1):
            th2 = thf + sgn * math.radians(17)
            d2 = Vector((math.cos(th2), math.sin(th2), 0))
            A2 = d2 * 0.62 + Vector((0, 0, cap0 + 0.62 * ch))
            B2 = d2 * (a_mid + 0.08) + Vector((0, 0, bell_top - 0.10))
            cparts.append(_stalk(name + f'_hst{i}{sgn}', A2, B2, 0.055, 0.04, col))
            t2 = _torus(name + f'_hel{i}{sgn}', 0.065, 0.03, col, seg=10, prof=6)
            place(t2, location=B2, rotation=(math.pi / 2, 0, th2))
            cparts.append(t2)
        df = Vector((math.cos(thf), math.sin(thf), 0))
        cparts.append(add_sphere(name + f'_fleuron{i}', 0.085, center=df * (a_mid + 0.03) + Vector((0, 0, cap1 - ab_h / 2)),
                                 segments=12, rings=8, material='white_paint', collection=col))
    # abacus: two layers with concave sides
    cparts.append(extrude_polygon(name + '_abacus0', _abacus_polygon(a_tip * 0.94, a_mid * 0.94), ab_h * 0.5, bell_top,
                                  material='white_paint', collection=col))
    cparts.append(extrude_polygon(name + '_abacus1', _abacus_polygon(a_tip, a_mid), ab_h * 0.5 + 0.005, bell_top + ab_h * 0.5,
                                  material='white_paint', collection=col))
    capital = _join(cparts, name + '_capital')
    parts.append(capital)
    return _join(parts, name)


# ----------------------------------------------------------------------------- entablature helpers
def _sweep(name, profile, pts, z0, collection, material='white_paint'):
    """Open mitred sweep of a closed (offset, z) profile along the plan polyline `pts` (offset > 0 lies to the
    RIGHT of the direction of travel), with flat end caps. Same construction as body's flank entablature, so the
    portico returns meet it without a step."""
    bm = bmesh.new()
    P = [Vector((p[0], p[1])) for p in pts]
    n = len(P)
    rings = []
    for i in range(n):
        p = P[i]
        d0 = (p - P[i - 1]).normalized() if i > 0 else None
        d1 = (P[i + 1] - p).normalized() if i < n - 1 else None
        if d0 is None:
            d0 = d1
        if d1 is None:
            d1 = d0
        n0 = Vector((d0.y, -d0.x))
        n1 = Vector((d1.y, -d1.x))
        m = n0 + n1
        if m.length < 1e-6:
            m = n0.copy()
        else:
            m.normalize()
            m /= m.dot(n0)
        rings.append([bm.verts.new((p.x + m.x * o, p.y + m.y * o, z0 + z)) for o, z in profile])
    k = len(profile)
    for i in range(n - 1):
        a, b = rings[i], rings[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            bm.faces.new((a[j], a[jj], b[jj], b[j]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _mesh_ob(name, bm, material, collection)


def _entablature_profile(E):
    """(offset from the WALL plane, z above z_bottom) outline of the portico entablature. The cornice part is the
    SAME outline body uses for the arm/core entablature (architrave face 0.2, frieze 0.21, dentil band 0.5->0.76
    at z 1.6-1.9, corona 1.1, top 1.17 = projection 0.96 beyond the frieze face), so the two 3 m returns run
    seamlessly into body's flank cornice at the end-wall corners. The portico architrave has three fascias."""
    ah, fh = E['architrave_h'], E['frieze_h']
    top = ah + fh + E['cornice_h']
    ft = ah + fh - 0.02                                    # frieze top (bed mould starts)
    prof = [(-0.3, 0.0), (0.10, 0.0), (0.10, 0.32 * ah), (0.15, 0.32 * ah), (0.15, 0.64 * ah), (0.20, 0.64 * ah),
            (0.20, ah - 0.05), (0.27, ah - 0.05), (0.27, ah + 0.03), (0.21, ah + 0.03),
            (0.21, ft), (0.30, ft + 0.02), (0.42, ft + 0.12), (0.50, ft + 0.20), (0.50, ft + 0.54), (0.72, ft + 0.57),
            (0.80, ft + 0.72), (1.00, ft + 0.87), (1.10, ft + 1.04), (1.10, ft + 1.20), (1.17, ft + 1.20),
            (1.17, top), (-0.3, top)]
    return prof, ft


# ----------------------------------------------------------------------------- one portico (local frame)
def _build_local(spec, col, pfx):
    """Build one portico in the local frame (column line y=0, wall y=+depth, outward -y). Returns objects."""
    P = spec['portico']
    E = P['entablature']
    PD = P['pediment']
    AC = P['acroteria_pedestals']
    AN = P['anta']
    depth = P['depth']                     # 3.0: column line -> arm end wall
    arm_hw = spec['arms']['common']['half_w']
    pil = spec['arms']['common']['pilasters']
    objs = []

    # ---- stylobate (spec: height 0 -> nothing). Kept data-driven in case the spec changes.
    sty_h = P.get('stylobate', {}).get('height', 0.0)
    if sty_h > 0:
        objs.append(add_box_on(pfx + 'stylobate', (2 * E['half_w'], depth + 1.6, sty_h), (0, depth / 2 - 0.8, 0),
                               material='granite', collection=col))

    # ---- columns
    proto = _column_proto(spec, col, pfx + 'col_1')
    offs = P['column_offsets']
    proto.location = (offs[0], 0, sty_h)
    objs.append(proto)
    for i, x in enumerate(offs[1:], start=2):
        objs.append(duplicate(proto, pfx + f'col_{i}', location=(x, 0, sty_h), rotation=(0, 0, 0)))

    # ---- entablature: open mitred sweep (front + two 3 m returns, nothing inside the arm) around the WALL plane
    # rectangle x = +-arm_hw (11.0), y_front: the frieze face (offset 0.21) ends up E.front_face_offset (0.9) in front
    # of the column line and the cornice edge at arm_hw + 1.17 = 12.17 = body's flank cornice edge.
    z0 = E['z_bottom']
    prof, ft = _entablature_profile(E)
    top = E['z_top'] - z0
    y_front = -(E['front_face_offset_from_column_line'] - 0.21)          # -0.69 : wall-plane line of the front
    pts = [(-arm_hw, depth), (-arm_hw, y_front), (arm_hw, y_front), (arm_hw, depth)]
    objs.append(_sweep(pfx + 'entablature', prof, pts, z0, col))
    # solid core (flat soffit at z0) filling the inside of the sweep, 0.05 into the end wall
    objs.append(add_box(pfx + 'ent_core', (2 * (arm_hw - 0.3), depth + 0.05 - (y_front + 0.3), top),
                        (0, (depth + 0.05 + y_front + 0.3) / 2, z0 + top / 2), material='white_paint', collection=col))
    y_frieze = y_front - 0.21                                              # -0.90
    y_edge = y_front - 1.17                                                # -1.86 cornice edge
    # dentils: band z ft+0.20 .. ft+0.54 behind offset 0.5 (same band as body's flank dentils)
    d_w, d_d, d_h = 0.18, 0.26, 0.30
    d_off = 0.50 + d_d / 2
    dz = z0 + ft + 0.37
    dent = add_box(pfx + 'dentil', (d_w, d_d, d_h), (0, 0, 0), material='white_paint', collection=col)
    dents = [dent]
    xo = arm_hw + d_off
    yo = y_front - d_off
    n = int(round((2 * xo) / 0.33))
    pitch = 2 * xo / n
    dent.location = (-xo, yo, dz)
    for i in range(1, n + 1):
        dents.append(duplicate(dent, pfx + f'dentil_f{i}', location=(-xo + i * pitch, yo, dz)))
    ny = int((depth - 0.10 - yo) / pitch)
    for s in (-1, 1):
        for i in range(1, ny + 1):
            dents.append(duplicate(dent, pfx + f'dentil_r{s}{i}', location=(s * xo, yo + i * pitch, dz), rotation=(0, 0, math.pi / 2)))
    objs.append(_join(dents, pfx + 'dentils'))
    # modillions: blocks under the corona, protruding from the sloped bed (offsets 0.60 -> 1.04, z ft+0.70 .. ft+1.00)
    m_w, m_d, m_h = 0.28, 0.44, 0.30
    m_off = 0.60 + m_d / 2
    mz = z0 + ft + 0.85
    mod = add_box(pfx + 'modillion', (m_w, m_d, m_h), (0, 0, 0), material='white_paint', collection=col)
    mods = [mod]
    xm = arm_hw + m_off
    ym = y_front - m_off
    nm = int(round((2 * xm) / 0.80))
    if nm % 2:
        nm += 1
    pm = 2 * xm / nm
    mod.location = (-xm, ym, mz)
    for i in range(1, nm + 1):
        mods.append(duplicate(mod, pfx + f'mod_f{i}', location=(-xm + i * pm, ym, mz)))
    nmy = int((depth - 0.15 - ym) / pm)
    for s in (-1, 1):
        for i in range(1, nmy + 1):
            mods.append(duplicate(mod, pfx + f'mod_r{s}{i}', location=(s * xm, ym + i * pm, mz), rotation=(0, 0, math.pi / 2)))
    objs.append(_join(mods, pfx + 'modillions'))

    # ---- pediment
    rake = math.radians(PD['rake_deg'])
    slope = math.tan(rake)
    apex_top = PD['apex_z']                               # 18.4 = top of the raking cornice at the axis
    rc_h = apex_top - PD['tympanum_apex_z']               # 0.75 vertical height of the raking cornice
    z_apex_base = PD['tympanum_apex_z']                   # 17.65 = tympanum apex under the cornice soffit
    y_t = y_frieze + PD['tympanum_setback']               # tympanum face (-0.40)
    x_stop = PD.get('raking_cornice_x_end', 10.75)        # 10.75: raking cornice ends (independent of the pedestals)
    # tympanum (wall tone) solid from its face back 0.1 into the arm end wall; clipped to |x| <= arm_hw - 0.1
    # (everything below the cornice top 14.2 is hidden inside the entablature anyway)
    xt = arm_hw - 0.1
    z_bl = z_apex_base - slope * xt
    tri = [(-xt, z0 + top - 0.9), (xt, z0 + top - 0.9), (xt, z_bl), (0, z_apex_base), (-xt, z_bl)]
    tymp = prism(pfx + 'tympanum', tri, depth + 0.1 - y_t, material='wall', collection=col)
    place(tymp, location=(0, depth + 0.1, 0), rotation=(0, 0, -math.pi / 2))
    objs.append(tymp)
    # raking cornice: the horizontal cornice's outline (bed mould, dentil band, sloped modillion bed, corona, cyma)
    # starting at the tympanum face, scaled to rc_h; profile = (y, vertical offset above the rake base line)
    k = rc_h / 1.32
    rprof = [(y_t + 0.7, 0.0), (y_t, 0.0), (y_t - 0.09, 0.02 * k), (y_t - 0.21, 0.12 * k), (y_t - 0.29, 0.20 * k),
             (y_t - 0.29, 0.54 * k), (y_t - 0.51, 0.57 * k), (y_t - 0.59, 0.72 * k), (y_t - 0.79, 0.87 * k),
             (y_t - 0.89, 1.04 * k), (y_t - 0.89, 1.20 * k), (y_t - 0.96, 1.20 * k), (y_t - 0.96, rc_h), (y_t + 0.7, rc_h)]
    objs.append(_gable_moulding(pfx + 'raking_cornice', rprof, x_stop, z_apex_base, slope, col))
    # raking dentils + modillions (tilted boxes along both slopes, mirrored about the axis)
    def _raking_row(key, size, y_c, dz_c, pitch_h, x_first):
        bx = add_box(pfx + key, size, (0, 0, 0), material='white_paint', collection=col)
        row = [bx]
        px = pitch_h * math.cos(rake)
        nrow = int((x_stop - 0.3 - x_first) / px)
        bx.location = (x_first, y_c, z_apex_base - slope * x_first + dz_c)
        bx.rotation_euler = (0, rake, 0)
        for s in (-1, 1):
            for i in range(nrow + 1):
                if s == 1 and i == 0:
                    continue
                x = s * (x_first + i * px)
                row.append(duplicate(bx, pfx + f'{key}{s}{i}', location=(x, y_c, z_apex_base - slope * abs(x) + dz_c),
                                     rotation=(0, s * rake, 0)))
        return _join(row, pfx + key + 's')
    objs.append(_raking_row('rdentil', (d_w, 0.26, 0.34 * k), y_t - 0.29 - 0.13, 0.37 * k, 0.33, 0.25))
    objs.append(_raking_row('rmodillion', (m_w, 0.34, 0.26 * k), y_t - 0.51 - 0.17, 0.72 * k, 0.80, 0.45))
    # dark roof: (a) thin cap on top of the raking cornice back to the end wall, (b) a dark block behind the
    # raking cornice up to the arm roof eaves, so the arm end wall / parapet never shows above the pediment and the
    # dark roof reads above the corners as in the photo (the arm gable roof itself belongs to body)
    cap = [(y_t - 0.96 - 0.06, rc_h - 0.01), (depth, rc_h - 0.01), (depth, rc_h + 0.05), (y_t - 0.96 - 0.06, rc_h + 0.05)]
    objs.append(_gable_moulding(pfx + 'roof_cap', cap, x_stop, z_apex_base, slope, col, material='roof_dark'))
    # Fixer r1: the block used to rise to 16.52 (parapet top) at the sides, 1.2-1.9 m of dark roof above the raking
    # cornice at the corners where the photo shows ~0.3-0.5 m and the LIT parapet end behind each corner statue.
    # Now its top follows the rake: cornice top at the corner + 0.45 at |x| = blk_hw, apex_z - 0.1 (18.3) at the axis
    # (pitch ~16.7 deg, the dark wedge grows from 0 at the apex to ~0.4 m at the corner pedestals); body's parapet
    # band (14.2-16.5) shows above it for |x| > ~6.7 as in the photo.
    blk_hw = arm_hw + pil['projection'] - 0.01                 # 1 cm inside body's flank parapet face
    z_eave = apex_top - slope * blk_hw + 0.45                  # 14.93: raking cornice top at the corner + 0.45
    z_ridge = PD['apex_z'] - 0.1                               # 18.3 (= arm roof ridge), below the roof cap at the apex
    y_blk0 = y_t + 0.8
    zb = z0 + top - 0.3
    blk = prism(pfx + 'roof_block', [(-blk_hw, zb), (blk_hw, zb), (blk_hw, z_eave), (0, z_ridge), (-blk_hw, z_eave)],
                depth + 0.02 - y_blk0, material='roof_dark', collection=col)
    place(blk, location=(0, y_blk0, 0), rotation=(0, 0, math.pi / 2))
    objs.append(blk)

    # ---- acroteria pedestals (statue feet at z_top = top of the 0.08 cap; bottoms sunk 0.02 into the cornice top / roof)
    ap = AC['apex']
    objs.append(add_box_on(pfx + 'ped_apex', (ap['size'], ap['size'], ap['z_top'] - 0.08 - ap['z_base'] + 0.02), (ap['offset_along_facade'], 0, ap['z_base'] - 0.02),
                           material='white_paint', collection=col))
    objs.append(add_box_on(pfx + 'ped_apex_cap', (ap['size'] + 0.12, ap['size'] + 0.12, 0.08), (ap['offset_along_facade'], 0, ap['z_top'] - 0.08),
                           material='white_paint', collection=col))
    # corner pedestals: directly above the end columns (offset 9.6), centred `setback` behind the column line so the
    # raking cornice hides their lower part; their top (15.7) shows ~0.3 m above the cornice line (photo)
    cp = AC['corners']
    y_cp = cp.get('setback_from_column_line', 0.9)
    for s, nm_ in ((-1, 'w'), (1, 'e')):
        x = s * cp['offset_along_facade']
        objs.append(add_box_on(pfx + f'ped_{nm_}', (cp['size'], cp['size'], cp['z_top'] - 0.08 - cp['z_base'] + 0.02), (x, y_cp, cp['z_base'] - 0.02),
                               material='white_paint', collection=col))
        objs.append(add_box_on(pfx + f'ped_{nm_}_cap', (cp['size'] + 0.12, cp['size'] + 0.12, 0.08), (x, y_cp, cp['z_top'] - 0.08),
                               material='white_paint', collection=col))

    # ---- antae: L-shaped corner pilasters at the arm end-wall corners. Flank face AN.width (1.3) wide along the
    # flank (body leaves that bay free), end-wall face from the responding pilaster's edge (column offset - 0.5)
    # to the corner, projection AN.projection (0.3, so it swallows body's 0.2 responding pilaster); same stacked
    # base/capital as body's pilasters (base 0.6, bell 9.7-10.4, bell 10.4-11.05, abacus 11.05-11.5).
    aw, apj = AN['width'], AN['projection']
    cap0, cap1 = pil['capital_z']
    bh = pil['base_h']
    x_in = abs(offs[-1]) - pil['width'] / 2 - 0.01             # 9.59 inner edge of the end-wall face
    stack = [('base', 0.10, 0.08, 0.0, bh), ('shaft', 0.0, 0.0, bh, cap0), ('bell1', 0.05, 0.08, cap0, cap0 + 0.7),
             ('bell2', 0.12, 0.16, cap0 + 0.7, cap1 - 0.45), ('ab', 0.18, 0.22, cap1 - 0.45, cap1)]
    for s, nm_ in ((-1, 'w'), (1, 'e')):
        parts = []
        for key, dw, dp, za, zb in stack:
            pr = apj + dp
            # end-wall face: x from x_in-dw to arm_hw+pr, y from depth-pr to depth+0.05
            xa, xb = x_in - dw, arm_hw + pr
            parts.append(add_box(pfx + f'anta_{nm_}_{key}_f', ((xb - xa), pr + 0.05, zb - za),
                                 (s * (xa + xb) / 2, depth - pr / 2 + 0.025, (za + zb) / 2), material='white_paint', collection=col))
            # flank face: x from arm_hw-0.05 to arm_hw+pr, y from depth+0.05 (= the back of the end-wall box, so the
            # two boxes touch instead of overlapping: overlapping coplanar faces render black in Cycles) to depth+aw+dw
            ya, yb = depth + 0.05, depth + aw + dw
            parts.append(add_box(pfx + f'anta_{nm_}_{key}_s', (pr + 0.05, yb - ya, zb - za),
                                 (s * (arm_hw + pr / 2 - 0.025), (ya + yb) / 2, (za + zb) / 2), material='white_paint', collection=col))
        objs.append(_join(parts, pfx + f'anta_{nm_}'))
    return objs


def _instance_matrix(inst):
    """World transform of a portico instance from its column-line point and facing."""
    axis = inst['axis']
    cl = inst['column_line']
    if axis in ('-Y', '+Y'):
        t = Vector((0, cl, 0))
    else:
        t = Vector((cl, 0, 0))
    theta = math.radians(180.0 - inst['facing_deg'])
    return Matrix.Translation(t) @ Matrix.Rotation(theta, 4, 'Z')


def portico(spec, arm_name, col, proto=None):
    """Build (or instance) the portico of arm `arm_name` ('S','N','E','W' or 'south'...).
    proto: (objects, local_matrices) of an already built portico -> linked duplicates.
    Returns (objects, (objects, local_matrices))."""
    key = arm_name[0].upper()
    inst = next(i for i in spec['portico']['instances'] if i['name'] == key)
    M = _instance_matrix(inst)
    pfx = f'{PFX}_{key}_'
    if proto is None:
        objs = _build_local(spec, col, pfx)
        bpy.context.view_layer.update()          # matrix_world is stale until the depsgraph runs
        locals_ = [o.matrix_world.copy() for o in objs]
        for o, L in zip(objs, locals_):
            o.matrix_world = M @ L
        return objs, (objs, locals_)
    src_objs, locals_ = proto
    out = []
    for o, L in zip(src_objs, locals_):
        nm = pfx + o.name.split('_', 2)[2]
        new = duplicate(o, nm, collection=col)
        new.matrix_world = M @ L
        out.append(new)
    return out, proto


def build(spec, col):
    """Module contract: build the four porticos inside collection `col`, return the objects."""
    allobjs = []
    proto = None
    order = ['S', 'N', 'E', 'W']
    names = [i['name'] for i in spec['portico']['instances']]
    for key in order:
        if key not in names:
            continue
        objs, proto = portico(spec, key, col, proto)
        allobjs += objs
    return allobjs


# ----------------------------------------------------------------------------- standalone test
if __name__ == '__main__':
    spec = load_spec()
    # use the spec palette for the previews (mod_look owns this in the final scene)
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
    print(f'[portico] built {len(objs)} objects in {time.time() - t0:.1f}s; scene (objects, polys) = {count_scene()}')
    # context massing only for the previews (NOT part of build): podium, arms, core, ground
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
    # simple stairs ramp so the photo view is not a cliff
    st = spec['stairs']
    ramp = prism('ctx_stairs', [(st['top_y'], st['top_z']), (st['bottom_y'], st['bottom_z']), (st['top_y'], st['bottom_z'])], 2 * st['half_w'],
                 material='granite', collection=ctx)
    place(ramp, location=(-st['half_w'], 0, 0))
    setup_sun_sky(**spec['sun'])
    cam = spec['camera']
    res = tuple(cam.get('preview_resolution', [480, 640]))
    # (1) photo viewpoint
    setup_camera(cam['location'], cam['target'], lens=cam['lens'], shift_y=cam.get('shift_y', 0.0))
    p1 = render(os.path.join(PREVIEWS, 'mod_portico_1.png'), res=res, samples=32)
    compare_with_photo(p1)
    # (2) close-up: SW capital of the south portico + entablature corner, ~15 m
    off = spec['portico']['column_offsets'][0]
    cl = spec['portico']['instances'][0]['column_line']
    setup_camera((off - 7.5, cl - 12.0, 8.0), (off - 0.6, cl - 0.4, 12.4), lens=50)
    render(os.path.join(PREVIEWS, 'mod_portico_2.png'), res=res, samples=32)
    # (3) whole south portico front-on from 60 m at eye level (on the square)
    setup_camera((0, cl - 60.0, spec['square_ground_z'] + 1.6), (0, cl, 9.5), lens=40)
    render(os.path.join(PREVIEWS, 'mod_portico_3.png'), res=res, samples=32)
    # (4) capital + cornice corner from below at ~7 m (debug)
    setup_camera((off - 4.0, cl - 6.0, 8.5), (off - 1.2, cl - 0.8, 12.0), lens=40)
    render(os.path.join(PREVIEWS, 'mod_portico_4.png'), res=res, samples=32)
    print('[portico] final count (objects, polys):', count_scene())
