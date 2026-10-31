#!/usr/bin/env python3
"""Screenshot per il README, in uno schermo virtuale e con un profilo temporaneo.

  xvfb-run -a -s "-screen 0 1440x900x24" .venv/bin/python scripts/screenshots.py docs/screenshots [it|en]

Serve ImageMagick (comando import). Il profilo vive in una cartella temporanea:
quello vero non viene toccato.
"""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
LANG = sys.argv[2] if len(sys.argv) > 2 else "en"
ROOT = tempfile.mkdtemp(prefix="devtox-shots-")
atexit.register(shutil.rmtree, ROOT, True)
for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.makedirs(os.path.join(ROOT, name.lower()))
    os.environ[name] = os.path.join(ROOT, name.lower())
os.environ["DEVTOX_SOCKET"] = os.path.join(ROOT, "dx.sock")
os.environ["LANGUAGE"] = LANG
# Sempre dentro Xvfb: senza queste due righe GTK sceglierebbe il desktop Wayland vero
os.environ["GDK_BACKEND"] = "x11"
os.environ.pop("WAYLAND_DISPLAY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Un server di sviluppo vero (solo su 127.0.0.1, in una cartella vuota del profilo
# temporaneo): la pagina iniziale lo mostra con strumento, cartella e uptime
# HOME punta al profilo temporaneo: la cartella appare come ~/projects/demo-site
os.environ["HOME"] = ROOT
SITE = os.path.join(ROOT, "projects", "demo-site")
os.makedirs(SITE)
DEMO = subprocess.Popen([sys.executable, "-m", "http.server", "--bind", "127.0.0.1", "5173"],
                        cwd=SITE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(DEMO.terminate)

from devtox import __main__ as app  # noqa: E402  (fissa le versioni di GTK prima di gi.repository)
from gi.repository import GLib, Gtk  # noqa: E402
from devtox.window import BrowserWindow  # noqa: E402


def window():
    return next(w for w in Gtk.Window.list_toplevels() if isinstance(w, BrowserWindow))


def shot(name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}-{LANG}.png")
    subprocess.run(["import", "-window", "root", path], check=True)
    # Via il fondo nero dello schermo virtuale: resta solo la finestra
    subprocess.run(["convert", path, "-fuzz", "3%", "-trim", "+repage", path], check=True)


def run(steps):
    """steps: [(secondi di attesa, funzione)] eseguite in sequenza nel main loop."""
    def next_step():
        if not steps:
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE
        delay, action = steps.pop(0)
        GLib.timeout_add(int(delay * 1000), lambda: (action(), next_step()) and GLib.SOURCE_REMOVE)
        return GLib.SOURCE_REMOVE
    GLib.timeout_add(6000, next_step)


def type_in_terminal():
    terminal = window().terminal_panel.current_terminal()
    # Prompt e titolo neutri: niente nome utente o hostname nelle immagini pubblicate
    terminal.feed_child(b"PROMPT_COMMAND=; PS1='$ '; printf '\\033]0;bash\\007'; clear; dx tabs; dx mem | tail -3\r")


run([
    (0, lambda: window().maximize()),
    (2, lambda: shot("setup")),
    (0, lambda: window().notebook.set_current_page(0)),
    (0, lambda: window().current_webview().reload()),
    (2, lambda: shot("start")),
    (0, lambda: window().show_terminal()),
    (3, type_in_terminal),
    (3, lambda: shot("terminal")),
    (0, lambda: window().hide_terminal()),
    (1, lambda: window().open_palette()),
    (0, lambda: window().palette.entry.set_text("term")),
    (1, lambda: shot("palette")),
])
sys.exit(app.main(["--new-instance"]))
