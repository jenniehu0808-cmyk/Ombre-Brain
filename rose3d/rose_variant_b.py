"""rose.py — procedural, 3D-printable replica of the reference rose.

Layers (inside -> outside), all anchored into a solid receptacle:
  bud     : 6 flat trapezoid panels tilted inward over a dimpled floor -> closed ~10 mm hex cup (cream)
  inner   : 6 cupped pale lining petals, 30 deg out of phase with the black whorl          (cream)
  spiral  : 6 imbricate tulip-cup walls whose soft rolled rim tapers from a broad head to a
            pointed tail -> six slim ribbon crescents in a camera-iris pinwheel from above  (black)
  outer   : 5 broad overlapping shields, rounded goblet, thin rolled undulating rims       (cream)
  sepals  : 5 modest flush sepals under the hip (calyx)                                     (cream)
  stem + leaf (separate part with a peg; the head has a matching socket) and
  a one-piece 'full' union.

usage: python3 rose.py [--out DIR] [--res 1.0] [--no-union] [--render] [--only head]
       python3 rose.py --params my_params.json   (override any LAYERS entry)
"""
from __future__ import annotations
import argparse, copy, json, os, subprocess, sys
import numpy as np
import trimesh
import roselib as rl

D2R = np.pi / 180.0
HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# petal surface
# ----------------------------------------------------------------------------
def petal_surface(theta0, *,
                  r_base=4.0, z_base=0.0,          # where the petal leaves the receptacle
                  r_top=20.0, z_top=25.0,          # where the body centreline ends (the lip starts here)
                  rise=0.6, bulge=0.15,            # body centreline shape (used when ctrl is None)
                  ctrl=None,                       # explicit Bezier control points [(r1,z1),(r2,z2)]
                  lip_len=0.0, lip_turn=0.0,       # rim: a circular arc of this length (mm) that bends the end
                                                   # tangent outward/down by lip_turn deg (90 = horizontal)
                  lip_fade=0.5, lip_center=0.0,    # lateral taper of the bend: corners turn (1-lip_fade) as much;
                                                   # lip_center shifts the fat part toward the +v (>0) or -v edge
                  span=100.0,                      # total angular width at the widest point (deg)
                  w_base=0.35, w_tip=0.7, u_max=0.6,  # width profile (relative to widest)
                  spiral=0.0, spiral_u=1.5,        # r *= 1 + spiral*v : one edge in, other out (imbricate pinwheel)
                  cup_r=4.0, cup_z=2.0, cup_tip=0.5,  # edges toward axis / raised; fraction kept at tip
                  ripple_n=2.0, ripple_amp=1.0, ripple_phase=0.0, side_ripple=0.0,
                  skew=0.0,                        # sideways lean of the tip (deg)
                  roll=0.0,                        # +v edge up / -v edge down (mm)
                  tip_round=0.3,
                  edge_drop=0.0, edge_drop_bias=0.0,  # rim corners droop by this many mm; bias>0: +v corner more
                  lean=0.0,                        # whole petal tilted outward about its base (deg)
                  apex=0.0,                        # slightly pointed apex in the middle of the rim (mm)
                  nu=48, nv=40):
    v = np.linspace(-1.0, 1.0, nv)
    # ---- body centreline: cubic Bezier in the (r,z) plane, resampled by arc length
    dr, dz = r_top - r_base, z_top - z_base
    if ctrl is None:
        p1 = (r_base + 0.05 * dr, z_base + rise * dz)
        p2 = (r_base + (0.55 + bulge) * dr, z_base + 1.02 * dz)
    else:
        p1, p2 = (float(ctrl[0][0]), float(ctrl[0][1])), (float(ctrl[1][0]), float(ctrl[1][1]))
    Cb = [(r_base, z_base), p1, p2, (r_top, z_top)]
    tt = np.linspace(0.0, 1.0, 400)
    B = rl.bezier(Cb, tt)
    seg = np.linalg.norm(np.diff(B, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    L_body = float(cum[-1])
    lip_len = max(0.0, float(lip_len))
    L = L_body + lip_len
    if lip_len > 0:
        nl = int(np.clip(round(nu * lip_len / L), 6, nu - 8))
        nb = nu - nl
    else:
        nb, nl = nu, 0
    s_b = np.linspace(0.0, L_body, nb)
    t_b = np.interp(s_b, cum, tt)
    Pb = rl.bezier(Cb, t_b)                       # (nb, 2)
    rc = np.repeat(Pb[:, 0][:, None], nv, axis=1)
    zc = np.repeat(Pb[:, 1][:, None], nv, axis=1)
    s_all = s_b
    if nl > 0:
        e0, e1 = rl.bezier(Cb, [0.995, 1.0])
        phi_end = np.arctan2(e1[1] - e0[1], e1[0] - e0[0])     # end tangent angle in the (r,z) plane
        Vf = (v - lip_center) / (1.0 + abs(lip_center))
        fade = np.clip(1.0 - float(lip_fade) * Vf ** 2, 0.0, 1.0)
        turn = np.radians(lip_turn) * fade                      # (nv,) total bend per lateral position
        s_l = np.linspace(0.0, lip_len, nl + 1)[1:]             # (nl,)
        S_, T_ = np.meshgrid(s_l, turn, indexing='ij')         # (nl, nv)
        k = T_ / lip_len
        small = np.abs(T_) < 1e-4
        kk = np.where(small, 1.0, k)
        r_arc = e1[0] + (np.sin(phi_end) - np.sin(phi_end - kk * S_)) / kk
        z_arc = e1[1] + (np.cos(phi_end - kk * S_) - np.cos(phi_end)) / kk
        r_str = e1[0] + S_ * np.cos(phi_end)
        z_str = e1[1] + S_ * np.sin(phi_end)
        rc = np.concatenate([rc, np.where(small, r_str, r_arc)], axis=0)
        zc = np.concatenate([zc, np.where(small, z_str, z_arc)], axis=0)
        s_all = np.concatenate([s_b, L_body + s_l])
    u = s_all / L
    U, V = np.meshgrid(u, v, indexing='ij')
    lin = w_base + (w_tip - w_base) * U
    w = lin + (1.0 - lin) * rl.bump(U, u_max, k=2.0)
    # cupping
    c = w * (1.0 - (1.0 - cup_tip) * rl.smoothstep((U - 0.5) / 0.5))
    r = rc - cup_r * V ** 2 * c
    z = zc + cup_z * V ** 2 * c
    # imbricate spiral: one lateral edge sits further in, the other further out
    r = r * (1.0 + spiral * V * rl.smoothstep(U * spiral_u))
    # roll
    z = z + roll * V * U
    # drooping rim corners (optionally more on one side)
    if edge_drop:
        z = z - edge_drop * (1.0 + edge_drop_bias * V) * V ** 2 * U ** 3
    # ripples
    z = z + ripple_amp * np.sin(ripple_n * np.pi * V + ripple_phase) * U ** 3
    if side_ripple:
        z = z + side_ripple * np.sin(3.0 * np.pi * U + ripple_phase) * np.abs(V) ** 5
    # rounded tip corners
    r = r - tip_round * 0.5 * dr * (V ** 4) * (U ** 4)
    # slightly pointed apex in the middle of the rim
    if apex:
        g = np.exp(-(V / 0.35) ** 2) * U ** 8
        r = r + apex * g
        z = z - 0.4 * apex * g
    # whole-petal outward lean about the base point
    if lean:
        a = np.radians(lean)
        rr, zz = r - r_base, z - z_base
        r = r_base + rr * np.cos(a) + zz * np.sin(a)
        z = z_base - rr * np.sin(a) + zz * np.cos(a)
    th = (theta0 + skew * U) * D2R + V * 0.5 * span * D2R * w
    return np.stack([r * np.cos(th), r * np.sin(th), z], -1)


def petal(theta0, thickness=1.2, bias=0.0, **kw):
    return rl.thick_surface(petal_surface(theta0, **kw), thickness, bias)


# ----------------------------------------------------------------------------
# leaf
# ----------------------------------------------------------------------------
def leaf_surface(length=34.0, width=15.0, fold=2.0, droop=4.0, ripple=0.7, serr=0.5, nu=56, nv=24):
    u = np.linspace(0, 1, nu); v = np.linspace(-1, 1, nv)
    U, V = np.meshgrid(u, v, indexing='ij')
    w = rl.bump(U, 0.40, k=1.6)
    w = w * (1 + serr * 0.08 * np.sin(22 * np.pi * U) * np.abs(V) ** 3)   # serrated edge
    w = np.maximum(w, 0.08 * (1 - U) + 0.015)
    x = length * U
    y = 0.5 * width * V * w
    z = (fold * np.abs(V) * w - droop * U ** 2
         + ripple * np.sin(5 * np.pi * U + 0.5) * np.abs(V) ** 3 * w
         + 0.5 * np.sin(2.0 * np.pi * V) * U ** 2 * 0.3)
    return np.stack([x, y, z], -1)


# ----------------------------------------------------------------------------
# default parameters (R = 30 mm head radius). Edit here or override via --params.
# ----------------------------------------------------------------------------
LAYERS = {
    # centre: six flat trapezoid panels tilting inward ~10 deg over a dimpled floor -> closed ~10 mm hex cup
    'bud': dict(n=6, phase=0, thickness=1.2, params=dict(
        r_base=6.2, z_base=15.0, r_top=4.0, z_top=28.5, ctrl=[(5.5, 19.5), (4.7, 24.0)],
        lip_len=0.0, lip_turn=0.0, span=66, w_base=0.75, w_tip=1.0, u_max=0.95,
        spiral=0.0, spiral_u=1.0, cup_r=-0.8, cup_z=0.0, cup_tip=1.0, ripple_n=1, ripple_amp=0.0,
        skew=0, roll=0.0, edge_drop=0.0, tip_round=0.0)),
    # cream lining: six cupped pale petals 30 deg out of phase with the black walls; their faces fill
    # the gaps between the crescents from above and show between the black rims from the side
    'inner': dict(n=6, phase=50, thickness=1.2, vary={'z_top': [28.0, 27.0, 28.5, 27.5, 28.0, 27.0]}, params=dict(
        r_base=4.5, z_base=3.0, r_top=13.0, z_top=28.0, ctrl=[(10.0, 5.0), (10.0, 19.0)],
        lip_len=3.0, lip_turn=35, lip_fade=0.6, lip_center=-0.3, span=110, w_base=0.5, w_tip=0.85, u_max=0.6,
        spiral=-0.30, spiral_u=1.5, cup_r=1.5, cup_z=0.0, cup_tip=0.6, ripple_n=1, ripple_amp=0.0,
        skew=-6, roll=0.0, edge_drop=2.0, edge_drop_bias=0.4, tip_round=0.15)),
    # black whorl: six imbricate tulip cups (tail r~9, head r~20): convex belly, slight waist, then the
    # top flares outward with a soft rolled rim that is broad at the outer head and tapers to a point
    # at the inner tail -> slim ribbon crescents in a camera-iris pinwheel from above
    'spiral': dict(n=6, phase=20, thickness=1.4,
        vary={'z_top': [30.5, 29.0, 30.0, 28.5, 30.5, 29.5], 'r_top': [14.5, 14.9, 14.3, 14.8, 14.6, 15.0]},
        params=dict(
        r_base=7.0, z_base=2.0, r_top=14.5, z_top=29.5, ctrl=[(14.0, 4.0), (11.0, 20.0)],
        lip_len=4.2, lip_turn=40, lip_fade=1.0, lip_center=-0.3, span=115, w_base=0.5, w_tip=0.95, u_max=0.7,
        spiral=-0.36, spiral_u=1.5, cup_r=1.2, cup_z=0.0, cup_tip=0.6, ripple_n=1, ripple_amp=0.3,
        skew=-5, roll=0.0, edge_drop=3.0, edge_drop_bias=0.3, tip_round=0.35)),
    # outer: five broad cupped shields; rounded goblet, near-vertical wall, convex belly, thin rolled
    # undulating rims with one slightly pointed apex; sizes vary around the whorl
    'outer': dict(n=5, phase=10, thickness=1.3,
        vary={'z_top': [25.0, 19.5, 23.5, 20.0, 22.5], 'r_top': [22.5, 24.0, 22.0, 24.3, 23.0],
              'lean': [0.0, 2.0, 1.0, 2.5, 1.5], 'apex': [1.2, 0.6, 1.0, 0.8, 1.2]},
        params=dict(
        r_base=5.5, z_base=-6.5, r_top=23.0, z_top=23.0, ctrl=[(16.0, -7.0), (21.0, 8.0)],
        lip_len=5.5, lip_turn=100, lip_fade=0.15, span=125, w_base=0.5, w_tip=0.75, u_max=0.55,
        spiral=-0.15, spiral_u=4.0, cup_r=3.0, cup_z=1.0, cup_tip=0.5, ripple_n=2.0, ripple_amp=1.3, side_ripple=0.5,
        skew=-8, roll=0.0, edge_drop=1.5, tip_round=0.2, apex=1.0)),
    # sepals: five modest flush points under the hip (calyx), lying against the outer petal bases
    'sepals': dict(n=5, phase=46, thickness=1.4, bias=-0.6, params=dict(
        r_base=2.5, z_base=-9.0, r_top=14.0, z_top=-2.5, ctrl=[(7.0, -9.2), (12.0, -5.5)],
        lip_len=0.0, lip_turn=0.0, span=24, w_base=0.7, w_tip=0.12, u_max=0.3,
        spiral=0.0, cup_r=0.8, cup_z=0.6, cup_tip=0.2, ripple_n=1, ripple_amp=0.0,
        skew=0, roll=0.0, edge_drop=0.0, tip_round=0.0)),
}
# smooth ogee hip hidden behind the petal bases, rising into the post that fills the bud cup
# (shallow domed floor rising to z~27, ~1.5-3 mm under the panel rims)
RECEPTACLE = [(0, -10), (4.5, -10), (6.5, -9.3), (8.0, -7.6), (9.0, -5.2), (9.4, -2.5), (9.2, 0.5), (8.6, 3.5),
              (7.6, 6.5), (6.5, 9.5), (5.9, 12.5), (5.7, 16.0), (5.4, 19.5), (4.9, 23.0), (4.5, 25.2), (4.3, 25.6),
              (2.5, 26.5), (1.0, 27.1), (0, 27.2)]
STEM = dict(length=118.0, radius=2.5, taper=0.12, ridges=14, ridge_amp=0.06, leaf_at=0.47,
            leaf_len=34.0, leaf_w=15.0, leaf_yaw=-50, leaf_pitch=25)
COLORS = {'bud': 'cream', 'spiral': 'black', 'inner': 'cream', 'outer': 'cream', 'sepals': 'cream'}


def drop_slivers(mesh, min_vol=1.0):
    """Remove boolean-artifact bodies (a few faces, ~0 mm^3) so the part is one real body."""
    try:
        parts = mesh.split(only_watertight=False)
    except Exception:
        return mesh
    keep = [p for p in parts if p.volume >= min_vol]
    if len(keep) == len(parts) or not keep:
        return mesh
    return trimesh.util.concatenate(keep)


def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v
    return d


# ----------------------------------------------------------------------------
def build(res=1.0, union=True, parts_wanted=('head', 'stem'), R=30.0, layers=None, stem_cfg=None,
          receptacle_prof=None, colors=None, verbose=True):
    layers = layers or LAYERS
    stem_cfg = stem_cfg or STEM
    receptacle_prof = receptacle_prof or RECEPTACLE
    colors = colors or COLORS
    s = R / 30.0
    nu, nv = max(16, int(56 * res)), max(12, int(44 * res))
    P = {}

    receptacle = rl.revolve([(a * s, b * s) for a, b in receptacle_prof], n=int(72 * res))
    socket = trimesh.creation.cylinder(radius=2.75 * s, height=8.0 * s, sections=48)
    socket.apply_translation([0, 0, -9 * s + 3.5 * s])

    built = {}
    for name, L in layers.items():
        n, phase, t = L['n'], L['phase'], L['thickness']
        bias = L.get('bias', 0.0)
        ms = []
        for i in range(n):
            kw = dict(L['params'])
            kw['ripple_phase'] = kw.get('ripple_phase', 0.0) + 0.9 * i
            # optional per-petal variation: explicit list (cycled) or +/- amplitude alternating around the whorl
            for key, amp in L.get('vary', {}).items():
                if isinstance(amp, (list, tuple)):
                    kw[key] = amp[i % len(amp)]
                else:
                    kw[key] = kw.get(key, 0.0) + amp * (np.cos(np.pi * i) if n % 2 == 0 else np.sin(2 * np.pi * i / n))
            ms.append(petal(phase + 360.0 * i / n, t, bias, nu=nu, nv=nv, **kw))
        built[name] = ms
    if s != 1.0:
        for L in built.values():
            for m in L:
                m.apply_scale(s)

    if 'stem' in parts_wanted:
        import stemleaf
        cfg = dict(stem_cfg); cfg['z_top'] = BASE_Z
        P['stem_leaf'] = stemleaf.build_stem_leaf(res=res, s=s, union=union, cfg=cfg)

    cream = [m for nme, ms in built.items() if colors.get(nme, 'cream') == 'cream' for m in ms] + [receptacle]
    black = [m for nme, ms in built.items() if colors.get(nme) == 'black' for m in ms]
    if union:
        if verbose: print('union: cream ...'); sys.stdout.flush()
        head_cream = rl.union_all(cream)
        if verbose: print('union: black ...'); sys.stdout.flush()
        head_black = rl.union_all(black) if black else None
        if verbose: print('union: head ...'); sys.stdout.flush()
        head = rl.union_all([head_cream] + ([head_black] if head_black is not None else []))
        try:
            head_s = trimesh.boolean.difference([head, socket], engine='manifold', check_volume=False)
            head_cream_s = trimesh.boolean.difference([head_cream, socket], engine='manifold', check_volume=False)
        except Exception as e:
            print('socket difference failed:', e); head_s, head_cream_s = head, head_cream
        head_s, head_cream_s = drop_slivers(rl.fill_voids(head_s)), drop_slivers(rl.fill_voids(head_cream_s))
        if head_black is not None:
            head_black = drop_slivers(rl.fill_voids(head_black))
    else:
        head_cream = trimesh.util.concatenate(cream)
        head_black = trimesh.util.concatenate(black) if black else None
        head = trimesh.util.concatenate([head_cream] + ([head_black] if head_black is not None else []))
        head_s, head_cream_s = head, head_cream
    P['head'] = head_s
    P['head_cream'] = head_cream_s
    if head_black is not None:
        P['head_black'] = head_black
    if 'stem' in parts_wanted:
        P['full'] = rl.fill_voids(rl.union_all([head, P['stem_leaf']]), keep='largest') if union else trimesh.util.concatenate([head, P['stem_leaf']])
    P['_layers'] = built
    return P


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'out'))
    ap.add_argument('--res', type=float, default=1.0)
    ap.add_argument('--R', type=float, default=30.0, help='head radius in mm (default 30 -> 60 mm head)')
    ap.add_argument('--no-union', action='store_true')
    ap.add_argument('--only', default='all', choices=['all', 'head'])
    ap.add_argument('--render', action='store_true')
    ap.add_argument('--views', default='top,side,iso,front')
    ap.add_argument('--prefix', default='rose')
    ap.add_argument('--params', default=None, help='JSON file: {"layers": {...}, "stem": {...}, "receptacle": [...], "colors": {...}}')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    layers, stem_cfg, rec, colors = copy.deepcopy(LAYERS), dict(STEM), list(RECEPTACLE), dict(COLORS)
    if a.params:
        ov = json.load(open(a.params))
        deep_update(layers, ov.get('layers', {}))
        for k_ in list(layers):
            if layers[k_] is None:
                del layers[k_]
        stem_cfg.update(ov.get('stem', {}))
        rec = ov.get('receptacle', rec)
        colors.update(ov.get('colors', {}))
    parts = build(res=a.res, union=not a.no_union, parts_wanted=('head', 'stem') if a.only == 'all' else ('head',),
                  R=a.R, layers=layers, stem_cfg=stem_cfg, receptacle_prof=rec, colors=colors)
    for name, m in parts.items():
        if name.startswith('_'):
            continue
        m = rl.export_safe(m, os.path.join(a.out, f'{a.prefix}_{name}.stl'))
        rl.report(m, name)
    if a.render:
        cream = os.path.join(a.out, f'{a.prefix}_head_cream.stl') + ':#f1ebdc'
        black = [os.path.join(a.out, f'{a.prefix}_head_black.stl') + ':#141414'] if 'head_black' in parts else []
        subprocess.run(['node', os.path.join(HERE, 'render.js'), '--out', a.out, '--prefix', a.prefix + '_head',
                        '--views', a.views, cream] + black, check=False)
        if 'stem_leaf' in parts:
            subprocess.run(['node', os.path.join(HERE, 'render.js'), '--out', a.out, '--prefix', a.prefix,
                            '--views', 'side,front', cream] + black + [os.path.join(a.out, f'{a.prefix}_stem_leaf.stl') + ':#e9e4d6'], check=False)


if __name__ == '__main__':
    main()
