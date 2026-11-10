#!/bin/bash
# Renders carousel preview PNGs with the real drawing code (host build).
# Usage: tools/carousel/make_previews.sh <outdir> [label.bmp ...]
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$1"; shift
mkdir -p "$OUT"
TMP="$(mktemp -d)"
gcc -O2 -Wall -DCAROUSEL_HOST -I"$ROOT/src" -o "$TMP/preview_host" \
    "$ROOT/tools/carousel/preview_host.c" "$ROOT/src/carousel_gfx.c" \
    "$ROOT/src/fonts/font_render.c" "$ROOT/src/utf_util.c"
i=0
for T in red-dark red-white hout donker licht; do
  for S in gba all slide; do
    "$TMP/preview_host" $i $S "$TMP/$T-$S.ppm" "$@"
    python3 "$ROOT/tools/carousel/ppm2png.py" "$TMP/$T-$S.ppm" "$OUT/$T-$S.png" 1
    python3 "$ROOT/tools/carousel/ppm2png.py" "$TMP/$T-$S.ppm" "$OUT/$T-$S-3x.png" 3
  done
  i=$((i+1))
done
rm -rf "$TMP"
ls "$OUT"
