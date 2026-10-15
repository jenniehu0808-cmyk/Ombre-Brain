"""compare.py — contact sheet: reference top/side next to a variant's renders.
usage: python3 compare.py <render_dir> <prefix> <out.png>
"""
import sys, os
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
ref = Image.open(os.path.join(HERE, 'ref', 'ref_side_top.jpg')).convert('RGB')
W, H = ref.size
ref_side = ref.crop((0, 0, W, H // 2))
ref_top = ref.crop((0, H // 2, W, H))
col = Image.open(os.path.join(HERE, 'ref', 'ref_collage.jpg')).convert('RGB')
cw, ch = col.size
ref_bw_top = col.crop((0, int(ch * 0.50), int(cw * 0.5), ch))
ref_bw_side = col.crop((int(cw * 0.5), int(ch * 0.50), cw, ch))

def fit(im, size):
    im = im.copy(); im.thumbnail((size, size)); bg = Image.new('RGB', (size, size), (12, 12, 12))
    bg.paste(im, ((size - im.width) // 2, (size - im.height) // 2)); return bg

d, prefix, out = sys.argv[1], sys.argv[2], sys.argv[3]
S = 420
tiles = [('REF top', ref_top), ('REF side', ref_side), ('REF 2-colour top', ref_bw_top), ('REF 2-colour side', ref_bw_side)]
mine = []
for v, label in [('top', 'MODEL top'), ('side', 'MODEL side'), ('iso', 'MODEL iso'), ('front', 'MODEL front')]:
    p = os.path.join(d, f'{prefix}_{v}.png')
    if os.path.exists(p):
        mine.append((label, Image.open(p).convert('RGB')))
sheet = Image.new('RGB', (S * 4, S * 2 + 30), (12, 12, 12))
dr = ImageDraw.Draw(sheet)
for i, (lab, im) in enumerate(tiles):
    sheet.paste(fit(im, S), (i * S, 0)); dr.text((i * S + 6, 4), lab, fill=(255, 220, 120))
for i, (lab, im) in enumerate(mine):
    sheet.paste(fit(im, S), (i * S, S + 30)); dr.text((i * S + 6, S + 34), lab, fill=(140, 220, 255))
sheet.save(out); print('wrote', out)
