"""Utilità comuni: nomi, percorsi e piccole funzioni di formattazione."""

import os
import re
import string

from gi.repository import GLib

from .i18n import _

APP_ID = "shellrunner"
APP_TITLE = "Shellrunner"

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)
RESOURCES_DIR = os.path.join(PACKAGE_DIR, "resources")
BIN_DIR = os.path.join(PROJECT_DIR, "bin")


def data_dir():
    """Dati persistenti del profilo (cookie, localStorage, ...)."""
    return os.path.join(GLib.get_user_data_dir(), APP_ID)


def cache_dir():
    """Cache del profilo, separata dai dati."""
    return os.path.join(GLib.get_user_cache_dir(), APP_ID)


def state_dir():
    """Stato che non è configurazione né cache (log)."""
    return os.path.join(GLib.get_user_state_dir(), APP_ID)


def config_dir():
    """Configurazione modificabile a mano (config.json, blocklist.txt)."""
    return os.path.join(GLib.get_user_config_dir(), APP_ID)


def socket_path():
    """Socket Unix per il comando sr (in /run/user/<uid>, accessibile solo all'utente)."""
    if os.environ.get("SHELLRUNNER_SOCKET"):  # stessa variabile letta da bin/sr
        return os.environ["SHELLRUNNER_SOCKET"]
    return os.path.join(GLib.get_user_runtime_dir(), APP_ID + ".sock")


# {{testo}} nelle risorse HTML/JS: testo da tradurre, scritto nella lingua sorgente
TRANSLATABLE_RE = re.compile(r"\{\{(.+?)\}\}", re.DOTALL)


def read_resource(name):
    """Contenuto di una risorsa con i testi {{...}} già tradotti."""
    with open(os.path.join(RESOURCES_DIR, name), encoding="utf-8") as f:
        text = f.read()
    return TRANSLATABLE_RE.sub(lambda m: _(" ".join(m.group(1).split())), text)


def render_template(name, **values):
    """Risorsa tradotta con i segnaposto $nome sostituiti (valori già sicuri per l'HTML)."""
    return string.Template(read_resource(name)).substitute(values)


def format_kb(kb):
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.2f} GB"
    return f"{kb / 1024:.1f} MB"
