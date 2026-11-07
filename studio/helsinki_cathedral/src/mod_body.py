"""mod_body.py - Helsinki Cathedral masonry: podium, Greek-cross arms, corner blocks, core attic.
Module contract: build(spec, col) -> list of objects. Only local import: common.
Coordinate contract: metres, +X east, +Y north, z=0 podium top, south facade faces -Y.

All facade elements (pilasters, windows, panels, doors, dentils, balusters) are built ONCE as
prototypes in a local "face frame" (wall plane y=0, outward = -Y, along-face = +X) and then
placed with linked duplicates on every face. Window reveals / sunk panels are cut into the
wall solids with ONE boolean per wall object (cutters joined into a single mesh).
"""
from common import *

MATERIAL_SPECS['louvre'] = {'Base Color': (0.30, 0.31, 0.33, 1), 'Roughness': 0.7}
MATERIAL_SPECS.setdefault('vent_dark', {'Base Color': (0.02, 0.02, 0.022, 1), 'Roughness': 0.9})   # unglazed vent slits

# Photo-derived constants (polish round; measured on ref/photo.jpg through the spec camera projection,
# fit checked against the spec's own anchors: abacus top y 1471 vs 1468, apex y 1268 vs 1272).
SLIT = {'w': 0.24, 'h': 0.38, 'z0': 4.75}        # tiny unglazed ventilation slit (photo 0.22 x 0.35, z 4.75-5.10)
SLIT_END_WALL_X = 8.6                             # end walls: in the outer bays, 0.45 from the bay centre toward the anta
SLIT_CB_OFFSET = 0.6                              # corner-block bay: 0.6 from the bay centre toward the re-entrant corner
RE_ENTRANT_DZ = -0.03                             # capital tiers of the flank pilaster at each re-entrant corner (no coplanar faces)
RELIEF_BORDER, RELIEF_RAISE, RELIEF_FIELD = 0.10, 0.06, 0.03
RELIEF_BLOBS = [(-0.36, 0.08), (-0.14, -0.14), (0.06, 0.12), (0.26, -0.06), (0.40, 0.10)]   # fractions of (w, h)
# Door surround as photographed (crop_door_base / grid overlay): jambs 0.22 wide, a plain 0.55 head band with a thin
# cap moulding, a projecting hood at z 5.85-6.2 (spec hood_z 4.6-5.1 and frame_w 2.75 disagree with the photo by
# 1.1 m / 0.65 m) carried by two thin consoles. The opening itself (spec: 1.65 x 4.5 from sill 0.2, leaves 3.05) matches.
DOOR_SURROUND = {'jamb_w': 0.22, 'head_h': 0.55, 'cap_h': 0.08, 'cap_proj': 0.16, 'hood_z': (5.85, 6.2),
                 'hood_half_w': 1.35, 'hood_proj': 0.36, 'console_w': 0.12, 'console_x': 1.2, 'console_proj': 0.28}

# ----------------------------------------------------------------------------- low level helpers
def _mk(name, bm, material, col):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    if material:
        me.materials.append(mat(material))
    return ob


def sweep(name, profile, pts, closed, z0, material, col):
    """Sweep a closed (offset, z) profile along a plan polyline with mitred corners.
    pts CCW around the solid -> offset > 0 is OUTWARD (right of travel). Open polylines get end caps."""
    bm = bmesh.new()
    P = [Vector((p[0], p[1])) for p in pts]
    n = len(P)
    rings = []
    for i in range(n):
        p = P[i]
        d0 = (p - P[i - 1]).normalized() if (closed or i > 0) else None
        d1 = (P[(i + 1) % n] - p).normalized() if (closed or i < n - 1) else None
        if d0 is None: d0 = d1
        if d1 is None: d1 = d0
        n0 = Vector((d0.y, -d0.x)); n1 = Vector((d1.y, -d1.x))
        m = n0 + n1
        if m.length < 1e-6:
            m = n0.copy()
        else:
            m.normalize(); m /= m.dot(n0)
        rings.append([bm.verts.new((p.x + m.x * o, p.y + m.y * o, z0 + z)) for o, z in profile])
    k = len(profile)
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for j in range(k):
            jj = (j + 1) % k
            bm.faces.new((a[j], a[jj], b[jj], b[j]))
    if not closed:
        bm.faces.new(rings[0]); bm.faces.new(list(reversed(rings[-1])))
    return _mk(name, bm, material, col)


def xz_solid(name, pts, out0, out1, material, col):
    """Polygon (x,z) in the face frame extruded from out0 to out1 (out>0 = in front of the wall = -Y)."""
    bm = bmesh.new()
    v0 = [bm.verts.new((x, -out1, z)) for x, z in pts]
    v1 = [bm.verts.new((x, -out0, z)) for x, z in pts]
    bm.faces.new(v0); bm.faces.new(list(reversed(v1)))
    n = len(pts)
    for j in range(n):
        k = (j + 1) % n
        bm.faces.new((v0[j], v0[k], v1[k], v1[j]))
    return _mk(name, bm, material, col)


def xz_ring(name, outer, inner, out0, out1, material, col):
    """Band between two matched (x,z) outlines, extruded along the face normal (frames, arch mouldings)."""
    bm = bmesh.new()
    n = len(outer)
    O0 = [bm.verts.new((x, -out1, z)) for x, z in outer]; I0 = [bm.verts.new((x, -out1, z)) for x, z in inner]
    O1 = [bm.verts.new((x, -out0, z)) for x, z in outer]; I1 = [bm.verts.new((x, -out0, z)) for x, z in inner]
    for j in range(n):
        k = (j + 1) % n
        bm.faces.new((O0[j], O0[k], I0[k], I0[j]))
        bm.faces.new((O1[k], O1[j], I1[j], I1[k]))
        bm.faces.new((O0[j], O1[j], O1[k], O0[k]))
        bm.faces.new((I0[k], I1[k], I1[j], I0[j]))
    return _mk(name, bm, material, col)


def arch_pts(w, z0, z1, seg=14):
    r = w / 2.0; zs = z1 - r
    return [(-r, z0), (r, z0)] + [(r * math.cos(math.pi * i / seg), zs + r * math.sin(math.pi * i / seg)) for i in range(seg + 1)]


def ell_pts(w, z0, z1, seg=18):
    a = w / 2.0; b = z1 - z0
    return [(a * math.cos(math.pi * i / seg), z0 + b * math.sin(math.pi * i / seg)) for i in range(seg + 1)]


def fb(name, x0, x1, z0, z1, out0, out1, material, col):
    """Box in the face frame: x range along the face, z range, out range (out>0 proud of the wall)."""
    return add_box(name, (x1 - x0, out1 - out0, z1 - z0), ((x0 + x1) / 2, -(out0 + out1) / 2, (z0 + z1) / 2),
                   material=material, collection=col)


class Face:
    """A straight wall face from p0 to p1 (plan, CCW around the building so the outside is on the right)."""
    def __init__(self, p0, p1):
        self.p0 = Vector((p0[0], p0[1])); self.p1 = Vector((p1[0], p1[1]))
        d = self.p1 - self.p0
        self.L = d.length; self.d = d / self.L
        self.n = Vector((self.d.y, -self.d.x))
        self.rot = math.atan2(self.d.y, self.d.x)

    def pos(self, u, z=0.0, out=0.0):
        p = self.p0 + self.d * u + self.n * out
        return (p.x, p.y, z)

    def box(self, name, u0, u1, z0, z1, out0, out1, material, col):
        c = self.pos((u0 + u1) / 2, (z0 + z1) / 2, (out0 + out1) / 2)
        return add_box(name, (u1 - u0, out1 - out0, z1 - z0), c, material=material, collection=col,
                       rotation=(0, 0, self.rot))


class Kit:
    """Prototype library + linked-duplicate placer. Cutters are collected per target wall."""
    def __init__(self, col):
        self.col = col; self.protos = {}; self.objs = []; self.cut = {}; self.n = 0

    def add(self, key, ob, cutter=None):
        self.protos[key] = (ob, cutter)

    def put(self, key, face, u, z=0.0, out=0.0, target='main', rot=None):
        ob, cut = self.protos[key]
        self.n += 1
        loc = face.pos(u, z, out)
        r = (0, 0, face.rot if rot is None else rot)
        d = None
        if ob is not None:
            d = duplicate(ob, 'body_%s_%03d' % (key, self.n), location=loc, rotation=r, collection=self.col)
            self.objs.append(d)
        if cut is not None:
            c = duplicate(cut, 'body_%s_cut_%03d' % (key, self.n), location=loc, rotation=r, collection=self.col)
            self.cut.setdefault(target, []).append(c)
        return d

    def finish(self):
        for ob, cut in self.protos.values():
            if ob is not None: bpy.data.objects.remove(ob, do_unlink=True)
            if cut is not None: bpy.data.objects.remove(cut, do_unlink=True)
        self.protos = {}


# ----------------------------------------------------------------------------- prototypes
def make_protos(spec, kit, col):
    A = spec['arms']['common']; W = 'white_paint'
    pil = A['pilasters']; pw, pp = pil['width'], pil['projection']
    cz0, cz1 = pil['capital_z']
    # --- pilaster = base + shaft + Corinthian-ish capital (astragal, bell, two staggered leaf rows, corner volutes,
    #     two-step abacus). mk(name, x0, x1, z0, z1, out0, out1) makes one box in the frame of the face in question.
    def pilaster(key, x0, x1, mk, dz=0.0):
        # dz shifts every internal tier boundary (base top, neck, leaves, volutes, abaci) but not the foot (0) nor the
        # top (cz1, which meets the entablature soffit): the 'pil_re' variant used at the re-entrant corners has no
        # horizontal face coplanar with the neighbouring corner-block pilaster (polish: z-fighting lines)
        c0, c1 = cz0 + dz, cz1 + dz
        parts = [mk(key + '_base', x0 - 0.1, x1 + 0.1, 0, pil['base_h'] + dz, 0, pp + 0.08),
                 mk(key + '_shaft', x0, x1, pil['base_h'] + dz, c0, 0, pp),
                 mk(key + '_neck', x0 - 0.04, x1 + 0.04, c0, c0 + 0.1, 0, pp + 0.06),
                 mk(key + '_bell', x0 - 0.02, x1 + 0.02, c0 + 0.1, c1 - 0.28, 0, pp + 0.05)]
        w = x1 - x0
        n1 = max(2, int(round(w / 0.26)))
        for i in range(n1):
            x = x0 + 0.12 + (w - 0.24) * i / (n1 - 1)
            parts.append(mk(key + '_l1%d' % i, x - 0.1, x + 0.1, c0 + 0.1, c0 + 0.72, pp + 0.05, pp + 0.17))
        for i in range(n1 - 1):
            x = x0 + 0.12 + (w - 0.24) * (i + 0.5) / (n1 - 1)
            parts.append(mk(key + '_l2%d' % i, x - 0.1, x + 0.1, c0 + 0.6, c0 + 1.22, pp + 0.05, pp + 0.21))
        for k, x in enumerate((x0 - 0.02, x1 + 0.02)):
            parts.append(mk(key + '_v%d' % k, x - 0.11, x + 0.11, c1 - 0.62, c1 - 0.26, pp + 0.05, pp + 0.3))
        parts.append(mk(key + '_ab1', x0 - 0.14, x1 + 0.14, c1 - 0.26, c1 - 0.1, 0, pp + 0.3))
        parts.append(mk(key + '_ab2', x0 - 0.2, x1 + 0.2, c1 - 0.1, cz1, 0, pp + 0.36))
        return parts
    mk_plain = lambda n, x0, x1, z0, z1, o0, o1: fb(n, x0, x1, z0, z1, o0, o1, W, col)
    kit.add('pil', join(pilaster('p', -pw / 2, pw / 2, mk_plain), 'proto_pil'))
    kit.add('pil_re', join(pilaster('pr', -pw / 2, pw / 2, mk_plain, dz=RE_ENTRANT_DZ), 'proto_pil_re'))
    # --- convex corner pilaster (1.3 w on both faces; local: face A along +x outward -y, face B along +y outward -x);
    #     the slabs of both faces run through to the corner so it is wrapped without a gap
    cw = 1.3
    def mk_a(name, x0, x1, z0, z1, out0, out1):          # face A keeps x >= 0 ...
        return fb(name, max(x0, 0.0), x1, z0, z1, out0, out1, W, col)
    def mk_b(name, y0, y1, z0, z1, out0, out1):          # ... face B supplies the corner block (no doubled faces)
        if y0 < 0:
            y0, out0 = -out1, 0.0
        return add_box(name, (out1 - out0, y1 - y0, z1 - z0), (-(out0 + out1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), material=W, collection=col)
    kit.add('cpil', join(pilaster('cpa', 0, cw, mk_a) + pilaster('cpb', 0, cw, mk_b), 'proto_cpil'))
    # --- attic pilaster (16.5 -> 24.6, simple cap)
    at = spec['core']['attic']; az0, az1 = at['z_base'], at['wall_top_z']
    parts = [fb('ap_base', -0.6, 0.6, az0, az0 + 0.5, 0, 0.28, W, col),
             fb('ap_shaft', -0.5, 0.5, az0 + 0.5, az1 - 0.85, 0, 0.2, W, col),
             fb('ap_cap', -0.58, 0.58, az1 - 0.85, az1 - 0.4, 0, 0.28, W, col),
             fb('ap_abacus', -0.65, 0.65, az1 - 0.4, az1, 0, 0.34, W, col)]
    kit.add('apil', join(parts, 'proto_apil'))

    # --- windows: recessed dark glass + white mullions + white frame; cutter makes the reveal
    def window(key, w, h, z0, fw, panes, sill=True, head=True):
        hw = w / 2; depth = 0.3
        cut = fb(key + '_cut', -hw, hw, z0, z0 + h, -depth, 0.12, None, col)
        parts = [fb(key + '_glass', -hw + 0.01, hw - 0.01, z0 + 0.01, z0 + h - 0.01, -depth, -depth + 0.06, 'glass', col)]
        nx, nz = panes
        for i in range(1, nx):
            x = -hw + w * i / nx
            parts.append(fb(key + '_mv', x - 0.03, x + 0.03, z0, z0 + h, -depth + 0.06, -depth + 0.12, W, col))
        for i in range(1, nz):
            z = z0 + h * i / nz
            # horizontals 1 cm behind the verticals: no coincident front faces at the crossings (fixer r2)
            parts.append(fb(key + '_mh', -hw, hw, z - 0.03, z + 0.03, -depth + 0.05, -depth + 0.11, W, col))
        # one mitred frame ring instead of four overlapping boxes (coincident fw x fw corner faces z-fought, fixer r2)
        parts.append(xz_ring(key + '_frame',
                             [(-hw - fw, z0 - fw), (hw + fw, z0 - fw), (hw + fw, z0 + h + fw), (-hw - fw, z0 + h + fw)],
                             [(-hw, z0), (hw, z0), (hw, z0 + h), (-hw, z0 + h)], 0, 0.08, W, col))
        if sill:
            parts.append(fb(key + '_sill', -hw - fw - 0.1, hw + fw + 0.1, z0 - fw - 0.12, z0 - fw, 0, 0.16, W, col))
        if head:
            parts.append(fb(key + '_head', -hw - fw - 0.12, hw + fw + 0.12, z0 + h + fw, z0 + h + fw + 0.18, 0, 0.2, W, col))
        kit.add(key, join(parts, 'proto_' + key), cut)
    wl, wu = A['windows_lower'], A['windows_upper']
    window('wtall', wl['width'], wl['height'], wl['z_bottom'], wl['frame_w'], wl['panes'])
    window('wup', wu['width'], wu['height'], wu['z_bottom'], wu['frame_w'], wu['panes'], head=False)
    # --- 'wsmall' = tiny unglazed ventilation slit (photo: a dark 0.22 x 0.35 hole at z 4.75-5.10, no frame, no glazing);
    #     the boolean reveal (wall material) gives the lit east jamb seen in the photo, a matte black slab closes the back
    sw, sh, sz0 = SLIT['w'], SLIT['h'], SLIT['z0']
    cut = fb('wsmall_cut', -sw / 2, sw / 2, sz0, sz0 + sh, -0.3, 0.12, None, col)
    kit.add('wsmall', fb('wsmall_dark', -sw / 2 + 0.01, sw / 2 - 0.01, sz0 + 0.01, sz0 + sh - 0.01, -0.3, -0.24, 'vent_dark', col), cut)
    # --- relief panels: flat figurative reliefs in the photo = a slightly lighter rectangle with a plain border.
    #     Raised 0.06 slab with a 0.10 border, the inner field recessed to 0.03, and a few low squashed blobs
    #     (fixed positions) suggesting the figures. No fins (the old 5 x 0.24 bars read as louvred grilles).
    rp = A['relief_panels']; rz0, rh = rp['z_bottom'], rp['height']; bd = RELIEF_BORDER
    for key, w in (('relief', rp['width']), ('relief_wide', 3.2)):
        outer = [(-w / 2, rz0), (w / 2, rz0), (w / 2, rz0 + rh), (-w / 2, rz0 + rh)]
        inner = [(-w / 2 + bd, rz0 + bd), (w / 2 - bd, rz0 + bd), (w / 2 - bd, rz0 + rh - bd), (-w / 2 + bd, rz0 + rh - bd)]
        parts = [xz_ring(key + '_border', outer, inner, 0, RELIEF_RAISE, W, col),
                 # field overlaps the border ring by 1 cm so its side faces are buried (no coincident planes)
                 fb(key + '_field', -w / 2 + bd - 0.01, w / 2 - bd + 0.01, rz0 + bd - 0.01, rz0 + rh - bd + 0.01, 0, RELIEF_FIELD, W, col)]
        for k, (fx, fz) in enumerate(RELIEF_BLOBS[:5 if w > 3 else 4]):
            b = add_sphere(key + '_f%d' % k, 0.12, (0, 0, 0), segments=12, rings=6, material=W, collection=col)
            # squashed: 0.12 along the face, 0.04 proud of the field (0.03 + 0.042 = just above the 0.06 border), 0.10 tall
            place(b, location=(fx * w, -RELIEF_FIELD, rz0 + rh / 2 + fz * rh), scale=(1.0, 0.5, 0.8))
            parts.append(b)
        kit.add(key, join(parts, 'proto_' + key))
    # --- sunk panel (cutter only)
    kit.add('sunk', None, fb('sunk_cut', -0.95, 0.95, 5.7, 8.5, -0.08, 0.1, None, col))
    # --- door (south type): recess, wood leaves, fanlight, white surround + hood
    D = spec['portico']['back_wall']['door']
    dw, dh, fwid, lh = D['width'], D['height'], D['frame_w'], D['leaf_h']
    sz = D['sill_z']; hz0, hz1 = D['hood_z']
    cut = fb('door_cut', -dw / 2, dw / 2, sz, sz + dh, -0.4, 0.15, None, col)
    parts = [fb('door_leaf', -dw / 2, dw / 2, sz, sz + lh, -0.4, -0.32, 'wood_door', col),
             fb('door_split', -0.015, 0.015, sz, sz + lh, -0.32, -0.3, 'glass', col),
             fb('door_fan', -dw / 2, dw / 2, sz + lh, sz + dh, -0.4, -0.34, 'glass', col),
             fb('door_transom', -dw / 2, dw / 2, sz + lh - 0.06, sz + lh + 0.06, -0.34, -0.22, W, col),
             fb('door_fm', -0.03, 0.03, sz + lh, sz + dh, -0.34, -0.28, W, col),
             fb('door_fh', -dw / 2, dw / 2, sz + lh + 0.55, sz + lh + 0.61, -0.33, -0.27, W, col)]   # 1 cm off door_fm
    for k in range(1, 4):
        z = sz + lh * k / 4
        parts.append(fb('door_pan%d' % k, -dw / 2, dw / 2, z - 0.03, z + 0.03, -0.32, -0.3, 'wood_door', col))
    # surround per the photo (DOOR_SURROUND); spec frame_w / hood_z kept only as the fallback names fwid, hz0, hz1
    S = DOOR_SURROUND; jw, hh, ch_ = S['jamb_w'], S['head_h'], S['cap_h']
    fx = dw / 2 + jw                                   # outer edge of the jambs (frame 2.09 wide)
    zh0 = sz + dh; zh1 = zh0 + hh                      # head band 4.7 -> 5.25
    zc1 = zh1 + ch_                                    # cap moulding top 5.33
    hz0, hz1 = S['hood_z']                             # hood 5.85 -> 6.2
    hx = S['hood_half_w']; cx_, cw_ = S['console_x'], S['console_w']
    parts += [fb('door_sl', -fx, -dw / 2, sz, zh0, 0, 0.1, W, col),
              fb('door_sr', dw / 2, fx, sz, zh0, 0, 0.1, W, col),
              fb('door_st', -fx, fx, zh0, zh1, 0, 0.1, W, col),                         # plain head band
              fb('door_cap', -fx - 0.05, fx + 0.05, zh1, zc1, 0, S['cap_proj'], W, col),  # thin cap moulding
              fb('door_hood', -hx, hx, hz0, hz1 - 0.1, 0, S['hood_proj'] - 0.06, W, col),  # hood fascia
              fb('door_hood_top', -hx - 0.04, hx + 0.04, hz1 - 0.1, hz1, 0, S['hood_proj'], W, col),  # hood crown slab
              fb('door_br1', -cx_ - cw_ / 2, -cx_ + cw_ / 2, zc1, hz0, 0.1, S['console_proj'], W, col),  # consoles
              fb('door_br2', cx_ - cw_ / 2, cx_ + cw_ / 2, zc1, hz0, 0.1, S['console_proj'], W, col)]
    kit.add('door', join(parts, 'proto_door'), cut)
    # --- attic round-headed louvred window in a shallow arched panel
    sw_ = at['side_windows']; aw, ah, az = sw_['width'], sw_['height'], sw_['z_bottom']
    inner = arch_pts(aw, az, az + ah)
    cut = xz_solid('awin_cut', inner, -0.3, 0.12, None, col)
    parts = [xz_solid('awin_louvre', inner, -0.3, -0.24, 'louvre', col),
             xz_ring('awin_frame', arch_pts(aw + 0.28, az - 0.14, az + ah + 0.14), inner, 0, 0.07, W, col),
             fb('awin_mv', -0.03, 0.03, az, az + ah - 0.1, -0.24, -0.18, W, col),
             fb('awin_mh', -aw / 2, aw / 2, az + ah - aw / 2 - 0.03, az + ah - aw / 2 + 0.03, -0.23, -0.17, W, col),
             fb('awin_sill', -aw / 2 - 0.25, aw / 2 + 0.25, az - 0.26, az - 0.14, 0, 0.14, W, col)]
    pw_ = 2.7; pz0 = az - 0.6; pz1 = az + ah + 0.75
    parts.append(xz_ring('awin_panel', arch_pts(pw_ + 0.3, pz0 - 0.15, pz1 + 0.15), arch_pts(pw_, pz0, pz1), 0, 0.06, W, col))
    for i in range(6):
        z = az + 0.3 + i * 0.4
        parts.append(fb('awin_slat%d' % i, -aw / 2 + 0.05, aw / 2 - 0.05, z - 0.02, z + 0.02, -0.24, -0.21, W, col))
    kit.add('awin', join(parts, 'proto_awin'), cut)
    # --- attic thermal (segmental) window
    tw = at['thermal_window']; tw_w, tz0, tz1 = tw['width'], tw['z_bottom'], tw['z_top']
    inner = ell_pts(tw_w, tz0, tz1)
    cut = xz_solid('twin_cut', inner, -0.3, 0.12, None, col)
    parts = [xz_solid('twin_glass', inner, -0.3, -0.24, 'glass', col),
             xz_ring('twin_frame', ell_pts(tw_w + 0.3, tz0 - 0.15, tz1 + 0.15), inner, 0, 0.07, W, col),
             fb('twin_sill', -tw_w / 2 - 0.15, tw_w / 2 + 0.15, tz0 - 0.15, tz0, 0, 0.07, W, col),
             fb('twin_m1', -tw_w / 6 - 0.03, -tw_w / 6 + 0.03, tz0, tz1 - 0.1, -0.24, -0.18, W, col),
             fb('twin_m2', tw_w / 6 - 0.03, tw_w / 6 + 0.03, tz0, tz1 - 0.1, -0.24, -0.18, W, col),
             fb('twin_mh', -tw_w / 2 + 0.15, tw_w / 2 - 0.15, tz0 + 0.6, tz0 + 0.66, -0.23, -0.17, W, col)]
    kit.add('twin', join(parts, 'proto_twin'), cut)
    # --- dentils (main cornice / attic cornice) and baluster
    E = A['entablature']
    ft = E['architrave_h'] + E['frieze_h']
    kit.add('dent', fb('dent', -0.09, 0.09, E['z_bottom'] + ft + 0.12, E['z_bottom'] + ft + 0.38, 0.28, 0.50, W, col))
    kit.add('adent', fb('adent', -0.09, 0.09, az1 + 0.12, az1 + 0.32, 0.12, 0.31, W, col))
    bal = [(0, 0), (0.08, 0), (0.08, 0.07), (0.055, 0.09), (0.06, 0.17), (0.095, 0.27), (0.105, 0.36), (0.09, 0.48),
           (0.065, 0.62), (0.052, 0.72), (0.06, 0.78), (0.08, 0.82), (0.08, 0.9), (0, 0.9)]
    kit.add('bal', lathe('proto_bal', bal, segments=10, material=W, collection=col))


# ----------------------------------------------------------------------------- facade layouts
def arm_bays(L, anta_at_start):
    """Pilaster positions and bays of an arm flank, from the anta (portico) end. us[-1] is always the pilaster next
    to the re-entrant corner. 2-bay flanks (E/W arms): photo (left/right wing crops) = PANEL bay at the portico end,
    WINDOW bay at the core end; 3-bay flanks: win, panel, win."""
    nb = 3 if L > 12 else 2
    avail = L - 1.3 - 1.0
    bw = (avail - (nb - 1) * 1.0) / nb
    us, bays, u = [], [], 1.3
    types = ['win', 'panel', 'win'] if nb == 3 else ['panel', 'win']
    for k in range(nb):
        bays.append((u, u + bw, types[k])); u += bw
        if k < nb - 1:
            us.append(u + 0.5); u += 1.0
    us.append(L - 0.5)
    if not anta_at_start:
        us = [L - x for x in us]; bays = [(L - b, L - a, t) for a, b, t in bays]
    return us, bays


def cb_long_bays(L, convex_at_start):
    us = [1.3 + 2.6 + 0.5, L - 0.5]
    bays = [(1.3, 3.9, 'win'), (4.9, 7.5, 'panel')]
    if not convex_at_start:
        us = [L - x for x in us]; bays = [(L - b, L - a, t) for a, b, t in bays]
    return us, bays


def cb_short_bays(L, convex_at_start):
    if convex_at_start:
        return [L - 0.5], [(1.3, L - 1.0, 'panel')]
    return [0.5], [(1.0, L - 1.3, 'panel')]


def fill_bay(kit, face, u0, u1, typ, slit_du=0.0, slit=True):
    """slit=False: panel bay without the ventilation slit (photo: arm flanks and the long corner-block faces show
    plain wall there; the slit is only seen on the 5.5 m corner-block faces and the portico back walls)."""
    uc = (u0 + u1) / 2
    kit.put('relief', face, uc)
    if typ == 'win':
        kit.put('wtall', face, uc); kit.put('wup', face, uc)
    else:
        kit.put('sunk', face, uc)
        if slit:
            kit.put('wsmall', face, uc + slit_du)


def dentils(kit, face, key, pitch, margin=0.3):
    n = int((face.L - 2 * margin) / pitch)
    if n < 1: return
    start = (face.L - (n - 1) * pitch) / 2
    for i in range(n):
        kit.put(key, face, start + i * pitch)


# ----------------------------------------------------------------------------- build
def build(spec, col):
    objs = []
    kit = Kit(col)
    make_protos(spec, kit, col)
    W = 'white_paint'

    # ---------------- podium (top z=0, down to square level) with granite coping; south edge left flat for the stairs
    P = spec['podium']; sq = spec['square_ground_z']; st = spec['stairs']
    hw, ys, yn = P['half_w'], P['y_range'][0], P['y_range'][1]
    objs.append(add_box('body_podium', (2 * hw, yn - ys, -sq), (0, (ys + yn) / 2, sq / 2), material='granite', collection=col))
    ch, cp = P['plinth']['top_coping_h'], P['plinth']['coping_projection']
    xo = st['side_walls']['x_outer']
    for name, size, c in [('W', (0.5 + cp, yn - ys + 2 * cp, ch), (-hw - cp + (0.5 + cp) / 2, (ys + yn) / 2, -ch / 2 + 0.01)),
                          ('E', (0.5 + cp, yn - ys + 2 * cp, ch), (hw + cp - (0.5 + cp) / 2, (ys + yn) / 2, -ch / 2 + 0.01)),
                          ('N', (2 * hw + 2 * cp, 0.5 + cp, ch), (0, yn + cp - (0.5 + cp) / 2, -ch / 2 + 0.01)),
                          ('SW', (hw - xo + cp, 0.5 + cp, ch), (-(hw + cp + xo) / 2, ys - cp + (0.5 + cp) / 2, -ch / 2 + 0.01)),
                          ('SE', (hw - xo + cp, 0.5 + cp, ch), ((hw + cp + xo) / 2, ys - cp + (0.5 + cp) / 2, -ch / 2 + 0.01))]:
        objs.append(add_box('body_podium_coping_' + name, size, c, material='granite', collection=col))

    # ---------------- plan outline of the Greek cross (CCW), faces
    C = spec['core']; A = spec['arms']; aw = A['common']['half_w']
    hwc, hdc = C['half_w'], C['half_d']
    S_end, N_end = A['south']['end_wall_y'], A['north']['end_wall_y']
    E_end, W_end = A['east']['end_wall_x'], A['west']['end_wall_x']
    PL = [(aw, S_end), (aw, -hdc), (hwc, -hdc), (hwc, -aw), (E_end, -aw), (E_end, aw), (hwc, aw), (hwc, hdc), (aw, hdc), (aw, N_end),
          (-aw, N_end), (-aw, hdc), (-hwc, hdc), (-hwc, aw), (W_end, aw), (W_end, -aw), (-hwc, -aw), (-hwc, -hdc), (-aw, -hdc), (-aw, S_end)]
    faces = [Face(PL[i], PL[(i + 1) % 20]) for i in range(20)]
    ent = A['common']['entablature']; par = A['common']['parapet']
    ez0, ez1 = ent['z_bottom'], ent['z_top']

    # walls 0 -> 11.5 as one extrusion of the cross footprint
    wall = extrude_polygon('body_walls', PL, ez0, 0.0, material='wall', collection=col)
    objs.append(wall)
    # hidden fillers closing the core and the arms between 11.5 and the roofs/attic (the arm fillers are flush
    # with the end walls so the end-wall face is solid behind the portico entablature)
    objs.append(add_box('body_core_fill', (2 * hwc - 0.6, 2 * hdc - 0.6, par['z_top'] - ez0), (0, 0, (ez0 + par['z_top']) / 2), material='wall', collection=col))
    cbz = spec['corner_blocks']['top_z']
    objs.append(add_box('body_core_roof', (2 * hwc - 0.9, 2 * hdc - 0.9, 0.08), (0, 0, cbz - 0.02), material='roof_dark', collection=col))
    fz0, fz1 = ez0, A['common']['roof']['eaves_z'] - 0.2
    for name, size, c in [('S', (2 * aw - 0.6, -hdc - S_end + 0.3, fz1 - fz0), (0, (S_end - hdc + 0.3) / 2, (fz0 + fz1) / 2)),
                          ('N', (2 * aw - 0.6, N_end - hdc + 0.3, fz1 - fz0), (0, (N_end + hdc - 0.3) / 2, (fz0 + fz1) / 2)),
                          ('E', (E_end - hwc + 0.3, 2 * aw - 0.6, fz1 - fz0), ((E_end + hwc - 0.3) / 2, 0, (fz0 + fz1) / 2)),
                          ('W', (-hwc - W_end + 0.3, 2 * aw - 0.6, fz1 - fz0), ((W_end - hwc + 0.3) / 2, 0, (fz0 + fz1) / 2))]:
        objs.append(add_box('body_arm_fill_' + name, size, c, material='wall', collection=col))

    # ---------------- continuous entablature 11.5-14.2 (not along the end walls: the porticos own that part)
    # profile = the portico's return profile shifted so that the frieze is flush with the pilaster shafts (0.2) and the
    # crown ends 0.02 INSIDE the portico's 12.0 return (0.98 from the wall plane): the return wraps the seam cleanly.
    ah, ft, et = ent['architrave_h'], ent['architrave_h'] + ent['frieze_h'], ez1 - ez0
    ent_profile = [(-0.3, 0), (0.12, 0), (0.12, ah * 0.34), (0.16, ah * 0.34), (0.16, ah * 0.68), (0.2, ah * 0.68), (0.2, ah * 0.88),
                   (0.28, ah * 0.96), (0.28, ah + 0.01), (0.2, ah + 0.01), (0.2, ft), (0.28, ft + 0.1), (0.28, ft + 0.4), (0.4, ft + 0.4),
                   (0.4, ft + 0.48), (0.52, ft + 0.48), (0.52, ft + 0.75), (0.88, ft + 0.75), (0.88, et - 0.22), (0.98, et - 0.08),
                   (0.98, et), (-0.3, et)]
    for q in range(4):
        pts = [PL[(5 * q + k) % 20] for k in range(5)]   # from one end-wall corner around to the next
        objs.append(sweep('body_entablature_%d' % q, ent_profile, pts, False, ez0, W, col))
    # parapet band 14.2-16.5 all around (plain, wall colour, thin coping)
    par_profile = [(-0.4, 0), (0.2, 0), (0.2, par['z_top'] - par['z_bottom'] - par['coping_h']), (0.28, par['z_top'] - par['z_bottom'] - par['coping_h']),
                   (0.28, par['z_top'] - par['z_bottom']), (-0.4, par['z_top'] - par['z_bottom'])]
    objs.append(sweep('body_parapet', par_profile, PL, True, par['z_bottom'], par['material'], col))

    # ---------------- facade articulation
    end_names = {4: 'E', 9: 'N', 14: 'W', 19: 'S'}
    for i, f in enumerate(faces):
        t = i % 5
        if t == 4:   # end wall = portico back wall
            cx = f.L / 2
            for off in spec['portico']['column_offsets'][1:-1]:   # the end positions are the portico's antae
                kit.put('pil', f, cx + off)
            for off in (-8.15, -4.25, 4.25, 8.15):
                kit.put('relief', f, cx + off)
            kit.put('relief_wide', f, cx)
            if end_names[i] == 'N':
                kit.put('wtall', f, cx); kit.put('wup', f, cx)
            else:
                kit.put('door', f, cx)
            for off in (-SLIT_END_WALL_X, SLIT_END_WALL_X):   # photo: the slit sits in the outer bays, anta side
                kit.put('wsmall', f, cx + off)
            continue
        re_u = None; slit_du = 0.0; slit = False
        if t == 0:
            us, bays = arm_bays(f.L, True); re_u = us[-1]
        elif t == 3:
            us, bays = arm_bays(f.L, False); re_u = us[-1]
        elif f.L < 7:
            us, bays = cb_short_bays(f.L, t == 2); slit = True
            slit_du = SLIT_CB_OFFSET if t == 2 else -SLIT_CB_OFFSET   # toward the re-entrant corner (photo, SW block)
        else:
            us, bays = cb_long_bays(f.L, t == 2)
        for u in us:
            kit.put('pil_re' if u == re_u else 'pil', f, u)      # flank pilaster at the re-entrant corner: shifted tiers
        for u0, u1, typ in bays:
            fill_bay(kit, f, u0, u1, typ, slit_du, slit)
        dentils(kit, f, 'dent', 0.32)
        if t == 1:   # convex corner pilaster at the end of this face
            nf = faces[i + 1]
            kit.put('cpil', nf, 0.0, rot=nf.rot)

    # ---------------- arm gable roofs (behind the end walls, dying into the attic)
    R = A['common']['roof']; rw = aw - par['thickness'] + 0.4
    prof = [(-rw, R['eaves_z'] - 0.4), (rw, R['eaves_z'] - 0.4), (rw, R['eaves_z']), (0, R['ridge_z']), (-rw, R['eaves_z'])]
    for name, length, loc, rz in [('S', (-hdc + 0.3) - (S_end + 0.05), (0, S_end + 0.05, 0), math.pi / 2),
                                  ('N', (N_end - 0.05) - (hdc - 0.3), (0, hdc - 0.3, 0), math.pi / 2),
                                  ('E', (E_end - 0.05) - (hwc - 0.3), (hwc - 0.3, 0, 0), 0.0),
                                  ('W', (-hwc + 0.3) - (W_end + 0.05), (W_end + 0.05, 0, 0), 0.0)]:
        ob = prism('body_roof_' + name, prof, length, material=R['material'], collection=col)
        place(ob, location=loc, rotation=(0, 0, rz))
        objs.append(ob)

    # ---------------- core attic (plus-shaped) 16.5 -> 25.2 with cornice, roof, balustrade
    at = C['attic']; ax, ay = at['arm_half_w'], at['arm_half_d']
    az0, az1, atop = at['z_base'], at['wall_top_z'], at['top_z']
    plus = [(ax, -hdc), (ax, -ay), (hwc, -ay), (hwc, ay), (ax, ay), (ax, hdc), (-ax, hdc), (-ax, ay), (-hwc, ay), (-hwc, -ay), (-ax, -ay), (-ax, -hdc)]
    attic = extrude_polygon('body_attic_walls', plus, az1 - az0, az0, material='wall', collection=col)
    objs.append(attic)
    plus_in = [(x - math.copysign(0.35, x), y - math.copysign(0.35, y)) for x, y in plus]
    objs.append(extrude_polygon('body_attic_roof', plus_in, atop - 0.02 - (az1 - 0.1), az1 - 0.1, material='roof_dark', collection=col))
    ch = at['cornice_h']; cpj = at['cornice_projection']
    acorn = [(-0.3, 0), (0.05, 0), (0.05, 0.08), (0.12, 0.12), (0.12, 0.34), (0.3, 0.4), (cpj, 0.48), (cpj, ch), (-0.3, ch)]
    objs.append(sweep('body_attic_cornice', acorn, plus, True, az1, W, col))
    afaces = [Face((-ax, -hdc), (ax, -hdc)), Face((hwc, -ay), (hwc, ay)), Face((ax, hdc), (-ax, hdc)), Face((-hwc, ay), (-hwc, -ay))]
    bal = at['balustrade']; bz0, bh, pitch = bal['z_base'], bal['height'], bal['baluster_pitch']
    for fi, f in enumerate(afaces):
        h = f.L / 2
        pil_us = [0.5, h - 3.9, h + 3.9, f.L - 0.5]
        if h > 11:
            pil_us += [h - 9.1, h + 9.1]
        for u in pil_us:
            kit.put('apil', f, u, target='attic')
        for off in at['side_windows']['offsets_along_face']:
            kit.put('awin', f, h + off, target='attic')
        kit.put('twin', f, h, target='attic')
        dentils(kit, f, 'adent', 0.36, 0.2)
        # balustrade: pedestals over the pilasters, rails + balusters between
        ped = sorted([0.25, f.L - 0.25, h - 3.9, h + 3.9] + ([h - 9.1, h + 9.1] if h > 11 else []))
        for u in ped:
            objs.append(f.box('body_bal_ped', u - 0.25, u + 0.25, bz0, bz0 + bh, -0.12, 0.32, W, col))
            objs.append(f.box('body_bal_pedcap', u - 0.3, u + 0.3, bz0 + bh, bz0 + bh + 0.07, -0.17, 0.37, W, col))
        for a, b in zip(ped[:-1], ped[1:]):
            u0, u1 = a + 0.25, b - 0.25
            objs.append(f.box('body_bal_rail0', u0, u1, bz0, bz0 + 0.15, -0.07, 0.27, W, col))
            objs.append(f.box('body_bal_rail1', u0, u1, bz0 + bh - 0.15, bz0 + bh, -0.08, 0.28, W, col))
            nb = int((u1 - u0) / pitch)
            s = u0 + ((u1 - u0) - (nb - 1) * pitch) / 2
            for k in range(nb):
                kit.put('bal', f, s + k * pitch, z=bz0 + 0.15, out=0.1)

    # ---------------- booleans: one joined cutter per wall solid
    bpy.context.view_layer.update()
    for target, host in (('main', wall), ('attic', attic)):
        cuts = kit.cut.get(target, [])
        if cuts:
            cutter = join(cuts, 'body_cutter_' + target)
            add_boolean(host, cutter)
            objs.append(cutter)
    kit.finish()
    objs += kit.objs
    return objs


# ----------------------------------------------------------------------------- standalone test
if __name__ == '__main__':
    spec = load_spec(); sc = reset_scene(); col = get_collection('Cathedral')
    # preview only: use the spec palette (mod_look does this in the final assembly) to judge the two-tone scheme
    for k, v in spec['materials'].items():
        if isinstance(v, dict) and 'rgb' in v:
            MATERIAL_SPECS[k] = {'Base Color': tuple(v['rgb']) + (1,), 'Roughness': v.get('roughness', 0.6), 'Metallic': v.get('metallic', 0.0)}
    t0 = time.time()
    objs = build(spec, col)
    print('[body] build %.1fs  objects=%d  scene=%s' % (time.time() - t0, len(objs), count_scene()))
    setup_sun_sky(**spec['sun'])
    cam = spec['camera']
    views = [('1', cam['location'], cam['target'], cam['lens']),
             ('2', (-78, -82, 118), (0, 0, 12), 35),
             ('3', (-44, -50, 10), (-13, -15, 15.5), 50),
             ('dbg', (-6, -75, 4), (0, -33.5, 9), 50)]
    only = sys.argv[1:] or ['1', '2', '3']
    for n, loc, tgt, lens in views:
        if n not in only: continue
        setup_camera(loc, tgt, lens, shift_y=cam.get('shift_y', 0.0) if n == '1' else 0.0)
        p = render(os.path.join(PREVIEWS, 'mod_body_%s.png' % n), res=tuple(cam['preview_resolution']), samples=32)
        if n == '1':
            print('[cmp]', compare_with_photo(p))
