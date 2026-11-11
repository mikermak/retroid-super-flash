"""Library index (INDEX.BIN / MY.BIN) -- the PC side of src/lib_index.c.

Keys: "S:gba:<GAMECODE>", "N:<family>:<rom file name, lower case>",
"C:<family>:<CRC32 hex, upper case>"; families gba, gb (GB + GBC), nes.
Each key is hashed twice (FNV-1a, two seeds); the file is a sorted table
{u32 h1, u32 h2, u32 cart} behind a 16-byte header ("RIDX", 1, count, 0).
Cart n is stored as <LIBRARY>/<C|M>/<n >> 8 as %02X>/<n as %04X>.CRT.
"""
import os
import struct

SEED1, SEED2 = 0x811C9DC5, 0x050C5D1F
KEY_MAX = 127                    # firmware key buffer is 128 bytes
FAMILY = {"gba": "gba", "gb": "gb", "gbc": "gb", "nes": "nes"}


def fnv(data, seed):
    h = seed
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def key(kind, family, value):
    v = value.encode("utf-8")
    if kind == "N":
        v = bytes(c + 32 if 65 <= c <= 90 else c for c in v)
    k = kind.encode() + b":" + family.encode() + b":" + v
    return k[:KEY_MAX]


def name_key(family, file_name):
    """N-key from a ROM file name (extension stripped, like the firmware)."""
    base = os.path.basename(file_name)
    stem, ext = os.path.splitext(base)
    return key("N", family, stem if ext and stem else base)


def write_index(path, pairs):
    """pairs: [(key bytes, cart)] in priority order (first wins on duplicates)."""
    seen = {}
    for k, cart in pairs:
        hk = (fnv(k, SEED1), fnv(k, SEED2))
        if hk not in seen:
            seen[hk] = cart
    rows = sorted(seen.items())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"RIDX" + struct.pack("<III", 1, len(rows), 0))
        for (h1, h2), cart in rows:
            f.write(struct.pack("<III", h1, h2, cart))
    return len(rows)


def cart_path(library, letter, cart):
    return os.path.join(library, letter, "%02X" % (cart >> 8), "%04X.CRT" % cart)


def find(path, k):
    """Python twin of libidx_find (for tests)."""
    d = open(path, "rb").read()
    assert d[:4] == b"RIDX"
    n = struct.unpack_from("<I", d, 8)[0]
    h = (fnv(k, SEED1), fnv(k, SEED2))
    lo, hi = 0, n - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        a, b, c = struct.unpack_from("<III", d, 16 + mid * 12)
        if (a, b) == h:
            return c
        if (a, b) < h:
            lo = mid + 1
        else:
            hi = mid - 1
    return None
