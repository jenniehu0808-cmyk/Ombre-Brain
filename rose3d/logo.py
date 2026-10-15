"""logo.py — the OpenAI blossom outline as a polygon, and a 'whorl' built from it:
the logo extruded/lofted into six standing petal walls so that, seen from the
top, the black whorl reads exactly as the logo.

The outline comes from the simple-icons OpenAI path (viewBox 0 0 24 24).
"""
from __future__ import annotations
import re, math
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely import affinity
import roselib as rl

OPENAI_PATH = ("M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z")


def _sample_subpaths(d, pts_per_unit=40):
    from svgpathtools import parse_path
    path = parse_path(d)
    subs = path.continuous_subpaths()
    rings = []
    for sp in subs:
        pts = []
        for seg in sp:
            n = max(2, int(seg.length() * pts_per_unit))
            for t in np.linspace(0, 1, n, endpoint=False):
                z = seg.point(t)
                pts.append((z.real, -z.imag))      # flip SVG y
        rings.append(np.array(pts))
    return rings


def logo_polygon(diameter=40.0, rotate_deg=0.0, simplify=0.02):
    """Shapely polygon (with holes) of the logo, centred at the origin, scaled so its
    outer extent (max over x/y) equals `diameter`, rotated by rotate_deg."""
    rings = _sample_subpaths(OPENAI_PATH)
    polys = [Polygon(r) for r in rings]
    polys = [p.buffer(0) for p in polys]
    polys.sort(key=lambda p: -p.area)
    outer = polys[0]
    holes = [p for p in polys[1:] if outer.contains(p.representative_point())]
    poly = Polygon(outer.exterior.coords, [h.exterior.coords for h in holes])
    if simplify:
        poly = poly.simplify(simplify, preserve_topology=True)
    minx, miny, maxx, maxy = poly.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    poly = affinity.translate(poly, -cx, -cy)
    sc = diameter / max(maxx - minx, maxy - miny)
    poly = affinity.scale(poly, sc, sc, origin=(0, 0))
    if rotate_deg:
        poly = affinity.rotate(poly, rotate_deg, origin=(0, 0))
    return poly


def _ring_xy(coords):
    c = np.asarray(coords, float)[:, :2]
    if np.allclose(c[0], c[-1]):
        c = c[:-1]
    return c


def _loft(poly, zs, scales, ztop_fn, z_bottom):
    """Loft a shapely Polygon (with holes) through levels (zs, scales); the top levels get
    ztop_fn(xy) added (weighted by height^3). Returns a closed trimesh."""
    rings = [_ring_xy(poly.exterior.coords)] + [_ring_xy(h.coords) for h in poly.interiors]
    rings = [r for r in rings if len(r) >= 3]
    nlev = len(zs)
    V, F = [], []
    off = 0
    for ring in rings:
        n = len(ring)
        for k in range(nlev):
            w = (zs[k] - z_bottom) / (zs[-1] - z_bottom)
            V.append(np.column_stack([ring * scales[k], zs[k] + ztop_fn(ring) * (w ** 3)]))
        for k in range(nlev - 1):
            for i in range(n):
                a = off + k * n + i; b = off + k * n + (i + 1) % n
                c = off + (k + 1) * n + (i + 1) % n; d = off + (k + 1) * n + i
                F.append([a, b, c]); F.append([a, c, d])
        off += n * nlev
    V = np.concatenate(V)
    cap_poly = Polygon(rings[0], rings[1:])
    v2, f2 = trimesh.creation.triangulate_polygon(cap_poly, engine='earcut')
    for k, sc in ((0, scales[0]), (nlev - 1, scales[-1])):
        w = (zs[k] - z_bottom) / (zs[-1] - z_bottom)
        base = len(V)
        V = np.vstack([V, np.column_stack([v2 * sc, zs[k] + ztop_fn(v2) * (w ** 3)])])
        F.extend((f2 + base).tolist())
    m = trimesh.Trimesh(V, np.array(F), process=False)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.remove_unreferenced_vertices()
    m.fix_normals()
    return m


def logo_whorl(diameter=40.0, z_bottom=4.0, z_top=30.0, flare=0.10, wave=2.0, wave_phase=None,
               fillet=1.5, rotate_deg=0.0, levels=14, belly=0.0, belly_at=0.7, base_scale=None,
               split=True, dz=(1.5, -1.0, 0.5, -1.5, 1.0, -0.5), overlap_deg=12.0):
    """The logo lofted from z_bottom (scaled by base_scale) to z_top (scale 1): six standing
    walls leaning outward, with a rounded top edge whose outer loops rise like petal tips (wave).
    split=True cuts the logo into six wedge pieces (one per arm) built at z_top + dz[k], so the
    arms overlap like petals from the side; from the top the union is still the logo.
    Returns a watertight trimesh solid."""
    poly = logo_polygon(diameter, rotate_deg)
    zs = np.linspace(z_bottom, z_top, levels)
    w0 = (zs - z_bottom) / (z_top - z_bottom)
    s_base = (1 - flare) if base_scale is None else base_scale
    scales = s_base + (1 - s_base) * rl.smoothstep(w0) ** 0.8
    if belly:
        scales = scales + belly * rl.bump(np.clip(w0, 1e-3, 1 - 1e-3), belly_at, k=3.0)
    if fillet > 0:
        zs = np.concatenate([zs, [z_top + fillet * 0.6, z_top + fillet]])
        f = fillet / diameter            # inward roll of ~fillet/2 at the outer radius
        scales = np.concatenate([scales, [scales[-1] * (1 - 0.3 * f), scales[-1] * (1 - 1.0 * f)]])
    # petal tips at the arms' outer loops: phase the wave on the exterior's maximum radius
    ext = _ring_xy(poly.exterior.coords)
    rr_e = np.linalg.norm(ext, axis=1)
    th_max = np.arctan2(ext[np.argmax(rr_e), 1], ext[np.argmax(rr_e), 0])
    ph = (-6 * th_max) if wave_phase is None else wave_phase

    def ztop_offset(xy):
        th = np.arctan2(xy[:, 1], xy[:, 0])
        rr = np.linalg.norm(xy, axis=1) / (diameter / 2)
        outer = rl.smoothstep((rr - 0.70) / 0.22)
        return wave * (0.5 + 0.5 * np.cos(6 * th + ph)) * outer

    if not split:
        return _loft(poly, zs, scales, ztop_offset, z_bottom)
    from shapely.geometry import MultiPolygon
    pieces = []
    R = diameter
    for k in range(6):
        a0 = np.radians(60 * k + np.degrees(th_max) - 30 - overlap_deg / 2)
        a1 = a0 + np.radians(60 + overlap_deg)
        angs = np.linspace(a0, a1, 12)
        wedge = Polygon([(0, 0)] + [(R * np.cos(a), R * np.sin(a)) for a in angs])
        inter = poly.intersection(wedge)
        parts = list(inter.geoms) if isinstance(inter, MultiPolygon) else [inter]
        for p in parts:
            if p.area < 1.0:
                continue
            pieces.append(_loft(p, zs + dz[k % len(dz)], scales, ztop_offset, z_bottom + dz[k % len(dz)]))
    return rl.union_all(pieces)


if __name__ == '__main__':
    import sys
    poly = logo_polygon(40.0)
    print('rings: exterior + %d holes, area %.1f mm^2, bounds %s' % (len(poly.interiors), poly.area, np.round(poly.bounds, 1)))
    # hex hole: the hole closest to the centre
    for h in poly.interiors:
        hp = Polygon(h)
        print('  hole: area %.1f  centroid %s  n=%d' % (hp.area, np.round(hp.centroid.coords[0], 1), len(h.coords)))
    m = logo_whorl(40.0, z_bottom=5.0, z_top=28.5, base_scale=0.6, wave=3.0, fillet=2.0)
    rl.report(m, 'logo_whorl')
    out = sys.argv[1] if len(sys.argv) > 1 else '/tmp/logo_whorl.stl'
    m.export(out)
    # raster preview of the polygon
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (600, 600), (12, 12, 12)); dr = ImageDraw.Draw(im)
    def xy(c): return [(300 + x * 13, 300 - y * 13) for x, y in c]
    dr.polygon(xy(poly.exterior.coords), fill=(20, 20, 20), outline=(240, 240, 240))
    for h in poly.interiors: dr.polygon(xy(h.coords), fill=(12, 12, 12), outline=(240, 200, 120))
    im.save(out.replace('.stl', '_2d.png'))
