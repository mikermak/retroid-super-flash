#!/usr/bin/env python3
"""Tests the firmware lookup (src/lib_index.c, compiled for the PC) against a
base pack and the No-Intro DATs.

  python tools/library/test_index.py <basispakket-map>

Checks: GBA EU+US game codes -> one cart, every No-Intro name, every CRC
(GB/GBC, NES with and without iNES header), CRC32 code == zlib, NES header
skipping, and an odd file name (name fails, CRC finds it).
Needs gcc (WSL) to build the test program.
"""
import os
import random
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import libindex  # noqa: E402
import maak_basispakket as bp  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def wsl(p):
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def build(tmp):
    exe = os.path.join(tmp, "test_index")
    cmd = "gcc -O2 -I%s -o %s %s %s" % (wsl(os.path.join(ROOT, "src")), wsl(exe),
                                         wsl(os.path.join(HERE, "test_index.c")), wsl(os.path.join(ROOT, "src", "lib_index.c")))
    subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-c", cmd], check=True,
                   env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    return exe


def run(exe, *a):
    r = subprocess.run(["wsl", "-d", "Ubuntu", "--", wsl(exe)] + list(a), capture_output=True, text=True,
                       env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    return r.stdout.split()


def main():
    pk = sys.argv[1] if len(sys.argv) > 1 else os.path.join(bp.mb.DEF_DB, "basispakket-test")
    index = os.path.join(pk, "LIBRARY", "INDEX.BIN")
    tmp = tempfile.mkdtemp()
    exe = build(tmp)
    groups, _ = bp.build_groups(bp.mb.DEF_DB, list(bp.DATS), True)

    cases = []          # (description, key, expected cart or None for "same as")
    for system, gs in groups.items():
        fam = libindex.FAMILY[system]
        for gk, members in gs.items():
            for g in members:
                cases.append(("naam " + g["name"], libindex.key("N", fam, g["name"])))
                for r in g["roms"]:
                    if system == "gba" and r.get("serial"):
                        cases.append(("spelcode %s (%s)" % (r["serial"], g["name"]), libindex.key("S", fam, r["serial"])))
                    cases.append(("crc %s %s" % (r["crc"], r["file"]), libindex.key("C", fam, r["crc"])))
    keys = os.path.join(tmp, "keys.txt")
    open(keys, "wb").write(b"\n".join(k for _, k in cases) + b"\n")
    got = run(exe, "find", wsl(index), wsl(keys))
    ok = sum(1 for (_, k), g in zip(cases, got) if int(g) == (libindex.find(index, k) if libindex.find(index, k) is not None else -1))
    found = sum(1 for g in got if g != "-1")
    print("C-zoeken == Python-zoeken: %d/%d sleutels; gevonden: %d" % (ok, len(cases), found))

    # GBA: EU and US codes of one game -> the same cart.
    pairs = 0
    for gk, members in groups.get("gba", {}).items():
        codes = {r["serial"] for g in members for r in g["roms"] if r.get("serial")}
        carts = {libindex.find(index, libindex.key("S", "gba", c)) for c in codes}
        if len(codes) > 1:
            pairs += 1
            print("  GBA %-38s codes %-24s -> cart %s" % (gk[:38], ",".join(sorted(codes)), sorted(c for c in carts if c is not None)))
    print("  (%d GBA-spellen met meerdere spelcodes)" % pairs)

    # NES: headered and headerless CRC of a game -> same cart.
    for gk, members in list(groups.get("nes", {}).items())[:4]:
        crcs = {(r["file"][-4:], r["crc"]) for g in members for r in g["roms"]}
        carts = {libindex.find(index, libindex.key("C", "nes", c)) for _, c in crcs}
        print("  NES %-28s %d CRC's (.nes + .unh) -> cart %s" % (gk[:28], len(crcs), sorted(c for c in carts if c is not None)))

    # CRC32 implementation + iNES header skip.
    random.seed(1)
    data = bytes(random.getrandbits(8) for _ in range(70000))
    f = os.path.join(tmp, "rom.bin")
    open(f, "wb").write(data)
    c1 = run(exe, "crc", wsl(f))[0]
    open(f, "wb").write(b"NES\x1a" + bytes(12) + data)
    c2 = run(exe, "crc", wsl(f), "nes")[0]
    want = "%08X" % (zlib.crc32(data) & 0xFFFFFFFF)
    print("CRC32: firmware %s, NES met header %s, zlib %s -> %s" % (c1, c2, want, "OK" if c1 == c2 == want else "FOUT"))

    # Odd file name: name key misses, CRC key still finds the cart.
    odd = libindex.name_key("nes", "mario3 FINAL kopie.nes")
    g = groups["nes"].get("super mario bros 3") or next(iter(groups["nes"].values()))
    crc = [r["crc"] for m in g for r in m["roms"] if r["file"].endswith(".unh")][0]
    print("Rare naam 'mario3 FINAL kopie.nes': naam -> %s, CRC %s -> cart %s"
          % (libindex.find(index, odd), crc, libindex.find(index, libindex.key("C", "nes", crc))))


if __name__ == "__main__":
    main()
