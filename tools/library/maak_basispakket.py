#!/usr/bin/env python3
"""Maakt het BASISPAKKET: kant-en-klare 3D-carts voor (bijna) alle officiele
EU- en US-spellen van GBA, GB, GBC en NES, voor plug-and-play levering.

Hervatbaar: elke run gaat verder waar de vorige stopte (alles wordt bewaard in
--db). Stopt vanzelf als het Screenscraper-dagquotum (bijna) op is.

  python tools/library/maak_basispakket.py                 # volledige run
  python tools/library/maak_basispakket.py --steekproef    # ~40 spellen, test

Uitvoer (--uit, standaard firmware\\library-db\\basispakket):
  LIBRARY\\INDEX.BIN          index: spelcode / No-Intro-naam / CRC -> cart
  LIBRARY\\C\\xx\\xxxx.CRT     de carts (een per spel, EU+US delen er een)
  LIBRARY\\_BLANK\\BLANK.BIN   lege carts (voor spellen zonder cart)
  LEESMIJ.txt, CREDITS.txt

Spellijsten: No-Intro DAT's (libretro-database) in firmware\\library-db\\dats.
Infokaart: alleen feiten (geen Screenscraper-beschrijvingen in het pakket).
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss  # noqa: E402
import pack  # noqa: E402
import libindex  # noqa: E402
import maak_bibliotheek as mb  # noqa: E402

DATS = {
    "gba": "Nintendo - Game Boy Advance.dat",
    "gb": "Nintendo - Game Boy.dat",
    "gbc": "Nintendo - Game Boy Color.dat",
    "nes": "Nintendo - Nintendo Entertainment System.dat",
}

# --- Filter rules -----------------------------------------------------------
# Only official releases for the USA / Europe (incl. single European countries).
OK_REGIONS = {"USA", "Europe", "World", "Germany", "France", "Spain", "Italy", "Netherlands",
              "Sweden", "UK", "United Kingdom", "Denmark", "Norway", "Finland", "Portugal",
              "Austria", "Switzerland", "Belgium", "Scandinavia", "Greece", "Poland"}
# Anything with one of these words in a tag is dropped.
BAD_TAGS = re.compile(
    r"\b(Beta|Proto|Prototype|Demo|Sample|Kiosk|Unl|Pirate|Hack|BIOS|Aftermarket|Homebrew|"
    r"Virtual Console|Switch Online|Classic Mini|Collection|Mini Mix|Anniversary|Retro-Bit|"
    r"Limited Run|Evercade|GameCube|iQue|Program|Test Program|Debug|Promo|Competition|"
    r"e-Reader|PlayChoice|PC10|VS System|Arcade|Alt|Sachen|Taikenban|Trial|"
    # Homebrew / new indie releases and rips from later re-releases:
    r"Compo|Jam|Byte-Off|Patreon|Steam|GOG|Switch|Digital|Incube8|ModRetro|Chromatic|"
    r"Flashback|Animal Crossing|Namco Museum|Collector|Capcom Town|Emulator Optimized|"
    r"Cheat|Batteryless|Alpha|Music|Album|Showdown|REMIX|Double Action|Flash64|DSI|"
    r"Solid State)\b", re.I)
# Official releases use "(Rev N)"; "(v1.2)" style versions are homebrew.
VERSION_TAG = re.compile(r"^v\d", re.I)
REGION_PREF = ["Europe", "World", "USA, Europe", "USA"]   # label preference

STEEKPROEF = {
    "gba": ["pokemon emerald version", "pokemon firered version", "metroid fusion",
            "super mario advance 4 super mario bros 3", "mario kart super circuit",
            "golden sun", "advance wars", "kirby nightmare in dream land",
            "legend of zelda the the minish cap", "castlevania aria of sorrow", "wario land 4"],
    "gb": ["tetris", "super mario land", "legend of zelda the link s awakening",
           "pokemon red version", "kirby s dream land", "metroid ii return of samus",
           "dr mario", "donkey kong land", "wario land super mario land 3"],
    "gbc": ["pokemon gold version", "pokemon crystal version", "tetris dx",
            "legend of zelda the oracle of seasons", "super mario bros deluxe",
            "wario land 3", "pokemon pinball", "shantae", "mario tennis"],
    "nes": ["super mario bros", "super mario bros 3", "legend of zelda the", "metroid",
            "mega man 2", "castlevania", "duck hunt", "punch out", "kirby s adventure",
            "zelda ii the adventure of link", "tetris"],
}


def parse_dat(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    games = []
    for m in re.finditer(r'^game \(\n(.*?)^\)', txt, re.S | re.M):
        body = m.group(1)
        name = re.search(r'^\tname "(.*)"$', body, re.M)
        if not name:
            continue
        g = {"name": name.group(1), "roms": []}
        sm = re.search(r'^\tserial "(.*)"$', body, re.M)
        if sm:
            g["serial"] = sm.group(1)
        for r in re.finditer(r'rom \( name "(.*?)" size (\d+) crc ([0-9A-Fa-f]{8})(.*?)\)$', body, re.M):
            ser = re.search(r'serial "(.*?)"', r.group(4))
            g["roms"].append({"file": r.group(1), "size": int(r.group(2)), "crc": r.group(3).upper(),
                              "serial": ser.group(1) if ser else g.get("serial")})
        games.append(g)
    return games


def tags(name):
    return re.findall(r"\(([^)]*)\)|\[([^\]]*)\]", name)


def region_of(name):
    m = re.search(r"\(([^)]*)\)", name)
    return [r.strip() for r in m.group(1).split(",")] if m else []


def keep(name):
    if name.startswith("[BIOS]") or name.startswith("~"):
        return False
    for a, b in tags(name):
        if BAD_TAGS.search(a or b) or VERSION_TAG.match(a or b):
            return False
    return bool(set(region_of(name)) & OK_REGIONS)


def norm_title(name):
    t = name.split(" (")[0].lower()
    t = t.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def pref(name):
    r = ", ".join(region_of(name))
    regs = set(region_of(name))
    if regs and regs <= {"Europe", "Germany", "France", "Spain", "Italy", "Netherlands", "Sweden",
                         "UK", "United Kingdom", "Denmark", "Norway", "Finland", "Portugal",
                         "Austria", "Switzerland", "Belgium", "Scandinavia", "Greece", "Poland"}:
        p = 0 if "Europe" in regs else 1
    elif "Europe" in regs or "World" in regs:
        p = 2
    elif "USA" in regs:
        p = 3
    else:
        p = 4
    rev = re.search(r"\(Rev (\d+)\)", name)
    return (p, -(int(rev.group(1)) if rev else 0), len(r), name)


def build_groups(dbdir, systems, sample):
    """Per system: {group key: {"members": [game], ...}} after filtering."""
    out, stats = {}, {}
    for system in systems:
        games = parse_dat(os.path.join(dbdir, "dats", DATS[system]))
        merged = {}
        for g in games:                       # NES: .nes and .unh entries share a name
            if not keep(g["name"]):
                continue
            m = merged.setdefault(g["name"], {"name": g["name"], "roms": [], "serial": g.get("serial")})
            m["roms"] += g["roms"]
        groups = {}
        for g in merged.values():
            groups.setdefault(norm_title(g["name"]), []).append(g)
        if sample:
            groups = {k: v for k, v in groups.items() if k in STEEKPROEF[system]}
        out[system] = groups
        stats[system] = (len(games), len(merged), len(groups))
    return out, stats


def rep_rom(g, system):
    """Representative ROM for the lookup (NES: the headerless CRC)."""
    roms = g["roms"]
    if system == "nes":
        unh = [r for r in roms if r["file"].endswith(".unh")]
        if unh:
            return unh[0]
    return roms[0]


def main():
    ap = argparse.ArgumentParser(description="Maak het basispakket (3D-carts voor EU/US-spellen).")
    ap.add_argument("--db", default=mb.DEF_DB)
    ap.add_argument("--uit", default=None, help="uitvoermap (standaard <db>\\basispakket)")
    ap.add_argument("--env", default=mb.DEF_ENV)
    ap.add_argument("--blender", default=mb.DEF_BLENDER)
    ap.add_argument("--gba-model", default=mb.DEF_GBA_MODEL)
    ap.add_argument("--gb-model", default=mb.DEF_GB_MODEL)
    ap.add_argument("--nes-model", default=mb.DEF_NES_MODEL)
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--systemen", default="gba,gb,gbc,nes")
    ap.add_argument("--steekproef", action="store_true", help="alleen ~40 bekende spellen (test)")
    ap.add_argument("--reserve", type=int, default=300, help="Screenscraper-verzoeken die over moeten blijven")
    ap.add_argument("--max-verzoeken", type=int, default=0, help="max. verzoeken deze run (0 = tot het quotum)")
    ap.add_argument("--batch", type=int, default=40, help="carts per Blender-run")
    ap.add_argument("--alleen-tellen", action="store_true", help="alleen filteren/tellen en een schatting tonen")
    args = ap.parse_args()
    args.uit = args.uit or os.path.join(args.db, "basispakket-test" if args.steekproef else "basispakket")
    systems = [s for s in args.systemen.split(",") if s in DATS]
    t0 = time.time()

    groups, stats = build_groups(args.db, systems, args.steekproef)
    print("Na filteren en groeperen (DAT-items -> releases -> spellen):")
    total = 0
    for s in systems:
        print("  %-4s %6d -> %5d -> %5d" % (s.upper(), *stats[s]))
        total += stats[s][2] if not args.steekproef else len(groups[s])
    if args.alleen_tellen:
        print("Schatting volledige run: %d spellen, ~%d Screenscraper-verzoeken, ~%.1f uur renderen, ~%d MB"
              % (total, total * 2, total * 9.5 / 3600, total * 36 // 1024))
        return

    state_file = os.path.join(args.db, "basispakket_state.json")
    state = json.load(open(state_file, encoding="utf-8")) if os.path.exists(state_file) else {}
    client = ss.Screenscraper(args.env, os.path.join(args.db, "ss_cache"), log=print)
    client.verbose = False

    # --- 1. Screenscraper (cached, resumable, within the daily quota) -------
    todo, stopped = [], False
    net_fails, skipped = 0, 0     # a single timeout skips that game (retried next run) instead of stopping
    for system in systems:
        for gk, members in sorted(groups[system].items()):
            sid = "%s:%s" % (system, gk)
            st = state.get(sid)
            if st and st.get("done"):
                todo.append((system, gk, members, st))
                continue
            if args.max_verzoeken and client.requests >= args.max_verzoeken:
                stopped = True
                break
            if client.maxday and client.maxday - client.today <= args.reserve:
                print("Screenscraper-quotum bijna op (%d/%d): stop, morgen verder." % (client.today, client.maxday))
                stopped = True
                break
            best = sorted(members, key=lambda g: pref(g["name"]))[0]
            r = rep_rom(best, system)
            region = ss.region_from_name(best["name"])
            try:
                jeu = client.game_info(system, romnom=best["name"] + ".zip", crc=r["crc"],
                                       size=r["size"] if not r["file"].endswith(".unh") else r["size"])
                if not jeu:
                    jeu = client.game_info(system, romnom=best["name"] + ".zip")
            except ss.SSError as e:
                net_fails += 1
                skipped += 1
                if net_fails >= 3 or "netwerkfout" not in str(e):
                    print("  Screenscraper-fout (%s), stop deze run." % e)
                    stopped = True
                    break
                print("  Screenscraper-fout (%s) bij %s: overgeslagen, volgende run opnieuw." % (e, best["name"]))
                continue
            net_fails = 0
            st = {"done": True, "rep": best["name"], "region": region}
            if jeu:
                info = ss.describe(jeu, region)
                info["synopsis"] = ""          # base pack: facts only
                prefs = ss.REGION_ORDER.get(region, ss.REGION_ORDER["eu"])
                m = ss.pick_media(jeu, "support-texture", prefs) or ss.pick_media(jeu, "support-2D", prefs)
                if m:
                    try:
                        raw = client.download(m["url"], os.path.join(args.db, "media", str(info["ssid"]),
                                                                     "label_%s.%s" % (m.get("region", "x"), m.get("format") or "png")))
                        info["region"] = ss.REGION_NAMES.get(m.get("region", ""), "")
                        st["label"] = pack.prep_label(raw, os.path.join(args.db, "labels", "%s_%s_v6.png"
                                                                       % (info["ssid"], m.get("region", "x"))))
                    except ss.SSError as e:
                        print("  label mislukt (%s): %s" % (e, best["name"]))
                st["info"] = info
            state[sid] = st
            todo.append((system, gk, members, st))
            if len(state) % 25 == 0:
                json.dump(state, open(state_file, "w", encoding="utf-8"))
        if stopped:
            break
    json.dump(state, open(state_file, "w", encoding="utf-8"))

    # Merge groups that Screenscraper says are the same game (e.g. other EU name).
    by_game = {}
    for system, gk, members, st in todo:
        if not st.get("label") or not st.get("info"):
            continue
        fam = libindex.FAMILY[system]
        k = (fam, st["info"].get("ssid"))
        e = by_game.setdefault(k, {"system": system, "members": [], "st": st})
        e["members"] += members
        if pref(st["rep"]) < pref(e["st"]["rep"]):
            e["st"], e["system"] = st, system
    carts = sorted(by_game.values(), key=lambda e: (libindex.FAMILY[e["system"]], norm_title(e["st"]["rep"])))

    # --- 2. Render (resumable: cached per game) -----------------------------
    rargs = SimpleNamespace(db=args.db, blender=args.blender, samples=args.samples,
                            gba_model=args.gba_model, gb_model=args.gb_model, nes_model=args.nes_model)
    jobs = []
    for e in carts:
        st, system = e["st"], e["system"]
        info = st["info"]
        g = {"system": system, "file": st["rep"] + ".x", "nointro": st["rep"],
             "cgb": 0x80 if system == "gbc" else 0}
        body, clear = mb.cart_colour(g, info.get("name"))
        body, clear = mb.special_colour(g, info.get("name"), body, clear)
        metal = mb.is_metal(g, info.get("name"))
        rdir = os.path.join(args.db, "renders", "%s_%s" % (system, info["ssid"]))
        mpath = getattr(rargs, mb.MODEL_ARGS[system])
        model = os.path.basename(mpath) + (":3" if system == "gba" else ":1") if os.path.exists(mpath) else ""
        stamp = json.dumps([mb.RENDER_VERSION, os.path.basename(st["label"]), body, clear, system, model]
                           + (["metal"] if metal else []))
        e["rdir"] = rdir
        sfile = os.path.join(rdir, "stamp.json")
        if not (os.path.exists(sfile) and open(sfile).read() == stamp):
            jobs.append({"system": system, "body": body, "clear": clear, "metal": metal,
                         "label": st["label"], "out": rdir, "_stamp": stamp})
    print("Renderen: %d nieuw (van %d carts), in blokken van %d" % (len(jobs), len(carts), args.batch))
    t_r = time.time()
    for i in range(0, len(jobs), args.batch):
        mb.render(rargs, jobs[i:i + args.batch])
    t_r = time.time() - t_r

    # --- 3. Pack + index -----------------------------------------------------
    lib = os.path.join(args.uit, "LIBRARY")
    if os.path.isdir(os.path.join(lib, "C")):
        def _clear_readonly(func, path, exc):
            # Windows: a folder with the read-only attribute cannot be removed (WinError 5).
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(os.path.join(lib, "C"), onexc=_clear_readonly)
    pairs, n = [], 0
    for e in carts:
        if not os.path.exists(os.path.join(e["rdir"], "poses.json")):
            continue
        st = e["st"]
        crt = os.path.join(args.db, "crt", "basis_" + os.path.basename(e["rdir"]) + ".crt")
        if not os.path.exists(crt) or os.path.getmtime(crt) < os.path.getmtime(os.path.join(e["rdir"], "poses.json")):
            pack.write_crt(e["rdir"], st["info"], crt, card_label=st["label"])
        dest = libindex.cart_path(lib, "C", n)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(crt, dest)
        fam = libindex.FAMILY[e["system"]]
        for g in e["members"]:
            for r in g["roms"]:
                if fam == "gba" and r.get("serial") and re.fullmatch(r"[0-9A-Z]{4}", r["serial"]):
                    pairs.append((libindex.key("S", fam, r["serial"]), n))
                pairs.append((libindex.key("N", fam, g["name"]), n))
                pairs.append((libindex.key("C", fam, r["crc"]), n))
        n += 1
    nkeys = libindex.write_index(os.path.join(lib, "INDEX.BIN"), pairs)
    os.makedirs(os.path.join(lib, "_BLANK"), exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "..", "..", "res", "carts.bin"), os.path.join(lib, "_BLANK", "BLANK.BIN"))
    write_docs(args.uit)

    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(lib) for f in fs)
    left = (client.maxday - client.today) if client.maxday else "?"
    print("\nKlaar%s: %d carts, %d sleutels in INDEX.BIN, %.1f MB in %s"
          % (" (deels; draai hetzelfde commando later opnieuw)" if stopped or skipped else "", n, nkeys, size / 1e6, lib))
    if skipped:
        print("Overgeslagen door netwerkfouten: %d spellen (volgende run opnieuw)" % skipped)
    print("Screenscraper: %d verzoeken deze run; vandaag %s/%s gebruikt, nog %s over"
          % (client.requests, client.today or "?", client.maxday or "?", left))
    print("Tijd: renderen %.0fs, totaal %.0fs" % (t_r, time.time() - t0))


LEESMIJ = """Retroid Super Flash - spellenbibliotheek (3D-cartridges)
=========================================================

Kopieer de map LIBRARY naar de hoofdmap van de SD-kaart (naast je spellen).
Klaar: in de carrousel zie je je spellen als echte cartridges met label.

- Je spellen mogen elke naam hebben en in elke map staan. De Retroid Super
  Flash herkent ze aan de spelcode (GBA) of de inhoud (GB, GBC, NES).
- Bij GB/GBC/NES-spellen met een eigen bestandsnaam rekent de cart het spel
  een keer na (een paar seconden, de cart toont zolang een lege cartridge).
  Het resultaat wordt bewaard in LIBRARY\\CRC.BIN.
- Spellen die niet in het pakket zitten, krijgen een lege cartridge met de naam.

De 3D-modellen zijn gemaakt door anderen; zie CREDITS.txt.
"""

CREDITS = """Credits 3D-modellen (licentie CC-BY-4.0, https://creativecommons.org/licenses/by/4.0/)

- GBA: "Gameboy Advance Cartridge" door Vxcl (https://sketchfab.com/vxclhd)
  https://sketchfab.com/3d-models/gameboy-advance-cartridge-38c1e6702e5d4f21af1d0930689b1d10
- Game Boy / Game Boy Color: "Gameboy cartridge" door Val Turcea (https://sketchfab.com/zwinkers)
  https://sketchfab.com/3d-models/gameboy-cartridge-0c4f3c521907447098df0792e6cf9a1b
- NES: "NES Cartridge" door Anette Rana (https://sketchfab.com/pertrosfoliea)
  https://sketchfab.com/3d-models/nes-cartridge-ce42ffeab9144a2fabf3238053d84832

Aangepast: echte labels per spel, plastic per spel ingekleurd.
Spelgegevens: Screenscraper.fr. Spellijsten: No-Intro (libretro-database).
"""


def write_docs(out):
    open(os.path.join(out, "LEESMIJ.txt"), "w", encoding="utf-8").write(LEESMIJ)
    open(os.path.join(out, "CREDITS.txt"), "w", encoding="utf-8").write(CREDITS)


if __name__ == "__main__":
    main()
