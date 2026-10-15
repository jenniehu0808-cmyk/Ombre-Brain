"""viewer_build.py — self-contained interactive three.js viewer with the meshes embedded.
usage: python3 viewer_build.py --out out/rose_viewer.html [--local-three DIR] part=path.stl:#hex ...
"""
import argparse, base64, json, os, struct
import numpy as np, trimesh

HERE = os.path.dirname(os.path.abspath(__file__))

def pack(mesh, angle=35.0):
    try:
        sm = trimesh.graph.smooth_shade(mesh, angle=np.radians(angle))
    except Exception:
        sm = mesh
    V = np.asarray(sm.vertices, np.float64); F = np.asarray(sm.faces, np.uint32)
    N = np.asarray(sm.vertex_normals, np.float64)
    lo, hi = V.min(0), V.max(0)
    q = np.round((V - lo) / np.maximum(hi - lo, 1e-9) * 65535 - 32768).astype(np.int16)
    n8 = np.clip(np.round(N * 127), -127, 127).astype(np.int8)
    buf = q.tobytes() + n8.tobytes()
    buf += b'\0' * ((4 - len(buf) % 4) % 4)
    buf += F.astype(np.uint32).tobytes()
    return dict(nv=int(len(V)), nf=int(len(F)), lo=lo.tolist(), hi=hi.tolist(), b64=base64.b64encode(buf).decode('ascii'))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--local-three', default=None, help='use a local three.js dir (file://) for offline smoke tests')
    ap.add_argument('--title', default='Ombre Rose')
    ap.add_argument('parts', nargs='+', help='name=path.stl:#hex')
    a = ap.parse_args()
    parts = []
    for spec in a.parts:
        name, rest = spec.split('=', 1)
        path, color = rest.split(':#')
        m = trimesh.load(path, force='mesh')
        d = pack(m); d['name'] = name; d['color'] = '#' + color
        parts.append(d)
        print(f'{name}: {d["nv"]} verts, {d["nf"]} tris, {len(d["b64"])/1e6:.2f} MB b64')
    allo = np.min([p['lo'] for p in parts], 0); allhi = np.max([p['hi'] for p in parts], 0)
    dims = (allhi - allo)
    head = [p for p in parts if p['name'].startswith('head')]
    hlo = np.min([p['lo'] for p in head], 0); hhi = np.max([p['hi'] for p in head], 0)
    three = a.local_three.rstrip('/') if a.local_three else 'https://cdn.jsdelivr.net/npm/three@0.160.0'
    if a.local_three:
        three = 'file://' + three
    importmap = json.dumps({"imports": {"three": f"{three}/build/three.module.js", "three/addons/": f"{three}/examples/jsm/"}})
    tpl = open(os.path.join(HERE, 'viewer_template.html')).read()
    html = (tpl.replace('__TITLE__', a.title)
               .replace('__IMPORTMAP__', importmap)
               .replace('__DATA__', json.dumps({'parts': parts}))
               .replace('__DIMS__', f'{dims[0]:.0f} × {dims[1]:.0f} × {dims[2]:.0f} mm')
               .replace('__HEAD_DIMS__', f'{hhi[0]-hlo[0]:.0f} mm across, {hhi[2]-hlo[2]:.0f} mm tall')
               .replace('__TRIS__', f'{sum(p["nf"] for p in parts):,}'))
    open(a.out, 'w').write(html)
    print('wrote', a.out, f'{os.path.getsize(a.out)/1e6:.2f} MB')

if __name__ == '__main__':
    main()
