#!/usr/bin/env python3
"""Convert EZ-Flash-Omega style 16bpp BMP thumbnails into SuperFW .cov files.

Input  : 120x80 (or any) uncompressed 16bpp X1R5G5B5 BMP, top-down or bottom-up.
Output : compact paletted ".cov" blob the firmware can blit straight into the
         Mode-4 framebuffer pane.

.cov layout (little endian):
    0  : magic  "SFCV" (4 bytes)
    4  : u16 width
    6  : u16 height
    8  : u16 ncolors      (palette entry count, <= 256-PAL_BASE)
   10  : u16 pal_base     (first BG palette index the pixels are biased to)
   12  : palette[ncolors] u16  GBA BGR555 (bit15 = 0)
   12+ncolors*2 : pixels[width*height] u8  (already biased by pal_base)

Because the pixel bytes are pre-biased by PAL_BASE, the firmware loads the
palette at MEM_PALETTE[PAL_BASE] and DMA-copies the pixel block straight into
the framebuffer -- no per-pixel offset needed at runtime.
"""
import argparse, os, struct, sys
from PIL import Image
try:
    import numpy as np
except ImportError:
    np = None

MAGIC      = b"SFCV"
PAL_BASE   = 32         # must match COVER_PAL_BASE in the firmware
NCOLORS    = 200        # palette slots reserved for one cover (32..231)
DEFAULT_W  = 96         # must match COVER_W
DEFAULT_H  = 64         # must match COVER_H


def read_rgb555_bmp(path):
    """Decode a 16bpp X1R5G5B5 BMP -> PIL RGB Image (numpy fast path + fallback)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"BM":
        raise ValueError(f"{path}: not a BMP")
    data_off = struct.unpack_from("<I", data, 0x0A)[0]
    width    = struct.unpack_from("<i", data, 0x12)[0]
    height   = struct.unpack_from("<i", data, 0x16)[0]
    bpp      = struct.unpack_from("<H", data, 0x1C)[0]
    if bpp != 16:
        raise ValueError(f"{path}: expected 16bpp, got {bpp}")
    top_down = height < 0
    h = abs(height)
    row_bytes = ((width * 2 + 3) // 4) * 4   # 4-byte aligned rows

    # Fast path: even width => rows are unpadded and contiguous.
    if np is not None and row_bytes == width * 2:
        px = np.frombuffer(data, dtype="<u2", count=width * h,
                           offset=data_off).reshape(h, width)
        r = (px >> 10) & 0x1F
        g = (px >> 5) & 0x1F
        b = px & 0x1F
        rgb = np.stack([(r << 3) | (r >> 2),
                        (g << 3) | (g >> 2),
                        (b << 3) | (b >> 2)], axis=-1).astype("u1")
        if not top_down:
            rgb = rgb[::-1]
        return Image.fromarray(rgb, "RGB")

    out = Image.new("RGB", (width, h))
    px = out.load()
    for ry in range(h):
        y = ry if top_down else (h - 1 - ry)
        base = data_off + ry * row_bytes
        for x in range(width):
            v = struct.unpack_from("<H", data, base + x * 2)[0]
            r = (v >> 10) & 0x1F
            g = (v >> 5) & 0x1F
            b = v & 0x1F
            px[x, y] = (r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2)
    return out


def to_bgr555(rgb):
    r, g, b = rgb
    return ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)


def convert(in_path, out_path, size=None, ncolors=NCOLORS, dither=False):
    img = read_rgb555_bmp(in_path)
    if size and tuple(size) != img.size:
        img = img.resize(size, Image.LANCZOS)
    d = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    q = img.quantize(colors=ncolors, method=Image.Quantize.MEDIANCUT, dither=d)
    pal = q.getpalette()[: ncolors * 3]
    pal = pal + [0] * (ncolors * 3 - len(pal))   # pad palettes with < ncolors colors
    idx = q.tobytes()
    w, h = q.size
    with open(out_path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<HHHH", w, h, ncolors, PAL_BASE))
        for i in range(ncolors):
            f.write(struct.pack("<H", to_bgr555(tuple(pal[i * 3 : i * 3 + 3]))))
        f.write(bytes((PAL_BASE + b) & 0xFF for b in idx))
    return q, img


def convert_tree(indir, outdir, size, ncolors, dither):
    """Convert every .bmp under indir into outdir/IMGS/{c0}/{c1}/{CODE}.cov."""
    done, fails = 0, []
    for root, _dirs, files in os.walk(indir):
        for fn in files:
            if not fn.lower().endswith(".bmp"):
                continue
            code = os.path.splitext(fn)[0]
            if len(code) < 4:
                continue
            code = code[:4].upper()
            sub = os.path.join(outdir, "IMGS", code[0], code[1])
            os.makedirs(sub, exist_ok=True)
            try:
                convert(os.path.join(root, fn), os.path.join(sub, code + ".cov"),
                        size, ncolors, dither)
                done += 1
                if done % 200 == 0:
                    print(f"  ... {done} converted")
            except Exception as e:
                fails.append((fn, str(e)))
    print(f"converted {done} covers -> {os.path.join(outdir, 'IMGS')}")
    if fails:
        print(f"{len(fails)} failed; first few: {fails[:5]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", help="input .bmp files (omit when using --tree)")
    ap.add_argument("-o", "--outdir", default=".")
    ap.add_argument("--tree", metavar="DIR", help="batch-convert every .bmp under DIR")
    ap.add_argument("--size", type=int, nargs=2, metavar=("W", "H"),
                    default=(DEFAULT_W, DEFAULT_H))
    ap.add_argument("--colors", type=int, default=NCOLORS)
    ap.add_argument("--dither", action="store_true")
    ap.add_argument("--preview", metavar="PNG", help="emit orig|quantized comparison")
    args = ap.parse_args()

    if args.tree:
        convert_tree(args.tree, args.outdir, args.size, args.colors, args.dither)
        return

    os.makedirs(args.outdir, exist_ok=True)
    rows = []
    for ip in args.inputs:
        code = os.path.splitext(os.path.basename(ip))[0]
        op = os.path.join(args.outdir, code + ".cov")
        q, orig = convert(ip, op, args.size, args.colors, args.dither)
        rows.append((code, orig, q.convert("RGB"), os.path.getsize(op)))
        print(f"{code}: {orig.size[0]}x{orig.size[1]} -> {op}  ({os.path.getsize(op)} bytes)")

    if args.preview:
        scale, pad, label_h = 3, 8, 14
        w, h = rows[0][1].size
        cell_w, cell_h = w * scale, h * scale + label_h
        sheet = Image.new("RGB", (cell_w * 2 + pad * 3, (cell_h + pad) * len(rows) + pad), (24, 24, 28))
        from PIL import ImageDraw
        dr = ImageDraw.Draw(sheet)
        for r, (code, orig, q, _sz) in enumerate(rows):
            y = pad + r * (cell_h + pad)
            for c, (img, tag) in enumerate([(orig, code + " original"), (q, "200-color")]):
                x = pad + c * (cell_w + pad)
                sheet.paste(img.resize((w * scale, h * scale), Image.NEAREST), (x, y + label_h))
                dr.text((x, y), tag, fill=(220, 220, 220))
        sheet.save(args.preview)
        print(f"\npreview -> {args.preview}")


if __name__ == "__main__":
    main()
