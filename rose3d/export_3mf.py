"""export_3mf.py — two-colour 3MF (cream + black bodies as one object) for Bambu Studio / PrusaSlicer.
usage: python3 export_3mf.py out
"""
import os, sys, trimesh
out = sys.argv[1] if len(sys.argv) > 1 else 'out'
cream = trimesh.load(os.path.join(out, 'rose_head_cream.stl'), force='mesh')
black = trimesh.load(os.path.join(out, 'rose_head_black.stl'), force='mesh')
cream.visual.face_colors = [239, 232, 216, 255]
black.visual.face_colors = [20, 20, 20, 255]
trimesh.Scene({'head_cream': cream, 'head_black': black}).export(os.path.join(out, 'rose_head_2colour.3mf'))
stem = trimesh.load(os.path.join(out, 'rose_stem_leaf.stl'), force='mesh')
stem.visual.face_colors = [227, 221, 208, 255]
trimesh.Scene({'head_cream': cream, 'head_black': black, 'stem_leaf': stem}).export(os.path.join(out, 'rose_all_parts.3mf'))
print('wrote', os.path.join(out, 'rose_head_2colour.3mf'), 'and rose_all_parts.3mf')
