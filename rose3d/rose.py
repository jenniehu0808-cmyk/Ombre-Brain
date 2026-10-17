"""rose.py — procedural, 3D-printable replica of the reference rose.

Layers (inside -> outside), all anchored into a solid receptacle:
  bud     : 6 flat trapezoid panels tilted inward -> closed ~10 mm hexagonal cup
            over a domed core (CORE)                                        (cream)
  inner   : 6 cupped pale lining petals, 30 deg out of phase with the black (cream)
  spiral  : 6 long imbricate ribbons, tulip body + tapered rim roll
            -> camera-iris of slim crescents from above                     (black)
  outer   : 5 broad cupped shields, bases sunk into the hip, rolled wavy rims (cream)
  sepals  : 5 flush sepals under the head (calyx)                           (cream)
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
                                                   # tangent outward/down by lip_turn deg (90 = horizontal, >90 droops)
                  lip_fade=0.5, lip_center=0.0,    # lateral taper of the bend: corners turn (1-lip_fade) as much;
                                                   # lip_center shifts the fat part toward the +v (>0) or -v edge
                  lip_taper=0.0,                   # lip LENGTH shrinks to (1-lip_taper) at the -v edge (>0) or +v edge (<0)
                  lip_corner=0.0,                  # lip LENGTH shrinks to (1-lip_corner) at both lateral edges (soft corners)
                  apex=0.0,                        # soft pointed apex: rim centre pushed out by this many mm
                  span=100.0,                      # total angular width at the widest point (deg)
                  w_base=0.35, w_tip=0.7, u_max=0.6,  # width profile (relative to widest)
                  spiral=0.0, spiral_u=1.5,        # r *= 1 + spiral*v : one edge in, other out (imbricate pinwheel)
                  spiral_asym=0.0,                 # 0..1: the +v (outer) edge moves out only (1-spiral_asym) as far
                  cup_r=4.0, cup_z=2.0, cup_tip=0.5,  # edges toward axis / raised; fraction kept at tip
                  cup_asym=0.0,                    # 0..1: the +v (outer/head) edge is cupped only (1-cup_asym) as much
                  ripple_n=2.0, ripple_amp=1.0, ripple_phase=0.0, side_ripple=0.0,
                  skew=0.0,                        # sideways lean of the tip (deg)
                  roll=0.0,                        # +v edge up / -v edge down (mm)
                  tip_round=0.3,
                  edge_drop=0.0,                   # rim corners droop by this many mm
                  lean=0.0,                        # whole petal tilted outward about its base (deg)
                  crease=0.0,                      # shallow fold along the centre line (mm inward)
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
        nl = int(np.clip(round(nu * lip_len / L * 1.8) + 2, 5, nu - 8))   # a curled rim needs a few extra rows
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
        lt = float(lip_taper)
        len_v = lip_len * (1.0 - abs(lt) * 0.5 * (1.0 - np.sign(lt) * v)) if lt else np.full(nv, lip_len)
        len_v = len_v * (1.0 - float(lip_corner) * v ** 2)
        len_v = np.maximum(len_v, 0.08 * lip_len)               # (nv,) arc length per lateral position
        f_l = np.linspace(0.0, 1.0, nl + 1)[1:]                 # (nl,) fraction along the lip
        S_ = f_l[:, None] * len_v[None, :]                      # (nl, nv)
        T_ = np.repeat(turn[None, :], nl, axis=0)
        k = T_ / len_v[None, :]
        small = np.abs(T_) < 1e-4
        kk = np.where(small, 1.0, k)
        r_arc = e1[0] + (np.sin(phi_end) - np.sin(phi_end - kk * S_)) / kk
        z_arc = e1[1] + (np.cos(phi_end - kk * S_) - np.cos(phi_end)) / kk
        r_str = e1[0] + S_ * np.cos(phi_end)
        z_str = e1[1] + S_ * np.sin(phi_end)
        rc = np.concatenate([rc, np.where(small, r_str, r_arc)], axis=0)
        zc = np.concatenate([zc, np.where(small, z_str, z_arc)], axis=0)
        s_all = np.concatenate([s_b, L_body + f_l * lip_len])
    u = s_all / L
    U, V = np.meshgrid(u, v, indexing='ij')
    lin = w_base + (w_tip - w_base) * U
    w = lin + (1.0 - lin) * rl.bump(U, u_max, k=2.0)
    # cupping
    c = w * (1.0 - (1.0 - cup_tip) * rl.smoothstep((U - 0.5) / 0.5))
    V2 = V ** 2 * (1.0 - cup_asym * 0.5 * (V + np.abs(V)))     # = V^2 for v<0, V^2 (1 - asym V) for v>0
    r = rc - cup_r * V2 * c
    z = zc + cup_z * V2 * c
    # shallow fold along the centre line
    if crease:
        r = r - crease * np.exp(-(V / 0.45) ** 2) * rl.smoothstep(U * 2.0)
    # imbricate spiral: one lateral edge sits further in, the other further out
    fV = V - spiral_asym * 0.5 * (V + np.abs(V)) * V          # = V for v<0, V - asym*V^2 for v>0 (C1 at 0)
    r = r * (1.0 + spiral * fV * rl.smoothstep(U * spiral_u))
    # roll
    z = z + roll * V * U
    # drooping rim corners
    if edge_drop:
        z = z - edge_drop * V ** 2 * U ** 3
    # ripples
    z = z + ripple_amp * np.sin(ripple_n * np.pi * V + ripple_phase) * U ** 3
    if side_ripple:
        z = z + side_ripple * np.sin(3.0 * np.pi * U + ripple_phase) * np.abs(V) ** 5
    # rounded tip corners
    r = r - tip_round * 0.5 * dr * (V ** 4) * (U ** 4)
    # soft pointed apex in the middle of the rim
    if apex:
        r = r + apex * np.exp(-(V / 0.45) ** 2) * U ** 6
    # whole-petal outward lean about the base point
    if lean:
        a = np.radians(lean)
        rr, zz = r - r_base, z - z_base
        r = r_base + rr * np.cos(a) + zz * np.sin(a)
        z = z_base - rr * np.sin(a) + zz * np.cos(a)
    th = (theta0 + skew * U) * D2R + V * 0.5 * span * D2R * w
    return np.stack([r * np.cos(th), r * np.sin(th), z], -1)


def petal(theta0, thickness=1.2, bias=0.0, thick_rim=None, **kw):
    """Solid petal. thick_rim: thickness at the rim (tapers linearly along the petal from `thickness`)."""
    P = petal_surface(theta0, **kw)
    if thick_rim is not None and thick_rim != thickness:
        U = np.linspace(0.0, 1.0, P.shape[0])[:, None]
        thickness = (thickness + (thick_rim - thickness) * rl.smoothstep(U)) * np.ones((1, P.shape[1]))
    return rl.thick_surface(P, thickness, bias)


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
    # centre: closed faceted hexagonal bud ~11 mm across: six flat trapezoid panels tilted ~12 deg inward so
    # their top chords nearly meet (adjacent edges touching); the domed CORE fills the opening to ~0.5 mm
    # under the panel rims (no open hex nut, no visible post)
    'bud': dict(n=6, phase=50, thickness=1.2, params=dict(
        r_base=5.7, z_base=19.0, r_top=3.5, z_top=29.0, ctrl=[(5.4, 22.0), (4.1, 26.5)],
        lip_len=0.0, lip_turn=0.0, span=66, w_base=0.85, w_tip=1.0, u_max=0.6,
        spiral=0.03, cup_r=-0.5, cup_z=0.0, cup_tip=1.0, ripple_n=1, ripple_amp=0.0,
        skew=4, roll=0.0, edge_drop=0.0, tip_round=0.0)),
    # cream lining: 6 cupped pale petals 30 deg out of phase with the black blades, nested just inside them
    # with rims ~2.5 mm under the black rims and flaring out, so a broad cream face fills every gap
    # between the crescents from above and from the side
    'inner': dict(n=6, phase=50, thickness=1.2,
        vary={'z_top': [28.0, 26.5, 27.5, 26.0, 27.0, 26.5]},
        params=dict(
        r_base=4.0, z_base=2.0, r_top=12.0, z_top=27.0, ctrl=[(8.0, 5.0), (11.0, 17.0)],
        lip_len=2.2, lip_turn=60, lip_fade=0.4, span=100, w_base=0.5, w_tip=0.85, u_max=0.6,
        spiral=0.15, cup_r=2.0, cup_z=0.0, cup_tip=0.7, ripple_n=1, ripple_amp=0.2,
        skew=15, roll=0.0, edge_drop=2.0, tip_round=0.15)),
    # black whorl: 6 long imbricate blades (span 125, tail pulled in 50 %, head pushed out 30 %) -> a
    # camera-iris of crescents from above. Cupped tulip body: base r 7 at z 2, belly r~15.3 at z~18, easing
    # back to r 13 at z 29, then a short soft rim roll (widest near the head, tapering to a point at the tail);
    # strongly cupped with dropped corners so each blade reads as one rounded cup from the side.
    'spiral': dict(n=6, phase=20, thickness=1.4,
        vary={'z_top': [30.5, 29.0, 30.0, 28.5, 29.5, 29.0], 'lean': [2, 3, 2, 3, 2, 3]},
        params=dict(
        r_base=7.0, z_base=2.0, r_top=14.2, z_top=29.0, ctrl=[(14.5, 4.0), (18.5, 18.0)],
        lip_len=3.0, lip_turn=75, lip_fade=1.0, lip_center=0.2, lip_taper=0.85,
        span=125, w_base=0.5, w_tip=0.92, u_max=0.6,
        spiral=0.5, spiral_asym=0.35, spiral_u=1.5, cup_r=3.5, cup_asym=0.75, cup_z=0.0, cup_tip=0.7, ripple_n=1, ripple_amp=0.2,
        skew=20, roll=0.0, edge_drop=6.0, tip_round=0.2)),
    # outer: 5 broad cupped shields; bases sunk into the hip, rounded belly wall with a shallow midrib fold,
    # thin rolled rim with 2-3 long undulations, soft rounded corners and a soft apex; r_top / z_top / lean vary
    'outer': dict(n=5, phase=10, thickness=1.3,
        vary={'z_top': [24.5, 20.5, 23.5, 19.5, 22.5], 'r_top': [25.6, 26.4, 27.0, 25.6, 27.0], 'lean': [0, 2, 1, 3, 1]},
        params=dict(
        r_base=5.5, z_base=-7.5, r_top=24.5, z_top=22.0, ctrl=[(14.0, -3.0), (21.5, 11.0)],
        lip_len=3.0, lip_turn=85, lip_fade=0.3, lip_corner=0.6, span=112, w_base=0.75, w_tip=0.8, u_max=0.5,
        spiral=0.12, spiral_u=2.5, cup_r=3.5, cup_z=1.5, cup_tip=0.5, ripple_n=2.5, ripple_amp=1.3, side_ripple=0.3,
        skew=8, roll=0.0, edge_drop=3.0, tip_round=0.5, apex=1.5, crease=1.5)),
    # calyx: 5 modest sepals hugging the underside of the outer petals, pointed tips curling slightly up
    'sepals': dict(n=5, phase=30, thickness=1.5, params=dict(
        r_base=3.5, z_base=-9.8, r_top=16.0, z_top=-0.8, ctrl=[(7.0, -9.7), (12.0, -4.5)],
        lip_len=0.0, lip_turn=0.0, span=42, w_base=0.5, w_tip=0.1, u_max=0.4,
        spiral=0.0, cup_r=0.0, cup_z=0.6, cup_tip=0.4, ripple_n=1, ripple_amp=0.0,
        skew=0, roll=0, tip_round=0.0)),
}
BASE_Z = -10.5   # underside of the head (stem socket opens here)
# smooth ogee hip hidden behind the petal bases, narrowing to the stem socket (no turned foot ring)
RECEPTACLE = [(0, -10.5), (6.5, -10.5), (7.3, -9.4), (8.0, -7.5), (8.6, -5.5), (9.0, -3.0), (9.3, 0.5), (8.8, 4.0),
              (7.5, 7.0), (5.5, 9.0), (0, 10)]
# domed core inside the hexagonal centre bud; dome top ~0.5 mm under the panel rims
CORE = [(0, 9.0), (4.5, 9.0), (4.2, 14.0), (4.2, 18.0), (5.0, 21.0), (4.4, 25.0), (3.6, 27.6), (2.2, 28.3), (0, 28.6)]
STEM = dict(length=118.0, radius=2.5, taper=0.12, ridges=14, ridge_amp=0.06, leaf_at=0.47,
            leaf_len=34.0, leaf_w=15.0, leaf_yaw=-50, leaf_pitch=25)
COLORS = {'bud': 'cream', 'spiral': 'black', 'inner': 'cream', 'outer': 'cream', 'sepals': 'cream'}

# ----------------------------------------------------------------------------
# logo mode (default): the black whorl is the OpenAI blossom lofted into six standing
# petals (see logo.py), so the head reads as the logo from the top. A cream hexagonal
# bud fills the centre, a cream floor + lowered lining petals show through the windows.
# ----------------------------------------------------------------------------
LOGO = dict(diameter=43.0, z_bottom=5.0, z_top=28.5, base_scale=0.58, belly=0.05, belly_at=0.62,
            wave=3.4, wave_width=0.40, wave_phase=None, fillet=1.4, fillet_inset=0.6, rotate_deg=0.0, split=True,
            dz=(0.25, -0.15, 0.1, -0.25, 0.15, -0.1),
            core_top_gap=1.3,      # cream hex bud top sits this far below the black top
            window_gap=0.8,        # cream plugs in the six windows end this far below the black top
            dimple=1.0,            # height of the small cone on the hex bud
            floor=[(0, 1.0), (12.5, 1.0), (13.4, 4.0), (16.8, 12.0), (15.5, 14.0), (0, 14.0)])
_TIP = 41.0   # angle (deg) of the logo's outer-loop tips (one of six); cream whorls are phased against it
# cream stack in logo mode: a garden-rose cup of four overlapping whorls around the black logo.
# Every petal is a cupped bowl: it leaves the hip almost horizontally, rounds up through a belly at
# the widest radius, stands nearly vertical and then curls back over itself at the rim (lip_turn);
# thickness tapers from the base to a thin rim.
LOGO_LAYERS = {
    # 5 big guard petals: leave the hip steeply, belly r~26 at z~5, rim reflexed back in a broad ~5 mm curl
    'outer': dict(n=5, phase=10, thickness=1.3, thick_rim=1.05, params=dict(
        r_base=5.5, z_base=-7.5, r_top=24.5, z_top=13.0, ctrl=[(11.0, -6.5), (26.0, 2.5)],
        lip_len=9.5, lip_turn=110, lip_fade=0.4, lip_corner=0.45, span=98, w_base=0.45, w_tip=0.8, u_max=0.7,
        spiral=0.08, spiral_u=2.5, cup_r=3.0, cup_z=1.8, cup_tip=0.4, ripple_n=2.5, ripple_amp=1.6, side_ripple=0.3,
        skew=8, roll=0.0, edge_drop=3.0, tip_round=0.3, apex=1.2, crease=1.5),
        vary={'z_top': [14.0, 11.0, 13.5, 10.5, 12.5], 'r_top': [24.5, 25.0, 24.0, 24.8, 24.2], 'lean': [1, 1, 1, 2, 1]}),
    # 5 cupped petals between them, belly r~24 at z~8, rims reflexed above the guards
    'mid': dict(n=5, phase=46, thickness=1.25, thick_rim=1.05, params=dict(
        r_base=5.0, z_base=-5.0, r_top=23.0, z_top=20.0, ctrl=[(12.0, -4.5), (24.5, 7.0)],
        lip_len=7.0, lip_turn=95, lip_fade=0.4, lip_corner=0.45, span=90, w_base=0.5, w_tip=0.78, u_max=0.7,
        spiral=0.08, spiral_u=2.5, cup_r=3.0, cup_z=1.5, cup_tip=0.45, ripple_n=2.5, ripple_amp=1.2, side_ripple=0.3,
        skew=10, roll=0.0, edge_drop=2.5, tip_round=0.25, apex=1.0, crease=1.2),
        vary={'z_top': [21.0, 18.5, 20.5, 18.0, 19.5], 'r_top': [23.0, 23.5, 22.6, 23.3, 22.8], 'lean': [1, 0, 1, 0, 1]}),
    # 6 tighter upright petals centred on the dips between the black arms, softly rolled
    'inner2': dict(n=6, phase=11, thickness=1.2, thick_rim=1.05, params=dict(
        r_base=4.5, z_base=-1.0, r_top=22.0, z_top=22.5, ctrl=[(12.0, -1.0), (23.5, 9.0)],
        lip_len=5.5, lip_turn=80, lip_fade=0.4, lip_corner=0.45, span=78, w_base=0.55, w_tip=0.78, u_max=0.7,
        spiral=0.04, spiral_u=2.5, cup_r=3.0, cup_z=1.0, cup_tip=0.55, ripple_n=1.5, ripple_amp=0.7, side_ripple=0.2,
        skew=10, roll=0.0, edge_drop=2.0, tip_round=0.15, apex=0.8, crease=1.0),
        vary={'z_top': [23.5, 22.0, 23.0, 21.5, 23.3, 22.3], 'r_top': [22.0, 22.5, 21.7, 22.3, 21.9, 22.2], 'lean': [0, 1, 0, 1, 1, 0]}),
    # 6 innermost cream petals, each wrapped around one black lobe (centred on the arms), cupping follows the logo outline
    'inner3': dict(n=6, phase=41, thickness=1.2, thick_rim=1.05, params=dict(
        r_base=5.0, z_base=2.0, r_top=22.5, z_top=27.0, ctrl=[(13.0, 2.0), (23.0, 15.0)],
        lip_len=4.0, lip_turn=60, lip_fade=0.45, lip_corner=0.45, span=68, w_base=0.6, w_tip=0.78, u_max=0.7,
        spiral=0.03, spiral_u=2.5, cup_r=2.5, cup_z=0.8, cup_tip=0.6, ripple_n=1.5, ripple_amp=0.5, side_ripple=0.2,
        skew=10, roll=0.0, edge_drop=1.5, tip_round=0.1, apex=0.6, crease=0.8),
        vary={'z_top': [27.5, 26.0, 27.0, 25.5, 27.3, 26.3], 'r_top': [22.5, 22.9, 22.3, 22.8, 22.4, 22.7], 'lean': [0, 1, 0, 1, 0, 1]}),
    # calyx: 5 short cupped sepals tucked under the guard petals (tips just showing from below)
    'sepals': dict(n=5, phase=30, thickness=1.5, params=dict(
        r_base=3.5, z_base=-9.8, r_top=15.0, z_top=-6.0, ctrl=[(7.0, -10.3), (11.5, -8.5)],
        lip_len=0.0, lip_turn=0.0, span=34, w_base=0.6, w_tip=0.15, u_max=0.35,
        spiral=0.0, cup_r=0.5, cup_z=1.0, cup_tip=0.4, ripple_n=1, ripple_amp=0.0,
        skew=3, roll=0, tip_round=0.0),
        vary={'z_top': [-6.0, -7.0, -5.5, -6.5, -5.8], 'r_top': [15.0, 14.2, 15.5, 14.6, 15.2]}),
}
LOGO_COLORS = {k: 'cream' for k in LOGO_LAYERS}


def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v
    return d


# ----------------------------------------------------------------------------
def build(res=1.0, union=True, parts_wanted=('head', 'stem'), R=30.0, layers=None, stem_cfg=None,
          receptacle_prof=None, colors=None, verbose=True, core_prof=None, logo_cfg=None, tabletop=None):
    """tabletop: cut height in mm (at R=30) — the head gets no stem socket and its bottom is sliced flat
    this far above BASE_Z so it stands on a table by itself."""
    logo_active = logo_cfg is not None
    if logo_active and layers is None:
        layers = copy.deepcopy(LOGO_LAYERS)
        colors = dict(LOGO_COLORS, **(colors or {}))
    layers = copy.deepcopy(layers or LAYERS)
    stem_cfg = stem_cfg or STEM
    receptacle_prof = receptacle_prof or RECEPTACLE
    core_prof = core_prof or CORE
    colors = colors or COLORS
    s = R / 30.0
    nu, nv = max(12, int(48 * res)), max(10, int(40 * res))
    P = {}

    receptacle = rl.revolve([(a * s, b * s) for a, b in receptacle_prof], n=int(72 * res))
    core = rl.revolve([(a * s, b * s) for a, b in core_prof], n=int(60 * res))
    socket = trimesh.creation.cylinder(radius=2.75 * s, height=7.6 * s, sections=48)   # 5.5 mm hole, 7 mm deep
    socket.apply_translation([0, 0, BASE_Z * s + 3.2 * s])

    built = {}
    for name, L in layers.items():
        n, phase, t = L['n'], L['phase'], L['thickness']
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
            ms.append(petal(phase + 360.0 * i / n, t, nu=nu, nv=nv, thick_rim=L.get('thick_rim'), **kw))
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
    if logo_active:
        import logo as logomod
        from shapely.geometry import Polygon
        from shapely import affinity
        lc = dict(logo_cfg)
        gap, floor_prof = lc.pop('core_top_gap', 2.5), lc.pop('floor', LOGO['floor'])
        wgap = lc.pop('window_gap', 2.0)
        dimple_h = lc.pop('dimple', 1.0)
        whorl = logomod.logo_whorl(**lc)
        whorl.apply_scale(s)
        black.append(whorl)
        # cream hexagonal bud in the centre hole and cream plugs in the six windows: lofts that follow
        # the whorl's own scale profile (so they stay inside the walls down to the floor); the black is
        # carved out of the cream afterwards, so the small overlap into the walls is harmless
        hexcore, plugs = logomod.logo_fills(hex_gap=gap, window_gap=wgap, expand=0.4, **lc)
        hole = logomod.logo_polygon(lc['diameter'], lc.get('rotate_deg', 0.0))
        rin = np.sqrt(min(Polygon(h).area for h in hole.interiors) / (2 * np.sqrt(3)))
        z1 = lc['z_top'] - gap
        dimple = trimesh.creation.cone(radius=rin * 0.92, height=max(0.3, dimple_h), sections=48)
        dimple.apply_translation([0, 0, z1 - 0.05])
        floor = rl.revolve(floor_prof, n=int(72 * res))
        for m_ in [hexcore, dimple, floor] + plugs:
            m_.apply_scale(s)
        cream += [hexcore, dimple, floor] + plugs
    else:
        cream.append(core)
    if union:
        if verbose: print('union: cream ...'); sys.stdout.flush()
        head_cream = rl.union_all(cream)
        if verbose: print('union: black ...'); sys.stdout.flush()
        head_black = rl.union_all(black) if black else None
        if verbose: print('union: head ...'); sys.stdout.flush()
        head = rl.union_all([head_cream] + ([head_black] if head_black is not None else []))
        if tabletop is not None:
            zc = (BASE_Z + tabletop) * s
            head_s = trimesh.intersections.slice_mesh_plane(head, [0, 0, 1], [0, 0, zc], cap=True)
            head_cream_s = trimesh.intersections.slice_mesh_plane(head_cream, [0, 0, 1], [0, 0, zc], cap=True)
            for m_ in (head_s, head_cream_s):
                m_.merge_vertices(); m_.update_faces(m_.nondegenerate_faces()); m_.fix_normals()
        else:
            try:
                head_s = trimesh.boolean.difference([head, socket], engine='manifold', check_volume=False)
                head_cream_s = trimesh.boolean.difference([head_cream, socket], engine='manifold', check_volume=False)
            except Exception as e:
                print('socket difference failed:', e); head_s, head_cream_s = head, head_cream
        if head_black is not None:
            try:   # the two colour bodies must not overlap: carve the black out of the cream
                head_cream_s = trimesh.boolean.difference([head_cream_s, head_black], engine='manifold', check_volume=False)
            except Exception as e:
                print('cream-black difference failed:', e)
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
    ap.add_argument('--tabletop', type=float, default=None, metavar='MM',
                    help='stemless version: no socket, bottom sliced flat MM above the base (try 4)')
    ap.add_argument('--wall', type=float, default=1.0, help='multiply every petal thickness (e.g. 0.72 with --R 45 keeps walls ~1.4 mm)')
    ap.add_argument('--no-logo', action='store_true', help='classic spiral whorl instead of the logo whorl')
    ap.add_argument('--params', default=None, help='JSON file: {"layers": {...}, "stem": {...}, "receptacle": [...], "core": [...], "colors": {...}}')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    layers, stem_cfg, rec, colors, core = copy.deepcopy(LAYERS), dict(STEM), list(RECEPTACLE), dict(COLORS), list(CORE)
    if not a.no_logo:
        layers, colors = copy.deepcopy(LOGO_LAYERS), dict(LOGO_COLORS)
    if a.params:
        ov = json.load(open(a.params))
        deep_update(layers, ov.get('layers', {}))
        for k_ in list(layers):
            if layers[k_] is None:
                del layers[k_]
        stem_cfg.update(ov.get('stem', {}))
        rec = ov.get('receptacle', rec)
        core = ov.get('core', core)
        colors.update(ov.get('colors', {}))
    logo_cfg = None if a.no_logo else copy.deepcopy(LOGO)
    if a.params and logo_cfg is not None and 'logo' in ov:
        logo_cfg.update(ov['logo'] or {})
    if a.wall != 1.0:
        for L in layers.values():
            L['thickness'] = L['thickness'] * a.wall
            if L.get('thick_rim'):
                L['thick_rim'] = L['thick_rim'] * a.wall
    if a.tabletop is not None:
        a.only = 'head'
    parts = build(res=a.res, union=not a.no_union, parts_wanted=('head', 'stem') if a.only == 'all' else ('head',),
                  R=a.R, layers=layers, stem_cfg=stem_cfg, receptacle_prof=rec, colors=colors, core_prof=core, logo_cfg=logo_cfg,
                  tabletop=a.tabletop)
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
