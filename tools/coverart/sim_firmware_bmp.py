#!/usr/bin/env python3
"""Mirror coverart.c exactly: decode an X1R5G5B5 .bmp the way the firmware does,
map each pixel to the fixed 6x6x6 (216) cube palette, and render what the GBA
would actually show. Builds a 'true BMP color' vs 'firmware 216-color' sheet."""
import struct, sys
from PIL import Image, ImageDraw

LVL = [0, 6, 12, 19, 25, 31]
CUBE = [(LVL[b] << 10) | (LVL[g] << 5) | LVL[r]
        for r in range(6) for g in range(6) for b in range(6)]


def cube_idx(v):
    r = (v >> 10) & 31; g = (v >> 5) & 31; b = v & 31
    return ((r * 6) >> 5) * 36 + ((g * 6) >> 5) * 6 + ((b * 6) >> 5)


def read(bmp):
    d = open(bmp, "rb").read()
    off = struct.unpack_from("<I", d, 10)[0]
    w = struct.unpack_from("<i", d, 18)[0]
    rh = struct.unpack_from("<i", d, 22)[0]
    td = rh < 0; h = abs(rh); rb = (w * 2 + 3) & ~3
    orig = Image.new("RGB", (w, h)); sim = Image.new("RGB", (w, h))
    po = orig.load(); ps = sim.load()
    for sy in range(h):
        base = off + sy * rb; dy = sy if td else h - 1 - sy
        for x in range(w):
            v = struct.unpack_from("<H", d, base + x * 2)[0]
            r = (v >> 10) & 31; g = (v >> 5) & 31; b = v & 31
            po[x, dy] = (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)
            c = CUBE[cube_idx(v)]; cr = c & 31; cg = (c >> 5) & 31; cb = (c >> 10) & 31
            ps[x, dy] = (cr << 3 | cr >> 2, cg << 3 | cg >> 2, cb << 3 | cb >> 2)
    return orig, sim


def main():
    out = sys.argv[1]
    inputs = sys.argv[2:]
    imgs = [read(p) for p in inputs]
    s, pad, lh = 3, 8, 14
    w, h = imgs[0][0].size
    cw, ch = w * s, h * s + lh
    sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + pad) * len(imgs) + pad), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    for i, (o, sm) in enumerate(imgs):
        y = pad + i * (ch + pad)
        for c, (im, tag) in enumerate([(o, "BMP original"), (sm, "firmware 216-color")]):
            x = pad + c * (cw + pad)
            sheet.paste(im.resize((w * s, h * s), Image.NEAREST), (x, y + lh))
            dr.text((x, y), tag, fill=(220, 220, 220))
    sheet.save(out)
    print(f"ok -> {out}  (pane {w}x{h})")


if __name__ == "__main__":
    main()
