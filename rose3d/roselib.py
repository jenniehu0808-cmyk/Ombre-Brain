"""roselib — small procedural-mesh toolkit used by rose.py.

Everything here produces *closed, watertight* trimesh solids so that the
parts can be boolean-unioned (manifold3d) and sliced for 3D printing.

Conventions: millimetres, Z up, flower axis = Z, flower faces +Z.
"""
from __future__ import annotations
import numpy as np
import trimesh

TAU = 2 * np.pi


# ----------------------------------------------------------------------------
# generic helpers
# ----------------------------------------------------------------------------
def _unit(v, eps=1e-9):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def bump(u, u_max=0.6, k=2.5, floor=0.0):
    """Beta-like bump on [0,1] with maximum 1 at u=u_max; returns floor..1."""
    u = np.clip(u, 1e-6, 1 - 1e-6)
    a, b = k * u_max, k * (1 - u_max)
    f = (u / u_max) ** a * ((1 - u) / (1 - u_max)) ** b
    return floor + (1 - floor) * f


def bezier(ctrl, t):
    """Evaluate a Bezier curve with control points ctrl (n,d) at t (m,) -> (m,d)."""
    ctrl = np.asarray(ctrl, float)
    n = len(ctrl) - 1
    t = np.asarray(t, float)[:, None]
    from math import comb
    out = np.zeros((len(t), ctrl.shape[1]))
    for i, p in enumerate(ctrl):
        out += comb(n, i) * (1 - t) ** (n - i) * t ** i * p
    return out


def grid_normals(P):
    """Vertex normals of a (nu, nv, 3) surface grid: n = dP/du x dP/dv."""
    du = np.gradient(P, axis=0)
    dv = np.gradient(P, axis=1)
    n = np.cross(du, dv)
    # fix degenerate normals by borrowing from neighbours
    bad = np.linalg.norm(n, axis=-1) < 1e-9
    if bad.any():
        good = _unit(n)
        for _ in range(3):
            pad = np.pad(good, ((1, 1), (1, 1), (0, 0)), mode='edge')
            avg = (pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]) / 4
            good = np.where(bad[..., None], avg, good)
        n = good
    return _unit(n)


def thick_surface(P, thickness=1.2, bias=0.0):
    """Turn a (nu,nv,3) surface grid into a closed solid of the given thickness.

    bias in [-1,1]: 0 = offset symmetrically about the surface, +1 = all material
    on the +normal side, -1 = all material on the -normal side.
    Returns a watertight trimesh.Trimesh with outward-facing normals.
    """
    P = np.asarray(P, float)
    nu, nv, _ = P.shape
    N = grid_normals(P)
    top = P + N * thickness * (0.5 + 0.5 * bias)
    bot = P - N * thickness * (0.5 - 0.5 * bias)
    V = np.concatenate([top.reshape(-1, 3), bot.reshape(-1, 3)])
    off = nu * nv

    def tid(i, j):
        return i * nv + j

    faces = []
    I, J = np.meshgrid(np.arange(nu - 1), np.arange(nv - 1), indexing='ij')
    a = (I * nv + J).ravel()
    b = ((I + 1) * nv + J).ravel()
    c = ((I + 1) * nv + J + 1).ravel()
    d = (I * nv + J + 1).ravel()
    # top (normal = du x dv -> (a,b,c) winding)
    faces.append(np.stack([a, b, c], 1))
    faces.append(np.stack([a, c, d], 1))
    # bottom, reversed
    faces.append(np.stack([a + off, c + off, b + off], 1))
    faces.append(np.stack([a + off, d + off, c + off], 1))
    # boundary loop (counter-clockwise in (i,j) parameter space)
    loop = []
    loop += [tid(i, 0) for i in range(nu - 1)]
    loop += [tid(nu - 1, j) for j in range(nv - 1)]
    loop += [tid(i, nv - 1) for i in range(nu - 1, 0, -1)]
    loop += [tid(0, j) for j in range(nv - 1, 0, -1)]
    loop = np.array(loop)
    p, q = loop, np.roll(loop, -1)
    # walls: top p -> top q -> bot q, top p -> bot q -> bot p
    faces.append(np.stack([p, q + off, q], 1))
    faces.append(np.stack([p, p + off, q + off], 1))
    F = np.concatenate(faces)
    m = trimesh.Trimesh(V, F, process=False)
    m.merge_vertices()
    m.remove_degenerate_faces() if hasattr(m, 'remove_degenerate_faces') else None
    m.update_faces(m.nondegenerate_faces())
    m.fix_normals()
    return m


def revolve(profile_rz, n=64, z_axis=True):
    """Revolve a 2-D profile (r,z) polyline (r>=0, first & last point on axis,
    or we close it through the axis) around Z into a closed solid."""
    prof = np.asarray(profile_rz, float)
    if prof[0, 0] > 1e-9:
        prof = np.vstack([[0, prof[0, 1]], prof])
    if prof[-1, 0] > 1e-9:
        prof = np.vstack([prof, [0, prof[-1, 1]]])
    m = len(prof)
    th = np.linspace(0, TAU, n, endpoint=False)
    V = []
    for r, z in prof:
        V.append(np.stack([r * np.cos(th), r * np.sin(th), np.full(n, z)], 1))
    V = np.concatenate(V)
    faces = []
    for k in range(m - 1):
        for t in range(n):
            a = k * n + t
            b = k * n + (t + 1) % n
            c = (k + 1) * n + (t + 1) % n
            d = (k + 1) * n + t
            faces.append([a, c, b])
            faces.append([a, d, c])
    mesh = trimesh.Trimesh(V, np.array(faces), process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.fix_normals()
    return mesh


def tube(path, radius, n=32, radius_fn=None, cap=True):
    """Sweep a (possibly ridged) circle along a 3-D polyline `path` (m,3).

    radius: scalar or (m,) array.  radius_fn(phi, s) -> multiplier lets you add
    longitudinal ridges (phi = angle around tube, s = 0..1 along path).
    Returns a closed solid (capped ends).
    """
    path = np.asarray(path, float)
    m = len(path)
    radius = np.broadcast_to(np.asarray(radius, float), (m,))
    # parallel-transport frames
    T = np.gradient(path, axis=0)
    T = _unit(T)
    # initial normal
    ref = np.array([1.0, 0, 0]) if abs(T[0] @ [1, 0, 0]) < 0.9 else np.array([0, 1.0, 0])
    Nn = _unit(np.cross(T[0], np.cross(ref, T[0])))
    frames = []
    for k in range(m):
        if k > 0:
            # rotate N to stay perpendicular to new T (Rodrigues-free projection)
            Nn = _unit(Nn - T[k] * (Nn @ T[k]))
        B = np.cross(T[k], Nn)
        frames.append((Nn.copy(), B))
    phi = np.linspace(0, TAU, n, endpoint=False)
    s = np.linspace(0, 1, m)
    V = []
    for k in range(m):
        Nn, B = frames[k]
        r = radius[k]
        if radius_fn is not None:
            r = r * radius_fn(phi, s[k])
        ring = path[k] + (np.cos(phi)[:, None] * Nn + np.sin(phi)[:, None] * B) * np.asarray(r).reshape(-1, 1)
        V.append(ring)
    V = np.concatenate(V)
    faces = []
    for k in range(m - 1):
        for t in range(n):
            a = k * n + t
            b = k * n + (t + 1) % n
            c = (k + 1) * n + (t + 1) % n
            d = (k + 1) * n + t
            faces.append([a, b, c])
            faces.append([a, c, d])
    if cap:
        c0 = len(V)
        V = np.vstack([V, path[0], path[-1]])
        for t in range(n):
            faces.append([c0, (t + 1) % n, t])
            faces.append([c0 + 1, (m - 1) * n + t, (m - 1) * n + (t + 1) % n])
    mesh = trimesh.Trimesh(V, np.array(faces), process=False)
    mesh.merge_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.fix_normals()
    return mesh


# ----------------------------------------------------------------------------
# boolean / export helpers
# ----------------------------------------------------------------------------
def union_all(meshes, engine='manifold'):
    """Robust union: tries one big union, falls back to incremental, then to a
    plain concatenation (slicers still accept overlapping closed shells)."""
    meshes = [m for m in meshes if m is not None and len(m.faces) > 0]
    if len(meshes) == 1:
        return meshes[0].copy()
    try:
        u = trimesh.boolean.union(meshes, engine=engine, check_volume=False)
        if u.is_watertight and u.volume > 0:
            return u
    except Exception as e:  # pragma: no cover
        print('  union(all) failed:', e)
    acc = meshes[0]
    for i, m in enumerate(meshes[1:], 1):
        try:
            acc = trimesh.boolean.union([acc, m], engine=engine, check_volume=False)
        except Exception as e:
            print(f'  union step {i} failed ({e}); concatenating')
            acc = trimesh.util.concatenate([acc, m])
    return acc


def fill_voids(mesh, keep='all'):
    """Drop enclosed cavities (negative-volume shells) left behind by unions of
    overlapping petals, so the result is solid and slices cleanly.
    keep='largest': also drop detached slivers, keep the biggest body only.
    keep='big'    : drop bodies smaller than 1% of the largest."""
    try:
        parts = list(mesh.split(only_watertight=False))
    except Exception:
        return mesh
    pos = [p for p in parts if p.volume > 0]
    if not pos:
        return mesh
    pos.sort(key=lambda p: -p.volume)
    if keep == 'largest':
        if len(pos) > 1:
            print(f'  fill_voids: dropping {len(pos)-1} stray bodies (max vol {pos[1].volume:.1f} mm^3)')
        pos = pos[:1]
    elif keep == 'big':
        pos = [p for p in pos if p.volume >= 0.01 * pos[0].volume]
    if len(pos) == len(parts):
        return mesh
    return trimesh.util.concatenate(pos)


def export_safe(mesh, path):
    """Export so that what a slicer reads back is still watertight: quantise to float32
    (STL precision), merge vertices that collapse, drop degenerate faces, then write."""
    m = mesh.copy()
    m.vertices = m.vertices.astype(np.float32).astype(np.float64)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    if not m.is_watertight:
        try:
            m.fill_holes()
        except Exception:
            pass
    m.export(path)
    return m


def report(mesh, name='mesh'):
    bb = mesh.bounds
    size = bb[1] - bb[0]
    try:
        bodies = mesh.body_count
    except Exception:
        bodies = -1
    print(f'{name}: {len(mesh.faces)} faces, bodies={bodies}, watertight={mesh.is_watertight}, '
          f'winding_ok={mesh.is_winding_consistent}, volume={mesh.volume:.1f} mm^3, '
          f'size={size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm')
