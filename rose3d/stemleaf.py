"""stemleaf.py — stem (ridged, gently curved, with a peg) and a veined, serrated leaf.

build_stem_leaf(res, s, union, cfg) -> trimesh (one closed body)
The peg at the top plugs into the 5.5 mm socket under the flower head.
"""
from __future__ import annotations
import numpy as np
import trimesh
import roselib as rl

STEM = dict(z_top=-9.0, length=118.0, radius=2.5, taper=0.12, ridges=14, ridge_amp=0.06, leaf_at=0.47,
            leaf_len=38.0, leaf_w=17.0, leaf_yaw=-50, leaf_pitch=18, veins=4)


def leaf_surface(length=34.0, width=15.0, fold=2.0, droop=4.0, ripple=0.6, serr=0.7, nu=64, nv=28):
    u = np.linspace(0, 1, nu); v = np.linspace(-1, 1, nv)
    U, V = np.meshgrid(u, v, indexing='ij')
    w = rl.bump(U, 0.40, k=1.6)
    # serrated margin (teeth pointing toward the tip), only near the edge
    teeth = np.sin(26 * np.pi * U) ** 2 * (1 - U) ** 0.5 * (U > 0.08)
    w = w * (1 - serr * 0.07 * teeth * np.abs(V) ** 4)
    w = np.maximum(w, 0.09 * (1 - U) + 0.04)
    x = length * U
    y = 0.5 * width * V * w
    z = (fold * np.abs(V) * w - droop * U ** 2
         + ripple * np.sin(5 * np.pi * U + 0.5) * np.abs(V) ** 3 * w
         + 0.5 * np.sin(2.0 * np.pi * V) * U ** 2 * 0.3)
    return np.stack([x, y, z], -1)


def build_stem_leaf(res=1.0, s=1.0, union=True, cfg=None):
    c = dict(STEM); c.update(cfg or {})
    n = int(90 * res)
    t = np.linspace(0, 1, n)
    z = c['z_top'] * s - c['length'] * s * t
    x = 4.0 * s * np.sin(np.pi * t) ** 2 * (1 - t) - 1.5 * s * t
    y = -2.5 * s * np.sin(np.pi * t * 0.9) * t
    path = np.stack([x, y, z], 1)
    rad = c['radius'] * s * (1.0 - c['taper'] * t)
    stem = rl.tube(path, rad, n=int(40 * res),
                   radius_fn=lambda phi, ss: 1 + c['ridge_amp'] * np.cos(c['ridges'] * phi))
    peg = trimesh.creation.cylinder(radius=2.55 * s, height=7.0 * s, sections=48)
    peg.apply_translation([x[0], y[0], z[0] + 3.0 * s])
    # leaf blade
    L, W = c['leaf_len'] * s, c['leaf_w'] * s
    blade = rl.thick_surface(leaf_surface(L, W, 2.0 * s, 4.0 * s, 0.6 * s, nu=int(64 * res), nv=int(28 * res)), 1.2 * s)
    parts = [blade]
    # midrib
    uu = np.linspace(0, 1, 40)
    mid_z = -4.0 * s * uu ** 2 + 0.35 * s
    parts.append(rl.tube(np.stack([L * uu, 0 * uu, mid_z], 1), 0.6 * s * (1 - 0.65 * uu) + 0.25 * s, n=12))
    # side veins: pairs sweeping forward from the midrib toward the margin
    nv_ = int(c.get('veins', 4))
    for k in range(nv_):
        u0 = 0.12 + 0.17 * k
        wk = 0.5 * W * rl.bump(np.array([min(u0 + 0.18, 0.95)]), 0.40, k=1.6)[0]
        for sign in (-1, 1):
            uu2 = np.linspace(0, 1, 12)
            xs = L * (u0 + 0.20 * uu2)
            ys = sign * wk * 0.92 * uu2 ** 0.9
            zs = -4.0 * s * (xs / L) ** 2 + 0.3 * s + 2.0 * s * np.abs(ys) / (0.5 * W) * 0.7
            parts.append(rl.tube(np.stack([xs, ys, zs], 1), 0.32 * s * (1 - 0.5 * uu2) + 0.12 * s, n=8))
    # petiole
    parts.append(rl.tube(np.stack([np.linspace(-7 * s, 0.5, 10), np.zeros(10), np.linspace(1.5 * s, 0, 10)], 1), 0.9 * s, n=16))
    leaf = rl.union_all(parts) if union else trimesh.util.concatenate(parts)
    T = trimesh.transformations
    k_at = int(c['leaf_at'] * n)
    M = (T.translation_matrix(path[k_at]) @ T.rotation_matrix(np.radians(c['leaf_yaw']), [0, 0, 1])
         @ T.rotation_matrix(np.radians(c['leaf_pitch']), [0, 1, 0]) @ T.translation_matrix([6.0 * s, 0, 0]))
    leaf.apply_transform(M)
    out = rl.union_all([stem, peg, leaf]) if union else trimesh.util.concatenate([stem, peg, leaf])
    return rl.fill_voids(out, keep='largest') if union else out


if __name__ == '__main__':
    import sys
    m = build_stem_leaf(res=1.0)
    rl.report(m, 'stem_leaf')
    m.export(sys.argv[1] if len(sys.argv) > 1 else 'out/stem_test.stl')
