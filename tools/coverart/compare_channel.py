#!/usr/bin/env python3
"""Render an EZ-Omega .bmp two ways to settle the channel order:
   - 'R-high' : interpret 16-bit pixel as X1R5G5B5 (current firmware)
   - 'R-low'  : interpret as X1B5G5R5 / GBA-native BGR (R and B swapped)
Ground truth: Pokemon Ruby is RED-dominant, FireRed's Charizard is ORANGE."""
import struct, sys
from PIL import Image, ImageDraw

LVL = [0, 6, 12, 19, 25, 31]


def q(c):  # 5-bit -> 8-bit
    return c << 3 | c >> 2


def render(bmp, swap):
    d = open(bmp, "rb").read()
    off = struct.unpack_from("<I", d, 10)[0]
    w = struct.unpack_from("<i", d, 18)[0]
    rh = struct.unpack_from("<i", d, 22)[0]
    td = rh < 0; h = abs(rh); rb = (w * 2 + 3) & ~3
    im = Image.new("RGB", (w, h)); px = im.load()
    for sy in range(h):
        base = off + sy * rb; dy = sy if td else h - 1 - sy
        for x in range(w):
            v = struct.unpack_from("<H", d, base + x * 2)[0]
            hi = (v >> 10) & 31; mid = (v >> 5) & 31; lo = v & 31
            # quantize to the 6-level cube the firmware uses, then expand
            def cube(c):
                return LVL[(c * 6) >> 5]
            if swap:   # R-low: red=lo, blue=hi
                px[x, dy] = (q(cube(lo)), q(cube(mid)), q(cube(hi)))
            else:      # R-high: red=hi, blue=lo
                px[x, dy] = (q(cube(hi)), q(cube(mid)), q(cube(lo)))
    return im


def main():
    out = sys.argv[1]
    inputs = sys.argv[2:]
    s, pad, lh = 3, 8, 14
    rows = [(p.split("/")[-1], render(p, False), render(p, True)) for p in inputs]
    w, h = rows[0][1].size
    cw, ch = w * s, h * s + lh
    sheet = Image.new("RGB", (cw * 2 + pad * 3, (ch + pad) * len(rows) + pad), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    for i, (name, a, b) in enumerate(rows):
        y = pad + i * (ch + pad)
        for c, (im, tag) in enumerate([(a, name + "  R-high (current)"), (b, name + "  R-low (swapped)")]):
            x = pad + c * (cw + pad)
            sheet.paste(im.resize((w * s, h * s), Image.NEAREST), (x, y + lh))
            dr.text((x, y), tag, fill=(220, 220, 220))
    sheet.save(out)
    print(f"ok -> {out}")


if __name__ == "__main__":
    main()
