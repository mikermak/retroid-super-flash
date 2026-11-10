#!/usr/bin/env python3
"""Convert a P6 PPM to PNG (optionally scaled up by an integer factor).
Standard library only.  Usage: ppm2png.py in.ppm out.png [scale]"""
import struct, sys, zlib

def read_ppm(fn):
    data = open(fn, "rb").read()
    parts = data.split(b"\n", 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3]

def write_png(fn, w, h, rgb, scale=1):
    rows = []
    for y in range(h):
        row = rgb[y * w * 3:(y + 1) * w * 3]
        if scale > 1:
            row = b"".join(row[x * 3:x * 3 + 3] * scale for x in range(w))
        for _ in range(scale):
            rows.append(b"\x00" + row)
    raw = zlib.compress(b"".join(rows), 9)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", raw) + chunk(b"IEND", b"")
    open(fn, "wb").write(png)

if __name__ == "__main__":
    w, h, rgb = read_ppm(sys.argv[1])
    write_png(sys.argv[2], w, h, rgb, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
