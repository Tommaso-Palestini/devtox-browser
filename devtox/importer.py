"""Import di preferiti e cronologia da altri browser installati su questo PC.

Solo lettura e solo file locali: si leggono una copia dei database (il browser
aperto li tiene bloccati) e il file JSON dei preferiti. Si importano preferiti
e cronologia web (http e https); password e cookie no: sono cifrati con il
portachiavi dell'altro browser, e copiarli altrove li esporrebbe.
Tor Browser non viene mai proposto: la sua cronologia non deve finire altrove.
"""

import glob
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass

HISTORY_LIMIT = 5000  # le pagine più recenti bastano per i suggerimenti, il resto pesa e basta
_CHROME_EPOCH = 11_644_473_600  # secondi tra il 1601 (orologio di Chromium) e il 1970

# (nome, cartella del profilo relativa alla home); Flatpak tiene i dati in ~/.var/app
CHROMIUM = [
    ("Google Chrome", ".config/google-chrome"),
    ("Google Chrome (Flatpak)", ".var/app/com.google.Chrome/config/google-chrome"),
    ("Chromium", ".config/chromium"),
    ("Chromium (Flatpak)", ".var/app/org.chromium.Chromium/config/chromium"),
    ("Chromium (Snap)", "snap/chromium/common/chromium"),
    ("Brave", ".config/BraveSoftware/Brave-Browser"),
    ("Brave (Flatpak)", ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"),
    ("Microsoft Edge", ".config/microsoft-edge"),
    ("Microsoft Edge (Flatpak)", ".var/app/com.microsoft.Edge/config/microsoft-edge"),
    ("Vivaldi", ".config/vivaldi"),
    ("Vivaldi (Flatpak)", ".var/app/com.vivaldi.Vivaldi/config/vivaldi"),
    ("Opera", ".config/opera"),
    ("Opera (Flatpak)", ".var/app/com.opera.Opera/config/opera"),
    ("Opera GX", ".config/opera-gx"),
    ("Opera GX (Flatpak)", ".var/app/com.opera.opera-gx/config/opera-gx"),
]
FIREFOX = [
    ("Firefox", ".mozilla/firefox"),
    ("Firefox (Flatpak)", ".var/app/org.mozilla.firefox/config/mozilla/firefox"),
    ("Firefox (Flatpak)", ".var/app/org.mozilla.firefox/.mozilla/firefox"),
    ("Firefox (Snap)", "snap/firefox/common/.mozilla/firefox"),
    ("LibreWolf", ".librewolf"),
    ("LibreWolf (Flatpak)", ".var/app/io.gitlab.librewolf-community/.librewolf"),
    ("Zen", ".zen"),
    ("Zen (Flatpak)", ".var/app/app.zen_browser.zen/.zen"),
    ("Waterfox", ".waterfox"),
]


@dataclass
class Source:
    name: str
    kind: str      # "chromium" | "firefox"
    profile: str   # cartella del profilo

    @property
    def id(self):
        return self.profile

    def bookmarks(self):
        """[(url, titolo)] dei preferiti web, nell'ordine dell'altro browser."""
        return _chromium_bookmarks(self.profile) if self.kind == "chromium" else _firefox_bookmarks(self.profile)

    def history(self, since, limit=HISTORY_LIMIT):
        """[(url, titolo, visite, ultimo accesso in secondi Unix)] dal più recente, dopo `since`."""
        if self.kind == "chromium":
            return _chromium_history(self.profile, since, limit)
        return _firefox_history(self.profile, since, limit)


def _is_web(url):
    return isinstance(url, str) and url.startswith(("http://", "https://"))


def discover(home=None):
    """Profili con preferiti o cronologia, browser per browser. Più profili: nome con il profilo."""
    home = home or os.path.expanduser("~")
    found = []
    for name, rel in CHROMIUM:
        base = os.path.join(home, rel)
        profiles = [p for p in sorted(glob.glob(os.path.join(base, "*"))) + [base]
                    if os.path.isfile(os.path.join(p, "Bookmarks")) or os.path.isfile(os.path.join(p, "History"))]
        found += _named(name, "chromium", profiles)
    for name, rel in FIREFOX:
        base = os.path.join(home, rel)
        profiles = [p for p in sorted(glob.glob(os.path.join(base, "*")))
                    if os.path.isfile(os.path.join(p, "places.sqlite"))]
        found += _named(name, "firefox", profiles)
    # Lo stesso profilo raggiunto da due percorsi (link simbolici) compare una volta sola
    unique, seen = [], set()
    for source in found:
        real = os.path.realpath(source.profile)
        if real not in seen:
            seen.add(real)
            unique.append(source)
    return unique


def _named(name, kind, profiles):
    if len(profiles) == 1:
        return [Source(name, kind, profiles[0])]
    return [Source(f"{name} · {os.path.basename(p)}", kind, p) for p in profiles]


def _copy_db(path):
    """Copia del database (con il suo -wal) in una cartella temporanea privata."""
    folder = tempfile.mkdtemp(prefix="devtox-import-")
    target = os.path.join(folder, "db.sqlite")
    shutil.copyfile(path, target)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.copyfile(path + suffix, target + suffix)
    return folder, target


def _query(path, sql, params=()):
    if not os.path.isfile(path):
        return []
    folder, copy = _copy_db(path)
    try:
        db = sqlite3.connect(copy)
        try:
            return db.execute(sql, params).fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _chromium_bookmarks(profile):
    try:
        with open(os.path.join(profile, "Bookmarks"), encoding="utf-8") as f:
            roots = json.load(f).get("roots", {})
    except (OSError, ValueError, AttributeError):
        return []
    found = []

    def walk(node, key=""):
        if not isinstance(node, dict) or key.lower() == "trash" or "pinboard" in key.lower():
            return  # cestino e bacheca interna di Opera non si importano
        if node.get("type") == "url":
            if _is_web(node.get("url")):
                found.append((node["url"], node.get("name") or node["url"]))
            return
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child)
        else:
            # Opera: custom_root è un dizionario di cartelle (speedDial, userRoot, trash...)
            for child_key, child in node.items():
                walk(child, child_key)

    for key, root in roots.items():
        walk(root, key)
    return _dedupe(found)


def _chromium_history(profile, since, limit):
    rows = _query(
        os.path.join(profile, "History"),
        """SELECT url, title, visit_count, last_visit_time FROM urls
           WHERE hidden = 0 AND last_visit_time > ? ORDER BY last_visit_time DESC LIMIT ?""",
        (int((since + _CHROME_EPOCH) * 1_000_000), limit),
    )
    return [(url, title or "", visits or 1, when / 1_000_000 - _CHROME_EPOCH)
            for url, title, visits, when in rows if _is_web(url)]


def _firefox_bookmarks(profile):
    rows = _query(
        os.path.join(profile, "places.sqlite"),
        """SELECT p.url, COALESCE(NULLIF(b.title, ''), p.title, p.url) FROM moz_bookmarks b
           JOIN moz_places p ON b.fk = p.id WHERE b.type = 1 ORDER BY b.id""",
    )
    return _dedupe([(url, title) for url, title in rows if _is_web(url)])


def _firefox_history(profile, since, limit):
    rows = _query(
        os.path.join(profile, "places.sqlite"),
        """SELECT url, title, visit_count, last_visit_date FROM moz_places
           WHERE last_visit_date > ? ORDER BY last_visit_date DESC LIMIT ?""",
        (int(since * 1_000_000), limit),
    )
    return [(url, title or "", visits or 1, when / 1_000_000) for url, title, visits, when in rows if _is_web(url)]


def _dedupe(rows):
    seen, out = set(), []
    for url, title in rows:
        if url not in seen:
            seen.add(url)
            out.append((url, title))
    return out
