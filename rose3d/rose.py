"""rose.py — procedural, 3D-printable replica of the reference rose.

Layers (inside -> outside), all anchored into a solid receptacle:
  bud     : 6 tightly wrapped upright petals -> hexagonal centre opening   (cream)
  spiral  : 6 wide, imbricate petals with rolled-back rims = dark pinwheel (black)
  inner   : 5 cupped cream petals behind the dark whorl                    (cream)
  outer   : 5 broad, rippled, flared cream petals                          (cream)
  sepals  : 5 narrow sepals under the head                                 (cream)
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
                  r_top=20.0, z_top=25.0,          # where the (un-curled) centreline ends
                  rise=0.6, bulge=0.15,            # centreline shape: fraction of the way up it
                                                   # goes before heading out, and outward bulge
                  p1=None, p2=None,                # explicit Bezier control points as (r_frac, z_frac)
                                                   # of (r_top-r_base, z_top-z_base); override rise/bulge
                  curl_out=6.0, curl_down=5.0,     # rim roll-back: extra (r,+) and (z,-) at the tip
                  curl_fade=1.0,                   # 0: roll-back along the whole rim, 1: only the middle
                  span=100.0,                      # total angular width at the widest point (deg)
                  w_base=0.35, w_tip=0.7, u_max=0.6,  # width profile (relative to widest)
                  spiral=0.0,                      # r *= 1 + spiral*v : one edge in, other out
                  cup_r=4.0, cup_z=2.0, cup_tip=0.5,  # edges toward axis / raised; fraction kept at tip
                  ripple_n=2.0, ripple_amp=1.0, ripple_phase=0.0, side_ripple=0.0,
                  skew=0.0,                        # sideways lean of the tip (deg)
                  roll=0.0,                        # +v edge up / -v edge down (mm)
                  tip_round=0.3,
                  nu=48, nv=40):
    u = np.linspace(0.0, 1.0, nu)
    v = np.linspace(-1.0, 1.0, nv)
    U, V = np.meshgrid(u, v, indexing='ij')
    lin = w_base + (w_tip - w_base) * U
    w = lin + (1.0 - lin) * rl.bump(U, u_max, k=2.0)
    # centreline: straight (no roll-back) and curled versions, blended laterally
    dr, dz = r_top - r_base, z_top - z_base
    p1 = p1 or (0.05, rise)
    p2 = p2 or (0.55 + bulge, 1.02)
    c_straight = [(r_base, z_base),
                  (r_base + p1[0] * dr, z_base + p1[1] * dz),
                  (r_base + p2[0] * dr, z_base + p2[1] * dz),
                  (r_top, z_top)]
    c_curled = [(r_base, z_base),
                (r_base + p1[0] * dr, z_base + p1[1] * dz),
                (r_base + p2[0] * dr, z_base + p2[1] * dz + 0.35 * curl_down),
                (r_top + curl_out, z_top - curl_down)]
    S = rl.bezier(c_straight, u)
    C = rl.bezier(c_curled, u)
    fade = (1.0 - V ** 2) ** (0.0001 + 1.5 * curl_fade) if curl_fade > 0 else np.ones_like(V)
    rc = S[:, 0][:, None] + fade * (C[:, 0] - S[:, 0])[:, None]
    zc = S[:, 1][:, None] + fade * (C[:, 1] - S[:, 1])[:, None]
    # cupping
    c = w * (1.0 - (1.0 - cup_tip) * rl.smoothstep((U - 0.5) / 0.5))
    r = rc - cup_r * V ** 2 * c
    z = zc + cup_z * V ** 2 * c
    # imbricate spiral: one lateral edge sits further in, the other further out
    r = r * (1.0 + spiral * V * np.clip(U * 1.5, 0, 1))
    # roll
    z = z + roll * V * U
    # ripples
    z = z + ripple_amp * np.sin(ripple_n * np.pi * V + ripple_phase) * U ** 3
    if side_ripple:
        z = z + side_ripple * np.sin(3.0 * np.pi * U + ripple_phase) * np.abs(V) ** 5
    # rounded tip corners
    r = r - tip_round * 0.5 * dr * (V ** 4) * (U ** 4)
    th = (theta0 + skew * U) * D2R + V * 0.5 * span * D2R * w
    return np.stack([r * np.cos(th), r * np.sin(th), z], -1)


def petal(theta0, thickness=1.2, bias=0.0, **kw):
    return rl.thick_surface(petal_surface(theta0, **kw), thickness, bias)




# ----------------------------------------------------------------------------
# spiral ribbon core: one continuous sheet wound around the axis, 6 petal lobes
# per turn. Adjacent turns are separated radially, so nothing self-intersects.
# ----------------------------------------------------------------------------
def ribbon_surface(t0, t1, *, lobes=6, r_rim=(3.5, 2.5, 0.8), z_rim=(30.0, -1.0), r_bot=(3.0, 0.5), z_bot=(8.0, -2.0),
                   lobe_r=0.25, lobe_z=3.0, drop=0.15, lean=(0.3, 1.5), lean_at=0.65, lean_down=0.6, lobe_phase=0.0,
                   p1=(0.15, 0.5), p2=(0.6, 1.0), cup=0.0, twist=0.0, mod_pow=1.5, poly=0.0, spt=240, ns=30):
    """Ribbon section for turns t0..t1 (1 turn = 360 deg) with `lobes` sawtooth petals per turn.

    Within each lobe (f = 0..1 along it) the rim radius and height ramp UP, then drop back over
    the last `drop` fraction: that drop is where the next petal starts, tucked under this one.
    r_rim = (a, b, c): turn radius a + b*tau + c*tau^2, modulated by (1 + lobe_r*(ramp-0.5))
    z_rim = (a, b): a + b*tau, modulated by lobe_z*(ramp-0.5)
    r_bot, z_bot: anchor curve inside the receptacle (linear in tau)
    lean = (a, b): outward lean of the rim (mm) = a + b*tau, peaking at f=lean_at and 0 at
    the lobe ends -> tapered crescent; lean_down: how far the leaning rim drops (fraction)
    lobe_phase: shift of the lobes in lobe units (use 0.5 on alternate turns for a pinwheel)
    mod_pow: the lobe modulation is scaled by s**mod_pow so the base stays smooth
    """
    nt = max(8, int(spt * (t1 - t0)))
    tau = np.linspace(t0, t1, nt)
    sv = np.linspace(0.0, 1.0, ns)
    T, S = np.meshgrid(tau, sv, indexing='ij')
    th = T * 2 * np.pi
    f = np.mod(lobes * T + lobe_phase, 1.0)
    up = f / (1.0 - drop)
    down = 1.0 - (f - (1.0 - drop)) / drop
    ramp = np.where(f < 1.0 - drop, up, rl.smoothstep(down))
    ramp = np.where(f < 1.0 - drop, rl.smoothstep(up) * 0.3 + up * 0.7, ramp)
    bumpf = rl.bump(np.clip(f / (1.0 - drop), 1e-4, 1 - 1e-4), lean_at, k=2.0)
    bumpf = np.where(f < 1.0 - drop, bumpf, 0.0)
    w = S ** mod_pow
    rr = (r_rim[0] + r_rim[1] * T + r_rim[2] * T ** 2) * (1.0 + lobe_r * (ramp - 0.5) * w)
    # poly: pull the rim toward a regular polygon with `lobes` straight sides (1 = full polygon)
    pf = np.cos(np.pi / lobes) / np.cos(np.pi / lobes * (2.0 * np.clip(f / (1.0 - drop), 0, 1) - 1.0))
    rr = rr * (1.0 + poly * (pf - 1.0) * w)
    zr = z_rim[0] + z_rim[1] * T + lobe_z * (ramp - 0.5) * w
    rb = r_bot[0] + r_bot[1] * T
    zb = z_bot[0] + z_bot[1] * T
    dr, dz = rr - rb, zr - zb
    P1r, P1z = rb + p1[0] * dr, zb + p1[1] * dz
    P2r, P2z = rb + p2[0] * dr, zb + p2[1] * dz
    om = 1 - S
    r = om ** 3 * rb + 3 * om ** 2 * S * P1r + 3 * om * S ** 2 * P2r + S ** 3 * rr
    z = om ** 3 * zb + 3 * om ** 2 * S * P1z + 3 * om * S ** 2 * P2z + S ** 3 * zr
    L = (lean[0] + lean[1] * T) * bumpf * S ** 4
    r = r + L
    z = z - lean_down * L
    r = r - cup * (1.0 - bumpf) * S ** 2
    thp = th + np.radians(twist) * S
    return np.stack([r * np.cos(thp), r * np.sin(thp), z], -1)


RIBBON = dict(
    sections=[  # (name, t0, t1, thickness, colour, lobe_phase)
        ('bud', 0.0, 1.0, 1.5, 'cream', 0.0),
        ('inner', 1.0, 2.0, 1.4, 'cream', 0.5),
        ('spiral', 2.0, 3.0, 1.5, 'black', 0.0),
    ],
    params=dict(lobes=6, r_rim=(3.5, 2.5, 0.8), z_rim=(30.0, -0.8), r_bot=(3.0, 0.5), z_bot=(8.0, -2.0),
                lobe_r=0.25, lobe_z=3.0, drop=0.15, lean=(0.2, 1.6), lean_at=0.65, lean_down=0.6,
                p1=(0.15, 0.5), p2=(0.6, 1.0), cup=0.3, twist=0.0, mod_pow=1.5),
)

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
    'bud': dict(n=6, phase=50, thickness=1.1, params=dict(
        r_base=2.6, z_base=4.0, r_top=5.2, z_top=28.0, rise=0.7, bulge=0.05,
        curl_out=0.0, curl_down=0.0, curl_fade=0.0, span=130, w_base=0.5, w_tip=0.85, u_max=0.55,
        spiral=0.22, cup_r=0.6, cup_z=0.0, cup_tip=1.0, ripple_n=1, ripple_amp=0.0,
        skew=25, roll=1.5, tip_round=0.15)),
    'spiral': dict(n=6, phase=20, thickness=1.4, params=dict(
        r_base=4.0, z_base=3.0, r_top=12.5, z_top=29.0, rise=0.75, bulge=0.1,
        curl_out=5.5, curl_down=5.0, curl_fade=0.8, span=125, w_base=0.4, w_tip=0.9, u_max=0.55,
        spiral=0.2, cup_r=2.5, cup_z=0.5, cup_tip=0.7, ripple_n=1, ripple_amp=0.3,
        skew=30, roll=3.0, tip_round=0.1)),
    'inner': dict(n=5, phase=46, thickness=1.2, params=dict(
        r_base=5.0, z_base=2.0, r_top=20.0, z_top=28.0, rise=0.7, bulge=0.15,
        curl_out=3.0, curl_down=3.0, curl_fade=0.6, span=105, w_base=0.35, w_tip=0.75, u_max=0.6,
        spiral=0.12, cup_r=4.0, cup_z=2.5, cup_tip=0.5, ripple_n=1.5, ripple_amp=1.0,
        skew=15, roll=2.0, tip_round=0.3)),
    'outer': dict(n=5, phase=10, thickness=1.3, params=dict(
        r_base=6.0, z_base=0.5, r_top=27.0, z_top=24.0, rise=0.65, bulge=0.2,
        curl_out=5.0, curl_down=7.0, curl_fade=0.4, span=100, w_base=0.3, w_tip=0.7, u_max=0.65,
        spiral=0.06, cup_r=5.0, cup_z=4.0, cup_tip=0.2, ripple_n=2.5, ripple_amp=1.8, side_ripple=0.8,
        skew=6, roll=1.0, tip_round=0.35)),
    'sepals': dict(n=5, phase=30, thickness=1.2, params=dict(
        r_base=5.0, z_base=-4.0, r_top=22.0, z_top=2.0, rise=0.3, bulge=0.1,
        curl_out=2.0, curl_down=4.0, curl_fade=0.0, span=22, w_base=0.6, w_tip=0.1, u_max=0.35,
        spiral=0.0, cup_r=1.0, cup_z=1.0, cup_tip=0.3, ripple_n=1, ripple_amp=0.0,
        skew=0, roll=0, tip_round=0.0)),
}
RECEPTACLE = [(0, -9), (3.5, -9), (6.5, -6), (8.3, -1.5), (8.4, 2.5), (7.0, 5.5), (4.5, 8.0), (0, 8.5)]
STEM = dict(length=118.0, radius=2.5, taper=0.12, ridges=14, ridge_amp=0.06, leaf_at=0.47,
            leaf_len=34.0, leaf_w=15.0, leaf_yaw=-50, leaf_pitch=25)
COLORS = {'bud': 'cream', 'spiral': 'black', 'inner': 'cream', 'outer': 'cream', 'sepals': 'cream'}


def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v
    return d


# ----------------------------------------------------------------------------
def build(res=1.0, union=True, parts_wanted=('head', 'stem'), R=30.0, layers=None, stem_cfg=None,
          receptacle_prof=None, colors=None, ribbon=None, verbose=True):
    layers = layers or LAYERS
    stem_cfg = stem_cfg or STEM
    receptacle_prof = receptacle_prof or RECEPTACLE
    colors = colors or COLORS
    s = R / 30.0
    nu, nv = max(12, int(48 * res)), max(10, int(40 * res))
    P = {}

    receptacle = rl.revolve([(a * s, b * s) for a, b in receptacle_prof], n=int(72 * res))
    socket = trimesh.creation.cylinder(radius=2.75 * s, height=8.0 * s, sections=48)
    socket.apply_translation([0, 0, -9 * s + 3.5 * s])

    built = {}
    for name, L in layers.items():
        n, phase, t = L['n'], L['phase'], L['thickness']
        ms = []
        for i in range(n):
            kw = dict(L['params'])
            kw['ripple_phase'] = kw.get('ripple_phase', 0.0) + 0.9 * i
            ms.append(petal(phase + 360.0 * i / n, t, nu=nu, nv=nv, **kw))
        built[name] = ms
    if ribbon:
        for name, t0, t1, th, col, ph in ribbon['sections']:
            Pr = ribbon_surface(t0, t1, spt=int(240 * res), ns=max(10, int(30 * res)), lobe_phase=ph, **ribbon['params'])
            built[name] = [rl.thick_surface(Pr, th)]
            colors = dict(colors); colors[name] = col
    if s != 1.0:
        for L in built.values():
            for m in L:
                m.apply_scale(s)

    if 'stem' in parts_wanted:
        import stemleaf
        P['stem_leaf'] = stemleaf.build_stem_leaf(res=res, s=s, union=union, cfg=stem_cfg)

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
        head_s, head_cream_s = rl.fill_voids(head_s, keep='largest'), rl.fill_voids(head_cream_s, keep='largest')
        if head_black is not None:
            head_black = rl.fill_voids(head_black, keep='big')
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
    ribbon = None
    if a.params and 'ribbon' in ov:
        ribbon = copy.deepcopy(RIBBON)
        if ov['ribbon'] is not None:
            if 'sections' in ov['ribbon']:
                ribbon['sections'] = [tuple(x) for x in ov['ribbon']['sections']]
            rp = ov['ribbon'].get('params', {})
            ribbon['params'].update({k: (tuple(v) if isinstance(v, list) else v) for k, v in rp.items()})
    parts = build(res=a.res, union=not a.no_union, parts_wanted=('head', 'stem') if a.only == 'all' else ('head',),
                  R=a.R, layers=layers, stem_cfg=stem_cfg, receptacle_prof=rec, colors=colors, ribbon=ribbon)
    for name, m in parts.items():
        if name.startswith('_'):
            continue
        rl.report(m, name)
        m.export(os.path.join(a.out, f'{a.prefix}_{name}.stl'))
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
