"""Turns cartridge renders into the .CRT files the firmware shows.

A .CRT holds one game: title + metadata strings and 5 pre-rendered poses
(front, half-turned left/right, side left/right). Every pose is already in the
exact format the GBA draws: 8-bit pixels with indices into that pose's fixed
palette slot (so no colour conversion on the GBA), one opaque span per row
(transparent around the cart) and a 15-bit palette.

File layout (little endian), see src/library.h in the firmware:
  0x000 "RCRT" u8 version, u8 system (0 GBA, 1 GB, 2 GBC), u8 npose, u8 flags
  0x008 title[48]  0x038 year[8]  0x040 publisher[32]  0x060 players[8]
  0x068 genre[24]  0x080 label rect of the front pose: u8 x, y, w, h
  0x084 pad[12]
  0x090 pose table: npose x {u32 offset, u32 size, u8 w, h, ax, ay, ncolors, base, u16 pad}
  data: per pose: palette (ncolors x u16), spans (h x {u8 x0, u8 len}), pixels; 4-aligned.
"""
import json
import os
import struct

from PIL import Image, ImageEnhance, ImageFilter

VERSION = 1
SYSTEMS = {"gba": 0, "gb": 1, "gbc": 2, "folder": 3, "nes": 4}
HEADER_SIZE = 0x90

# Pose order + palette slot (first index, colour count) in MEM_PALETTE.
POSES = [
    ("F", 20, 92),
    ("ML", 112, 32),
    ("MR", 144, 32),
    ("L", 176, 32),
    ("R", 208, 32),
]

# Render setup shared with render_carts.py (canvas + anchor in final pixels).
RENDER_POSES = [
    {"name": "F",  "yaw": 0,   "scale": 1.0,  "canvas": [150, 104], "anchor": [75, 97]},
    {"name": "ML", "yaw": 32,  "scale": 0.84, "canvas": [130, 100], "anchor": [65, 95]},
    {"name": "MR", "yaw": -32, "scale": 0.84, "canvas": [130, 100], "anchor": [65, 95]},
    {"name": "L",  "yaw": 58,  "scale": 0.70, "canvas": [110, 92],  "anchor": [55, 88]},
    {"name": "R",  "yaw": -58, "scale": 0.70, "canvas": [110, 92],  "anchor": [55, 88]},
]


def to555(c):
    return ((c[0] >> 3) & 31) | (((c[1] >> 3) & 31) << 5) | (((c[2] >> 3) & 31) << 10)


def from555(v):
    r, g, b = v & 31, (v >> 5) & 31, (v >> 10) & 31
    return ((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2))


def prepare(path, ss):
    """Downscale a supersampled RGBA render; returns (RGBA image, alpha mask)."""
    im = Image.open(path).convert("RGBA")
    w, h = im.width // ss, im.height // ss
    small = im.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    rgb = small.convert("RGB").filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=1))
    # A little extra colour and contrast: the GBA screen is less vivid than a PC.
    rgb = ImageEnhance.Contrast(ImageEnhance.Color(rgb).enhance(1.15)).enhance(1.06)
    mask = small.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    return rgb, mask


def quantize_pose(rgb, mask, ncolors):
    """Adaptive palette of `ncolors` 15-bit colours + Floyd-Steinberg dithering."""
    bbox = mask.getbbox()
    if not bbox:
        return None
    rgb = rgb.crop(bbox)
    mask = mask.crop(bbox)
    # Fill the transparent area with the average cart colour so it does not
    # steal palette entries.
    px = [p for p, a in zip(rgb.getdata(), mask.getdata()) if a]
    avg = tuple(sum(c[i] for c in px) // len(px) for i in range(3))
    filled = Image.new("RGB", rgb.size, avg)
    filled.paste(rgb, (0, 0), mask)

    first = filled.quantize(colors=ncolors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = first.getpalette()[:ncolors * 3]
    pal555 = []
    for i in range(ncolors):
        c = tuple(pal[i * 3:i * 3 + 3]) if i * 3 + 2 < len(pal) else (0, 0, 0)
        v = to555(c)
        if v not in pal555:
            pal555.append(v)
    palimg = Image.new("P", (1, 1))
    # Pad the 256-entry palette by repeating our colours, so whatever index
    # Pillow picks maps back with "% len".
    flat = []
    for i in range(256):
        flat += list(from555(pal555[i % len(pal555)]))
    palimg.putpalette(flat)
    idx = filled.quantize(palette=palimg, dither=Image.Dither.FLOYDSTEINBERG)
    n = len(pal555)
    idx = idx.point(lambda v: v % n)
    return bbox, idx, mask, pal555


def encode_pose(rgb, mask, anchor, base, ncolors):
    q = quantize_pose(rgb, mask, ncolors)
    if not q:
        raise ValueError("lege render")
    (x0, y0, x1, y1), idx, mask, pal = q
    w, h = x1 - x0, y1 - y0
    if w > 255 or h > 255:
        raise ValueError("pose te groot")
    pixels = idx.load()
    m = mask.load()
    spans, data = bytearray(), bytearray()
    for y in range(h):
        xs = [x for x in range(w) if m[x, y]]
        if not xs:
            spans += bytes((0, 0))
            continue
        a, b = xs[0], xs[-1] + 1
        spans += bytes((a, b - a))
        data += bytes(base + pixels[x, y] for x in range(a, b))
    blob = b"".join(struct.pack("<H", v) for v in pal) + bytes(spans) + bytes(data)
    blob += b"\0" * (-len(blob) % 4)
    ax, ay = anchor[0] - x0, anchor[1] - y0
    return blob, (w, h, max(0, min(255, ax)), max(0, min(255, ay)), len(pal), base), (x0, y0)


def _str(s, n):
    b = (s or "").encode("utf-8")[:n - 1]
    while True:   # never cut a UTF-8 sequence in half
        try:
            b.decode("utf-8")
            break
        except UnicodeDecodeError:
            b = b[:-1]
    return b + b"\0" * (n - len(b))


def write_crt(render_dir, info, out_path):
    with open(os.path.join(render_dir, "poses.json")) as f:
        meta = json.load(f)
    ss = meta.get("supersample", 1)
    blobs, table = [], []
    label = (0, 0, 0, 0)
    for name, base, ncol in POSES:
        rgb, mask = prepare(os.path.join(render_dir, name + ".png"), ss)
        pm = meta["poses"][name]
        blob, ent, (cx, cy) = encode_pose(rgb, mask, pm["anchor"], base, ncol)
        if name == "F" and "label" in pm:
            lx, ly, lw, lh = pm["label"]
            label = (max(0, lx - cx), max(0, ly - cy), min(255, lw), min(255, lh))
        blobs.append(blob)
        table.append(ent)

    hdr = bytearray(b"RCRT")
    hdr += bytes((VERSION, SYSTEMS[meta["system"]], len(POSES), 0))
    hdr += _str(info.get("name"), 48) + _str(info.get("year"), 8) + _str(info.get("publisher"), 32)
    hdr += _str(info.get("players"), 8) + _str(info.get("genre"), 24)
    hdr += bytes(label) + b"\0" * 12
    assert len(hdr) == HEADER_SIZE
    off = HEADER_SIZE + 16 * len(POSES)
    tbl = bytearray()
    for blob, (w, h, ax, ay, n, base) in zip(blobs, table):
        tbl += struct.pack("<IIBBBBBBH", off, len(blob), w, h, ax, ay, n, base, 0)
        off += len(blob)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(hdr + tbl + b"".join(blobs))
    return off


def read_crt(path):
    """Decodes a .CRT back to RGBA images (for previews / checks)."""
    d = open(path, "rb").read()
    assert d[:4] == b"RCRT"
    out = {"system": d[5], "title": d[8:56].split(b"\0")[0].decode("utf-8", "replace"), "poses": []}
    for i in range(d[6]):
        off, size, w, h, ax, ay, n, base, _ = struct.unpack_from("<IIBBBBBBH", d, HEADER_SIZE + 16 * i)
        pal = [from555(struct.unpack_from("<H", d, off + 2 * k)[0]) for k in range(n)]
        sp = off + 2 * n
        px = sp + 2 * h
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for y in range(h):
            x0, ln = d[sp + 2 * y], d[sp + 2 * y + 1]
            for x in range(ln):
                im.putpixel((x0 + x, y), pal[d[px] - base] + (255,))
                px += 1
        out["poses"].append({"img": im, "anchor": (ax, ay)})
    return out
