"""check_print.py — printability report for the exported STLs.
usage: python3 check_print.py out/rose_head.stl [more.stl ...]
"""
import sys, numpy as np, trimesh

def report(path):
    m = trimesh.load(path, force='mesh')
    print(f'== {path}')
    bb = m.bounds; size = bb[1] - bb[0]
    print(f'   faces={len(m.faces)}  bodies={m.body_count}  watertight={m.is_watertight}  winding={m.is_winding_consistent}')
    print(f'   size = {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm   volume = {m.volume/1000:.1f} cm^3  (~{m.volume/1000*1.24:.0f} g PLA solid)')
    # wall thickness: cast rays inward from sampled surface points
    pts, fid = m.sample(4000, return_index=True)
    nrm = m.face_normals[fid]
    try:
        th = trimesh.proximity.thickness(m, pts, exterior=False, normals=nrm, method='ray')
        th = th[np.isfinite(th) & (th > 0)]
        print(f'   wall thickness: min={th.min():.2f}  p5={np.percentile(th,5):.2f}  median={np.median(th):.2f} mm '
              f'({(th<0.8).mean()*100:.1f}% of samples < 0.8 mm)')
    except Exception as e:
        print('   thickness check failed:', e)
    # overhangs for face-up printing (+Z up): downward-facing faces steeper than 50 deg
    nz = m.face_normals[:, 2]
    area = m.area_faces
    over = (nz < -np.cos(np.radians(40)))      # normal pointing down within 50deg of straight down
    print(f'   downward-facing area (needs support if printed face-up): {area[over].sum()/area.sum()*100:.1f}% of surface')
    # lowest points -> what touches the bed
    zmin = bb[0][2]
    low = m.vertices[:, 2] < zmin + 0.5
    print(f'   bed contact footprint: {low.sum()} verts within 0.5 mm of z_min ({zmin:.1f})')
    return m

if __name__ == '__main__':
    for p in sys.argv[1:]:
        report(p)
