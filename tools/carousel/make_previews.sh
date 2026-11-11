#!/bin/bash
# Renders carousel v2 preview PNGs with the real drawing code (host build).
# Usage: tools/carousel/make_previews.sh <outdir> <crtdir>
#   <crtdir> = library-db/crt (made by tools/library/maak_bibliotheek.py)
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$1"; C="$2"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
gcc -O2 -DCAROUSEL_HOST -I"$ROOT/src" -o "$TMP/ph" \
    "$ROOT/tools/carousel/preview_host.c" "$ROOT/src/carousel_gfx.c" \
    "$ROOT/src/fonts/font_render.c" "$ROOT/src/utf_util.c" 2>/dev/null
shot() {  # name theme slide filter items...
  local n="$1"; shift
  "$TMP/ph" "$1" "$2" "$3" "$TMP/x.ppm" "${@:4}"
  python3 "$ROOT/tools/carousel/ppm2png.py" "$TMP/x.ppm" "$OUT/$n.png" 1
  python3 "$ROOT/tools/carousel/ppm2png.py" "$TMP/x.ppm" "$OUT/$n-3x.png" 3
}
GBA="$C/gba_3767.crt $C/gba_84408.crt $C/gba_84406.crt $C/gba_3751.crt $C/gba_3790.crt"
GB="$C/gb_2970.crt $C/gb_2967.crt $C/gb_2976.crt $C/gb_69990.crt $C/gb_2973.crt"
GBC="$C/gbc_82619.crt $C/gbc_82379.crt $C/gbc_82375.crt $C/gbc_82606.crt $C/gbc_37208.crt"
NES="$C/nes_1250.crt $C/nes_1246.crt $C/nes_1245.crt $C/nes_1255.crt $C/nes_1256.crt"
MIX="$C/gb_2976.crt $C/gba_84406.crt $C/nes_1245.crt $C/gb_69990.crt $C/gba_3751.crt"
ALL="$C/gb_69990.crt $C/gbc_82606.crt $C/gba_3762.crt blank:$C/blank_gba.crt:My_Homebrew_Game blank:$C/blank_folder.crt:Hacks"
BLANK="$C/gba_3776.crt blank:$C/blank_folder.crt:Hacks blank:$C/blank_gba.crt:My_Homebrew_Game blank:$C/blank_gb.crt:Unknown_GB_game $C/gbc_36998.crt"
i=0
for T in red-dark red-white hout donker licht; do
  shot "$T-gba" $i 0 1 $GBA
  if [ $i -ge 2 ]; then
    shot "$T-gb" $i 0 2 $GB
    shot "$T-gbc" $i 0 3 $GBC
    shot "$T-alles" $i 0 0 $ALL
    shot "$T-leeg" $i 0 0 $BLANK
    for S in 192 128 64; do shot "$T-anim-$S" $i $S 1 $GBA; done
    shot "$T-nes" $i 0 4 $NES
    shot "$T-alles-nes" $i 0 0 $MIX
    shot "$T-nes-anim-128" $i 128 4 $NES
  fi
  i=$((i+1))
done
rm -rf "$TMP"
ls "$OUT" | wc -l
