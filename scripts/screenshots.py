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
os.environ["DEVTOX_NO_NETWORK"] = "1"  # niente download della lista anti-phishing
# Sempre dentro Xvfb: senza queste due righe GTK sceglierebbe il desktop Wayland vero
os.environ["GDK_BACKEND"] = "x11"
os.environ.pop("WAYLAND_DISPLAY", None)
# Xvfb non ha GPU: col compositing il GL software sposta la pagina nella vista responsive
os.environ["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Un server di sviluppo vero (solo su 127.0.0.1, in una cartella vuota del profilo
# temporaneo): la pagina iniziale lo mostra con strumento, cartella e uptime
# HOME punta al profilo temporaneo: la cartella appare come ~/projects/demo-site
os.environ["HOME"] = ROOT
SITE = os.path.join(ROOT, "projects", "demo-site")
os.makedirs(SITE)
# Una pagina finta con stile e un'API JSON: serve a rete, vista responsive e visualizzatore JSON
DEMO_FILES = {
    "index.html": """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Demo site</title>
<link rel="stylesheet" href="style.css"></head><body>
<header><b>demo-site</b><nav><a href="#">Docs</a><a href="#">Pricing</a><a href="#">Blog</a></nav></header>
<main><h1>Ship faster, locally.</h1><p>A tiny demo page served by <code>python -m http.server</code>.</p>
<a class="cta" href="api.json">See the API</a>
<section class="cards"><div><h3>Fast</h3><p>Hot reload in milliseconds.</p></div>
<div><h3>Private</h3><p>Nothing leaves your machine.</p></div>
<div><h3>Simple</h3><p>One command to start.</p></div></section></main>
<script src="app.js"></script></body></html>""",
    "style.css": """body{margin:0;font:16px/1.5 system-ui,sans-serif;color:#1d2433;background:#f6f7fb}
header{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:#fff;border-bottom:1px solid #e3e6ee}
nav a{margin-left:18px;color:#4a5571;text-decoration:none}
main{max-width:880px;margin:0 auto;padding:48px 24px}h1{font-size:44px;line-height:1.1;margin:0 0 12px}
.cta{display:inline-block;margin:16px 0 32px;padding:10px 18px;border-radius:8px;background:#3b5bdb;color:#fff;text-decoration:none}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.cards div{background:#fff;border:1px solid #e3e6ee;border-radius:10px;padding:4px 18px}""",
    "app.js": "fetch('api.json').then(r => r.json()).then(d => console.log(d.name));\n",
    "api.json": '{"name": "demo-site", "version": "1.4.2", "ok": true, "uptime_s": 5231, '
                '"routes": [{"path": "/", "method": "GET"}, {"path": "/api/users", "method": "GET"}, '
                '{"path": "/api/users", "method": "POST"}], "db": {"engine": "sqlite", "size_mb": 3.2}, '
                '"features": ["hot-reload", "https-dev", "mock-api"], "maintainer": null}',
}
for name, text in DEMO_FILES.items():
    with open(os.path.join(SITE, name), "w") as f:
        f.write(text)
DEMO_URL = "http://localhost:5173/"
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
    (0, lambda: window().palette.hide()),
    (0, lambda: window().load_in_current("devtox://passwords")),
    (5, lambda: shot("passwords")),
    (0, lambda: window().load_in_current(DEMO_URL)),
    (0, lambda: window().toggle_side_panel("rete")),
    (3, lambda: window().current_webview().reload()),
    (3, lambda: shot("network")),
    (0, lambda: window().toggle_side_panel("rete")),
    (0, lambda: window().set_responsive((390, 844))),
    (6, lambda: shot("responsive")),
    (0, lambda: window().set_responsive(None)),
    (0, lambda: window().load_in_current(DEMO_URL + "api.json")),
    (6, lambda: shot("json")),
    (0, lambda: window().toggle_side_panel("memoria")),
    (3, lambda: shot("memory")),
])
sys.exit(app.main(["--new-instance"]))
