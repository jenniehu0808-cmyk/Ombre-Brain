"""nesting.py — numeric check that petal layers nest (inner layer stays inside the next one).
usage: python3 nesting.py [params.json]
Prints, per 3 mm height band, the radial extent [min..max] of each layer's petal surfaces
(ordered inside -> outside) and flags bands where an inner layer pokes outside the next layer.
"""
import sys, json, copy, numpy as np
import rose

ORDER_HINT = ['bud', 'inner', 'spiral', 'mid', 'inner2', 'outer', 'sepals']

def extents(layers, dz=3.0):
    rows = {}
    for name, L in layers.items():
        P = rose.petal_surface(L['phase'], nu=60, nv=40, **L['params'])
        r = np.linalg.norm(P[..., :2], axis=-1).ravel(); z = P[..., 2].ravel()
        rows[name] = (r, z)
    zmin = min(z.min() for r, z in rows.values()); zmax = max(z.max() for r, z in rows.values())
    bands = np.arange(np.floor(zmin / dz) * dz, zmax + dz, dz)
    return rows, bands

def main():
    layers = copy.deepcopy(rose.LAYERS)
    if len(sys.argv) > 1:
        ov = json.load(open(sys.argv[1])); rose.deep_update(layers, ov.get('layers', {}))
        layers = {k: v for k, v in layers.items() if v is not None}
    names = [n for n in ORDER_HINT if n in layers] + [n for n in layers if n not in ORDER_HINT]
    names = [n for n in names if n != 'sepals']
    rows, bands = extents(layers)
    print('z band      ' + ''.join(f'{n:>16s}' for n in names) + '   overlaps (inner pokes past next)')
    for z0 in bands:
        cells, ext = [], []
        for n in names:
            r, z = rows[n]; m = (z >= z0) & (z < z0 + 3.0)
            if m.any():
                ext.append((r[m].min(), r[m].max())); cells.append(f'{r[m].min():6.1f}..{r[m].max():5.1f}')
            else:
                ext.append(None); cells.append(' ' * 13 + '-')
        flags = []
        for i in range(len(names) - 1):
            a, b = ext[i], ext[i + 1]
            if a and b and a[1] > b[0] + 0.5 and z0 > 8:
                flags.append(f'{names[i]}>{names[i+1]} by {a[1]-b[0]:.1f}')
        print(f'{z0:5.0f}..{z0+3:3.0f}  ' + ''.join(f'{c:>16s}' for c in cells) + '   ' + ', '.join(flags))

if __name__ == '__main__':
    main()
