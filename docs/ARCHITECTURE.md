# Architecture

Shellrunner is one Python process that drives GTK 3, WebKitGTK 4.1 and VTE through
PyGObject. WebKit runs each page in its own web process and does networking in a
network process; everything else (window, panels, internal pages, terminal) lives
in the UI process.

```
                 ┌─────────────── UI process (Python) ───────────────┐
 sr (CLI) ──────►│ control.py   Unix socket, one JSON line each way  │
                 │ window.py    header, rail, tabs, panels, palette  │
                 │   ├ tabs.py        one WebView per tab, suspension │
                 │   ├ terminal.py    VTE panel                       │
                 │   ├ devtools.py    network, site data, screenshots │
                 │   ├ monitor.py     memory per process (from /proc) │
                 │   ├ downloads.py   ai.py   ui.py   actions.py      │
                 │ navigation.py  address bar + sr:// pages           │
                 │   ├ startpage.py   servers.py (from /proc)         │
                 │   ├ onboarding.py  about.py                        │
                 │ privacy.py   profile, content filter, HTTPS guard  │
                 └──────┬────────────────────────────────────────────┘
                        │ WebKitGTK
        web processes ◄─┤  webext/privacy_ext.c (Sec-GPC, Referer)
     network process  ◄─┘
```

## Start-up

`__main__.main` checks the system libraries (`deps.py`), loads `config.json`,
picks the language (`i18n.py`), installs the theme, creates the `WebContext`
(`privacy.create_web_context`), registers `sr://`, compiles the content filter and
only then creates the window. No page can load before the blocklist and the HTTPS
rules are in place.

## Internal pages (`sr://`)

`navigation.register_internal_scheme` maps `sr://<name>?<query>` to a Python
function that returns HTML. Pages are templates in `shellrunner/resources/`
(`{{text}}` is translated, `$name` is filled with values that are already
HTML-escaped). The scheme is registered as *local*, so web pages cannot open or
embed it. `sr://setup` changes settings only with a per-process random token.

## Privacy layers

| Layer | Where |
|---|---|
| HTTPS-only and the tracker blocklist | WebKit content filter (`privacy.build_rules`), compiled from `blocklist.txt` |
| HTTP fallback after a failed upgrade | `privacy.HttpsGuard`: only after a click on the error page, in the same tab |
| `Sec-GPC` header, Referer trimmed to the origin | C web extension, built at first start into the cache |
| `navigator.globalPrivacyControl`, canvas/WebGL noise | user scripts injected before page scripts |
| Third-party cookies, ITP, WebRTC off, permissions denied | WebKit settings in `privacy.py` |
| Private tabs | a second, ephemeral `WebContext`, dropped with the last private tab |

## Local data

Everything stays in the XDG folders listed in the README. `storage.py` holds
history and bookmarks in SQLite and the session in JSON. Private tabs never touch
it. There is no network access except the pages the user opens, the search
engine, and Ollama on 127.0.0.1 when the AI panel is used.

## Tests

`python3 -m unittest` runs everything that needs no window. `scripts/check.sh`
adds a real start-up inside Xvfb (`tests/test_gui.py`). Tests run in Italian, the
source language; `tests/test_i18n.py` checks that every string is translated and
that placeholders survive translation.

## Decisions

The reasons behind the main choices are in [docs/adr](adr/):

1. [WebKitGTK from the system, not a bundled engine](adr/0001-webkitgtk-from-the-system.md)
2. [A local, hand-edited blocklist](adr/0002-local-blocklist.md)
3. [Internal pages rendered in Python](adr/0003-internal-pages-in-python.md)
4. [Dev servers discovered from /proc](adr/0004-servers-from-proc.md)
