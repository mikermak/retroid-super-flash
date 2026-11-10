"""Small Screenscraper.fr client for the Retroid game library tool.

- Credentials are read from the Label Builder's .env.local (VITE_SS_*). They are
  only kept in memory: never printed, logged or written to the cache.
- Every API answer is cached on disk (with all credentials stripped from the
  media URLs), so a game is only ever asked once.
- One request at a time, with a small pause, to stay within the quota.
"""
import json
import os
import re
import time
import hashlib
import urllib.parse
import urllib.request
import urllib.error

API = "https://api.screenscraper.fr/api2/"
SOFTNAME = "retroid-library"
SECRET_KEYS = ("devid", "devpassword", "ssid", "sspassword")
SYSTEM_IDS = {"gb": 9, "gbc": 10, "gba": 12}


class SSError(Exception):
    pass


def read_env(path):
    vals = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    creds = {
        "devid": vals.get("VITE_SS_DEVID", ""),
        "devpassword": vals.get("VITE_SS_DEVPASSWORD", ""),
        "ssid": vals.get("VITE_SS_SSID", ""),
        "sspassword": vals.get("VITE_SS_SSPASSWORD", ""),
    }
    if not creds["devid"] or not creds["devpassword"]:
        raise SSError("Geen Screenscraper-gegevens gevonden in .env.local (VITE_SS_DEVID/DEVPASSWORD)")
    return creds


def strip_secrets(obj):
    """Removes credentials from every URL inside an API answer (recursively)."""
    if isinstance(obj, dict):
        return {k: strip_secrets(v) for k, v in obj.items() if k not in SECRET_KEYS}
    if isinstance(obj, list):
        return [strip_secrets(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("http") and "?" in obj:
        u = urllib.parse.urlsplit(obj)
        q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if k not in SECRET_KEYS]
        return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))
    return obj


class Screenscraper:
    def __init__(self, env_path, cache_dir, pause=1.2, log=print):
        self._creds = read_env(env_path)
        self.cache_dir = cache_dir
        self.pause = pause
        self.log = log
        self._last = 0.0
        self.requests = 0
        os.makedirs(cache_dir, exist_ok=True)

    # -- low level ---------------------------------------------------------
    def _wait(self):
        dt = time.time() - self._last
        if dt < self.pause:
            time.sleep(self.pause - dt)
        self._last = time.time()

    def _get(self, url, binary=False, tries=3):
        last = None
        for attempt in range(tries):
            self._wait()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": SOFTNAME})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                return data if binary else data.decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                # Never echo the URL (it contains the credentials).
                last = SSError("HTTP %d" % e.code)
                if e.code in (400, 404):
                    raise last
                if e.code in (401, 403, 423, 426, 429, 430, 431):
                    time.sleep(5 + 10 * attempt)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = SSError("netwerkfout: %s" % type(e).__name__)
                time.sleep(3 + 5 * attempt)
        raise last

    def _params(self, extra):
        p = dict(self._creds)
        p.update({"softname": SOFTNAME, "output": "json"})
        p.update(extra)
        return urllib.parse.urlencode(p)

    # -- game info -----------------------------------------------------------
    def game_info(self, system, romnom=None, crc=None, size=None, serial=None):
        """Returns the (credential free) 'jeu' dict or None if unknown."""
        key = json.dumps([system, romnom, crc, size, serial], sort_keys=True)
        cfile = os.path.join(self.cache_dir, "info_%s.json" % hashlib.sha1(key.encode()).hexdigest()[:16])
        if os.path.exists(cfile):
            with open(cfile, encoding="utf-8") as f:
                cached = json.load(f)
            return cached.get("jeu")

        q = {"systemeid": SYSTEM_IDS[system], "romtype": "rom"}
        if romnom:
            q["romnom"] = romnom
        if crc:
            q["crc"] = crc
        if size:
            q["romtaille"] = str(size)
        if serial:
            q["serialnum"] = serial
        jeu = None
        try:
            txt = self._get(API + "jeuInfos.php?" + self._params(q))
            if txt.strip().startswith("{"):
                data = json.loads(txt)
                resp = data.get("response", {})
                jeu = strip_secrets(resp.get("jeu"))
                user = resp.get("ssuser") or {}
                if user:
                    self.log("    (quota: %s/%s verzoeken vandaag)" % (user.get("requeststoday", "?"), user.get("maxrequestsperday", "?")))
            # Plain-text answers ("Erreur : Rom/Iso/Dossier non trouvée !") = unknown game.
        except SSError as e:
            if "404" not in str(e):
                raise
        with open(cfile, "w", encoding="utf-8") as f:
            json.dump({"jeu": jeu}, f, ensure_ascii=False)
        return jeu

    # -- media ---------------------------------------------------------------
    def download(self, url, dest):
        """Downloads a (stripped) media URL, re-adding the credentials in memory."""
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return dest
        u = urllib.parse.urlsplit(url)
        q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        full = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, self._params(q), ""))
        data = self._get(full, binary=True)
        if len(data) < 100 or data[:4] in (b"NOME", b"CRCO", b"MD5O", b"SHA1"):
            raise SSError("geen afbeelding")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return dest


# -- helpers on a 'jeu' dict ------------------------------------------------

REGION_ORDER = {
    "eu": ["eu", "wor", "us", "ss", "jp"],
    "us": ["us", "wor", "eu", "ss", "jp"],
    "jp": ["jp", "wor", "us", "eu", "ss"],
}


def region_from_name(name):
    m = re.search(r"\(([^)]*)\)", name or "")
    s = (m.group(1).lower() if m else "")
    if "europe" in s or "germany" in s or "france" in s or "spain" in s or "italy" in s:
        return "eu"
    if "japan" in s:
        return "jp"
    if "usa" in s:
        return "us"
    return "eu"


def pick_text(entries, prefs, key="text"):
    if not entries:
        return None
    if isinstance(entries, dict):
        return entries.get(key)
    for r in prefs + ["wor", "en"]:
        for e in entries:
            if e.get("region") == r or e.get("langue") == r:
                return e.get(key)
    return entries[0].get(key)


def pick_media(jeu, mtype, prefs):
    medias = [m for m in (jeu.get("medias") or []) if m.get("type") == mtype]
    for r in prefs:
        for m in medias:
            if m.get("region") == r:
                return m
    return medias[0] if medias else None


def clean(text):
    """Plain ASCII (the menu font may lack accents) and English-style colons."""
    import unicodedata
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.encode("ascii", "replace").decode("ascii").replace("?", "")
    t = re.sub(r"\s+:\s*", ": ", t)
    return re.sub(r"\s+", " ", t).strip()


def describe(jeu, region):
    prefs = REGION_ORDER.get(region, REGION_ORDER["eu"])
    name = pick_text(jeu.get("noms"), prefs) or "?"
    date = pick_text(jeu.get("dates"), prefs) or ""
    year = date[:4] if date[:4].isdigit() else ""
    pub = (jeu.get("editeur") or {}).get("text", "")
    players = (jeu.get("joueurs") or {}).get("text", "")
    genre = ""
    for g in jeu.get("genres") or []:
        genre = pick_text(g.get("noms"), ["en"]) or genre
        if g.get("principale") == "1":
            break
    return {"name": clean(name), "year": year, "publisher": clean(pub), "players": clean(players),
            "genre": clean(genre), "ssid": jeu.get("id")}
