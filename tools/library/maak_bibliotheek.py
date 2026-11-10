#!/usr/bin/env python3
"""Maakt de spellenbibliotheek (3D-cartridges met echt label) voor de
Retroid Super Flash carrousel.

Gebruik (Windows, vanuit de map superfw-slot):
  python tools/library/maak_bibliotheek.py --roms F:\\ --uit C:\\pad\\naar\\LIBRARY

Daarna de map LIBRARY naar de hoofdmap van de SD-kaart kopieren.

Wat het doet, per spel:
 1. ROM lezen (CRC32 + header: GBA-spelcode of GB-titel/checksum).
 2. Opzoeken bij Screenscraper (CRC + systeem, anders de bestandsnaam, anders
    zoeken op titel). Alles wordt bewaard in --db, dus nooit twee keer gevraagd.
 3. Het label (support-texture) downloaden.
 4. In Blender de cartridge renderen met dat label (5 standen).
 5. Omzetten naar het GBA-formaat (.CRT) en in --uit zetten:
      GBA:     LIBRARY/<eerste letter spelcode>/<SPELCODE>.CRT
      GB/GBC:  LIBRARY/G<x>/<HEADERHASH>.CRT
      zonder ROM (--testset): LIBRARY/N/<naam>.CRT  (zelfde naam als het romsbestand)

De database, labels en renders blijven in --db (alleen lokaal: labels zijn
auteursrechtelijk beschermd en horen niet in git of een release).

Extra:
  --testset tools/library/testset.txt   spellen op naam, zonder ROMs (om te testen)
  --blanco res/carts.bin                 lege carts voor de firmware maken
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss  # noqa: E402
import pack  # noqa: E402

RETROID = os.path.abspath(os.path.join(HERE, "..", "..", ".."))           # ...\firmware
DOCS = os.path.dirname(RETROID)                                           # ...\Retroid
DEF_DB = os.path.join(RETROID, "library-db")
DEF_ENV = os.path.join(DOCS, "builders", "game-label-configurator", ".env.local")
DEF_BLENDER = os.path.join(DOCS, "builders", "gb-builder-3d", ".tools", "blender-5.2.2-windows-x64", "blender.exe")
RENDER_VERSION = 1

EXTS = {".gba": "gba", ".agb": "gba", ".gb": "gb", ".gbc": "gbc", ".cgb": "gbc"}


# ---------------------------------------------------------------------------
# ROM reading + keys (must match src/menu_carousel.h)

def fnv1a(data):
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def read_rom(path):
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    system = EXTS[ext]
    g = {"path": path, "file": os.path.basename(path), "system": system, "size": len(data),
         "crc": "%08X" % (zlib.crc32(data) & 0xFFFFFFFF), "cgb": 0}
    if system == "gba" and len(data) >= 0xC0:
        code = data[0xAC:0xB0].decode("latin-1")
        g["title"] = data[0xA0:0xAC].split(b"\0")[0].decode("latin-1").strip()
        g["code"] = code
        if re.fullmatch(r"[0-9A-Za-z]{4}", code):
            g["key"] = "%s/%s" % (code[0].upper(), code.upper())
    elif len(data) >= 0x150:
        g["title"] = data[0x134:0x143].split(b"\0")[0].decode("latin-1").strip()
        g["cgb"] = data[0x143]
        g["key"] = "G%X/%08X" % (fnv1a(data[0x134:0x150]) >> 28, fnv1a(data[0x134:0x150]))
    return g


def scan_roms(root):
    games = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".") and d.upper() not in ("LIBRARY", "IMGS", "SYSTEM VOLUME INFORMATION")]
        for f in sorted(fn):
            if os.path.splitext(f)[1].lower() in EXTS:
                p = os.path.join(dp, f)
                if os.path.getsize(p) <= 64 * 1024 * 1024:
                    games.append(read_rom(p))
    return games


def read_testset(path):
    games = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            system, name = [x.strip() for x in line.split("|", 1)]
            games.append({"system": system, "file": name + {"gba": ".gba", "gb": ".gb", "gbc": ".gbc"}[system],
                          "nointro": name, "cgb": 0x80 if system == "gbc" else 0})
    return games


# ---------------------------------------------------------------------------
# Cartridge colours (sRGB); special editions by game code / title.

SPECIAL_GBA = {"AXV": ("b3202a", True), "AXP": ("2350b0", True), "BPE": ("2f9a63", True),
               "BPR": ("cc3b2c", True), "BPG": ("6cb34a", True)}
SPECIAL_NAME = [
    (r"pokemon.*\bred\b", "b8262c", False), (r"pokemon.*\bblue\b", "2a52a8", False),
    (r"pokemon.*yellow", "e8c42c", False), (r"pokemon.*\bgold\b", "c9a03a", False),
    (r"pokemon.*silver", "b9bdc6", False), (r"pokemon.*crystal", "86cde9", True),
    (r"pokemon.*ruby", "b3202a", True), (r"pokemon.*sapphire", "2350b0", True),
    (r"pokemon.*emerald", "2f9a63", True), (r"pokemon.*firered", "cc3b2c", True),
    (r"pokemon.*leafgreen", "6cb34a", True),
]


def srgb_to_linear(hexs):
    out = []
    for i in (0, 2, 4):
        c = int(hexs[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def cart_colour(g, name):
    code = (g.get("code") or "")[:3].upper()
    if code in SPECIAL_GBA:
        h, clear = SPECIAL_GBA[code]
        return srgb_to_linear(h), clear
    low = (name or g.get("nointro") or g.get("file") or "").lower().replace("\u00e9", "e")
    for pat, h, clear in SPECIAL_NAME:
        if re.search(pat, low):
            return srgb_to_linear(h), clear
    if g["system"] == "gba":
        return srgb_to_linear("46474c"), False
    if g["system"] == "gbc" or g.get("cgb", 0) & 0x80:
        return srgb_to_linear("1e1e22"), False     # Game Boy Color carts are black
    return srgb_to_linear("a2a2a8"), False         # Classic grey Game Boy cart


# ---------------------------------------------------------------------------

def safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip()


def lookup(client, g, region):
    """Screenscraper lookup: CRC, file name, then a title search."""
    system = g["system"]
    romnom = (g.get("nointro") or os.path.splitext(g["file"])[0]) + ".zip"
    jeu = None
    if g.get("crc"):
        jeu = client.game_info(system, romnom=romnom, crc=g["crc"], size=g["size"])
    if not jeu:
        jeu = client.game_info(system, romnom=romnom)
    if not jeu and system == "gbc":
        # Dual-mode games are sometimes filed as Game Boy.
        jeu = client.game_info("gb", romnom=romnom)
    return jeu


def main():
    ap = argparse.ArgumentParser(description="Maak de 3D-cartridgebibliotheek voor de Retroid Super Flash.")
    ap.add_argument("--roms", help="map met .gba/.gb/.gbc (bv. de SD-kaart)")
    ap.add_argument("--testset", help="tekstbestand 'systeem|No-Intro-naam' (zonder ROMs)")
    ap.add_argument("--uit", help="uitvoermap (wordt LIBRARY op de SD)")
    ap.add_argument("--db", default=DEF_DB, help="database/cache-map (alleen lokaal)")
    ap.add_argument("--env", default=DEF_ENV, help=".env.local met de Screenscraper-gegevens")
    ap.add_argument("--blender", default=DEF_BLENDER)
    ap.add_argument("--regio", default="eu", choices=["eu", "us", "jp"])
    ap.add_argument("--samples", type=int, default=48, help="Blender render-samples")
    ap.add_argument("--blanco", help="maak alleen de lege carts voor de firmware (res/carts.bin)")
    args = ap.parse_args()

    os.makedirs(args.db, exist_ok=True)
    t_start = time.time()

    if args.blanco:
        make_blanks(args)
        return

    if not args.uit or not (args.roms or args.testset):
        ap.error("geef --uit en --roms (of --testset)")

    games = scan_roms(args.roms) if args.roms else read_testset(args.testset)
    print("%d spellen gevonden" % len(games))

    client = ss.Screenscraper(args.env, os.path.join(args.db, "ss_cache"), log=print)
    dbfile = os.path.join(args.db, "library.json")
    db = json.load(open(dbfile, encoding="utf-8")) if os.path.exists(dbfile) else {}

    jobs, todo = [], []
    for i, g in enumerate(games):
        label = g.get("nointro") or g["file"]
        print("[%d/%d] %s" % (i + 1, len(games), label))
        region = ss.region_from_name(g.get("nointro") or g["file"]) if (g.get("nointro") or "(" in g["file"]) else args.regio
        try:
            jeu = lookup(client, g, region)
        except ss.SSError as e:
            print("    Screenscraper: %s" % e)
            jeu = None
        info = ss.describe(jeu, region) if jeu else {"name": os.path.splitext(g["file"])[0]}
        if not jeu:
            print("    niet gevonden: lege cart met de naam")
        tex = None
        if jeu:
            prefs = ss.REGION_ORDER.get(region, ss.REGION_ORDER["eu"])
            m = ss.pick_media(jeu, "support-texture", prefs)
            if m:
                ext = m.get("format") or "png"
                dest = os.path.join(args.db, "media", str(info["ssid"]), "label_%s.%s" % (m.get("region", "x"), ext))
                try:
                    tex = client.download(m["url"], dest)
                except ss.SSError as e:
                    print("    label downloaden mislukt: %s" % e)
            else:
                print("    geen label-scan beschikbaar")
        body, clear = cart_colour(g, info.get("name"))
        ident = "%s_%s" % (g["system"], info.get("ssid") or safe_name(info["name"]))
        rdir = os.path.join(args.db, "renders", ident)
        stamp = json.dumps([RENDER_VERSION, tex and os.path.basename(tex), body, clear, g["system"]])
        sfile = os.path.join(rdir, "stamp.json")
        if not (os.path.exists(sfile) and open(sfile).read() == stamp):
            jobs.append({"system": g["system"], "body": body, "clear": clear, "label": tex, "out": rdir,
                         "_stamp": stamp})
        todo.append((g, info, rdir, tex))
        db[g.get("key") or "N/" + safe_name(os.path.splitext(g["file"])[0])] = dict(
            info, system=g["system"], file=g["file"], crc=g.get("crc"), label=bool(tex))

    t_lookup = time.time()
    if jobs:
        print("Renderen van %d cartridges in Blender..." % len(jobs))
        render(args, jobs)
    t_render = time.time()

    n = 0
    for g, info, rdir, tex in todo:
        crt = os.path.join(args.db, "crt", os.path.basename(rdir) + ".crt")
        if not os.path.exists(os.path.join(rdir, "poses.json")):
            print("    render ontbreekt, overgeslagen: %s" % info.get("name"))
            continue
        pack.write_crt(rdir, info, crt)
        targets = []
        if g.get("key"):
            targets.append(g["key"] + ".CRT")
        else:
            targets.append("N/" + safe_name(os.path.splitext(g["file"])[0]) + ".CRT")
        for t in targets:
            dest = os.path.join(args.uit, *t.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(crt, dest)
            n += 1
    with open(dbfile, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)

    t_end = time.time()
    print("\nKlaar: %d cartridges in %s" % (n, args.uit))
    print("Tijd: opzoeken %.0fs, renderen %.0fs (%d nieuw), inpakken %.0fs, totaal %.0fs"
          % (t_lookup - t_start, t_render - t_lookup, len(jobs), t_end - t_render, t_end - t_start))
    print("Screenscraper-verzoeken deze keer: %d" % client.requests)


def render(args, jobs):
    cfg = {"supersample": 3, "samples": args.samples, "poses": pack.RENDER_POSES,
           "jobs": [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]}
    os.makedirs(os.path.join(args.db, "tmp"), exist_ok=True)
    jf = os.path.join(args.db, "tmp", "jobs_%d.json" % os.getpid())
    with open(jf, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    script = os.path.join(HERE, "render_carts.py")
    p = subprocess.Popen([args.blender, "-b", "--factory-startup", "--python", script, "--", jf],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    done = 0
    for line in p.stdout:
        if line.startswith("RENDERED"):
            done += 1
            print("    gerenderd %d/%d" % (done, len(jobs)), flush=True)
        elif "Error" in line or "Traceback" in line:
            print("    blender: " + line.rstrip())
    p.wait()
    for j in jobs:
        if os.path.exists(os.path.join(j["out"], "poses.json")):
            with open(os.path.join(j["out"], "stamp.json"), "w") as f:
                f.write(j["_stamp"])


def make_blanks(args):
    """Blank carts (one per system) for the firmware: res/carts.bin."""
    jobs = []
    for system, col in (("gba", "46474c"), ("gb", "a2a2a8"), ("gbc", "1e1e22"), ("folder", "e2b85e")):
        jobs.append({"system": system, "body": srgb_to_linear(col), "clear": False, "label": None,
                     "out": os.path.join(args.db, "renders", "blank_" + system), "_stamp": "blank"})
    render(args, jobs)
    blobs = []
    for j in jobs:
        crt = os.path.join(args.db, "crt", "blank_%s.crt" % j["system"])
        pack.write_crt(j["out"], {"name": ""}, crt)
        blobs.append(open(crt, "rb").read())
    # "RCRB", count, offsets, then the .CRT files (4-aligned).
    hdr = b"RCRB" + struct.pack("<I", len(blobs))
    off = len(hdr) + 4 * len(blobs)
    offs, body = [], b""
    for b in blobs:
        offs.append(off + len(body))
        body += b + b"\0" * (-len(b) % 4)
    data = hdr + b"".join(struct.pack("<I", o) for o in offs) + body
    with open(args.blanco, "wb") as f:
        f.write(data)
    print("lege carts: %s (%d bytes)" % (args.blanco, len(data)))


if __name__ == "__main__":
    main()
