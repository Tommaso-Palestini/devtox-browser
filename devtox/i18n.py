"""Traduzioni: il testo sorgente è in italiano, le altre lingue stanno in locale/<lingua>.po.

Il file .po viene letto direttamente (niente .mo da compilare). La lingua si
decide una volta all'avvio, prima che gli altri moduli creino le loro stringhe:
la voce "language" di config.json, altrimenti le variabili LANGUAGE/LC_*/LANG.
Non usa GLib: deve funzionare anche prima del controllo delle dipendenze.
"""

import ast
import json
import os

SOURCE_LANGUAGE = "it"
LANGUAGES = {"it": "Italiano", "en": "English"}
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")

language = SOURCE_LANGUAGE
_catalog = {}


def _config_language():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    try:
        with open(os.path.join(base, "devtox", "config.json"), encoding="utf-8") as f:
            value = json.load(f).get("language", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value if isinstance(value, str) else ""


def system_language():
    """Prima lingua supportata tra quelle del sistema; inglese se nessuna lo è."""
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for item in os.environ.get(name, "").split(":"):
            code = item.split("_")[0].split(".")[0].lower()
            if code in LANGUAGES:
                return code
            if code and code not in ("c", "posix"):
                return "en"
    return "en"


def parse_po(path):
    """{msgid: msgstr} da un file .po; le traduzioni vuote sono ignorate."""
    catalog, entry, field = {}, {}, None

    def flush():
        if entry.get("msgid") and entry.get("msgstr"):
            catalog[entry["msgid"]] = entry["msgstr"]
        entry.clear()

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                if not line:
                    flush()
                continue
            if line.startswith(("msgid ", "msgstr ")):
                keyword, _sep, value = line.partition(" ")
                if keyword == "msgid" and "msgstr" in entry:
                    flush()
                field = keyword
                entry[field] = ast.literal_eval(value)
            elif line.startswith('"') and field:
                entry[field] += ast.literal_eval(line)
    flush()
    return catalog


def setup(lang=None):
    """Sceglie la lingua; lang esplicito (test, anteprima) oppure config/sistema."""
    global language, _catalog
    lang = lang or _config_language() or system_language()
    language = lang if lang in LANGUAGES else "en"
    _catalog = {}
    if language != SOURCE_LANGUAGE:
        path = os.path.join(LOCALE_DIR, language + ".po")
        if os.path.exists(path):
            _catalog = parse_po(path)


def _(text):
    return _catalog.get(text, text)


def N_(text):
    """Segna una stringa da tradurre più tardi (costanti di modulo)."""
    return text
