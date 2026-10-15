#!/usr/bin/env bash
# Full-resolution build of every part + previews + printability report + viewer page.
set -euo pipefail
cd "$(dirname "$0")"
OUT=${1:-out}
RES=${RES:-1.0}
mkdir -p "$OUT"
python3 rose.py --res "$RES" --render --views top,side,iso,front --out "$OUT" --prefix rose
python3 compare.py "$OUT" rose_head "$OUT/compare.png"
python3 check_print.py "$OUT/rose_head.stl" "$OUT/rose_stem_leaf.stl" "$OUT/rose_full.stl" | tee "$OUT/print_report.txt"
python3 export_3mf.py "$OUT"
python3 viewer_build.py --out "$OUT/rose_viewer.html" \
  head_cream="$OUT/rose_head_cream.stl:#efe8d8" head_black="$OUT/rose_head_black.stl:#141414" stem_leaf="$OUT/rose_stem_leaf.stl:#e3ddd0"
