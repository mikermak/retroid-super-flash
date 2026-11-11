#!/usr/bin/env python3
"""Preview: ROMs with home-made file names are still found (base pack index).

For each case the cart is looked up exactly like the firmware does
(src/lib_index.c via tools/library/test_index.c): game code (GBA), name, CRC.
The CRC of the "ROM" is taken from the No-Intro DAT (no ROM files here).
Then the carousel is rendered with tools/carousel/preview_host.
  python tools/carousel/preview_v7.py <basispakket-map> <out.png>
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "library"))
import libindex  # noqa: E402
import test_index as ti  # noqa: E402
import maak_basispakket as bp  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# (file name on the SD, family, system, game group, how the firmware finds it)
CASES = [
    ("pkmn emerald.gba", "gba", "gba", "pokemon emerald version", "spelcode"),
    ("mario3 FINAL kopie.nes", "nes", "nes", "super mario bros 3", "CRC (zonder NES-header)"),
    ("tetris_dx backup.gbc", "gb", "gbc", "tetris dx", "CRC"),
]


def main():
    pk, out = sys.argv[1], sys.argv[2]
    lib = os.path.join(pk, "LIBRARY")
    index = os.path.join(lib, "INDEX.BIN")
    groups, _ = bp.build_groups(bp.mb.DEF_DB, list(bp.DATS), True)
    tmp = tempfile.mkdtemp()
    exe = ti.build(tmp)
    ph = os.path.join(tmp, "ph")
    cmd = ("gcc -O2 -DCAROUSEL_HOST -I{s} -o {o} {h}/preview_host.c {s}/carousel_gfx.c "
           "{s}/fonts/font_render.c {s}/utf_util.c").format(s=ti.wsl(os.path.join(ROOT, "src")), o=ti.wsl(ph), h=ti.wsl(HERE))
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", cmd], check=True, env=dict(os.environ, MSYS_NO_PATHCONV="1"))

    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 22)
    bold = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
    tiles = []
    for fname, fam, system, gk, how in CASES:
        members = groups[system][gk]
        keys = [libindex.name_key(fam, fname)]
        if fam == "gba":
            keys.append(libindex.key("S", fam, members[0]["roms"][0]["serial"]))
        else:
            r = [r for m in members for r in m["roms"] if r["file"].endswith(".unh")] or members[0]["roms"]
            keys.append(libindex.key("C", fam, r[0]["crc"]))
        kf = os.path.join(tmp, "k.txt")
        open(kf, "wb").write(b"\n".join(keys) + b"\n")
        res = ti.run(exe, "find", ti.wsl(index), ti.wsl(kf))
        cart = next((int(x) for x in res if x != "-1"), None)
        crt = libindex.cart_path(lib, "C", cart)
        filt = {"gba": 1, "gb": 2, "gbc": 3, "nes": 4}[system]
        ppm = os.path.join(tmp, "x.ppm")
        subprocess.run(["wsl", "-d", "Ubuntu", "--", ti.wsl(ph), "3", "0", str(filt), ti.wsl(ppm),
                        "-", "-", ti.wsl(crt), "-", "-"], check=True, env=dict(os.environ, MSYS_NO_PATHCONV="1"))
        d = open(ppm, "rb").read().split(b"\n", 3)
        im = Image.frombytes("RGB", (240, 160), d[3]).resize((720, 480), Image.NEAREST)
        tiles.append((fname, "naam: %s  |  %s: cart %d" % ("niet gevonden" if res[0] == "-1" else "gevonden", how, cart), im))

    W = 720 * len(tiles) + 20 * (len(tiles) + 1)
    c = Image.new("RGB", (W, 480 + 110), (28, 30, 36))
    dr = ImageDraw.Draw(c)
    for i, (fname, line, im) in enumerate(tiles):
        x = 20 + i * 740
        dr.text((x, 14), "Bestand op de SD:  %s" % fname, font=bold, fill=(240, 240, 245))
        dr.text((x, 46), line, font=font, fill=(170, 175, 185))
        c.paste(im, (x, 90))
    c.save(out)
    print(out)


if __name__ == "__main__":
    main()
