"""Pagina iniziale (devtox://start): il prompt, i server che girano su questo PC, le ultime pagine.

Tutto viene da dati locali letti al momento: /proc per i server, il database
della cronologia e dei preferiti, config.json per lo stato della privacy.
"""

import html
import time

from . import navigation, privacy, servers, utils
from .devtools import listening_ports
from .i18n import N_, _

RECENT_ROWS = 6
BOOKMARK_ROWS = 8

# Le scorciatoie che servono davvero ogni giorno; tutto il resto è nella palette (Ctrl+K)
KEYS = [
    ("Ctrl+K", N_("tutti i comandi")),
    ("Ctrl+`", N_("terminale")),
    ("Ctrl+Shift+L", N_("server locali")),
    ("Ctrl+Shift+E", N_("richieste di rete")),
    ("Ctrl+Shift+M", N_("vista responsive")),
    ("Ctrl+U", N_("sorgente")),
    ("F12", N_("strumenti sviluppatore")),
]


def _e(text):
    return html.escape(str(text), quote=True)


def collect_servers(watched_ports):
    """Server dell'utente da /proc più le porte osservate in ascolto ma di altri (Docker, root)."""
    found = servers.scan()
    known = {s.port for s in found}
    extra = [p for p in watched_ports if p not in known]
    for port in listening_ports(extra) if extra else []:
        found.append(servers.Server(port=port, host="localhost"))
    return sorted(found, key=lambda s: s.port)


def _servers_html(found, watched_ports):
    if not found:
        watched = ", ".join(str(p) for p in watched_ports)
        note = _("Niente è in ascolto su localhost in questo momento.")
        tip = _("Avvia un server dal terminale (<kbd>Ctrl+`</kbd>), per esempio "
                "<code>npm run dev</code> o <code>python3 -m http.server</code>: comparirà qui.")
        watched_line = (f'<p class="quiet">{_e(_("Porte sempre controllate anche se di altri utenti:"))} '
                        f'<span class="mono">{_e(watched)}</span></p>') if watched else ""
        return f'<div class="empty"><p>{_e(note)}</p><p class="quiet">{tip}</p>{watched_line}</div>'
    rows = []
    for s in found:
        tool = _e(s.tool) if s.tool else '<span class="quiet">—</span>'
        if s.project:
            project = f'<span class="path" title="{_e(s.project)}">{_e(s.project)}</span>'
        elif s.pid is None:
            project = f'<span class="quiet">{_e(_("di un altro utente o di sistema"))}</span>'
        else:
            project = '<span class="quiet">—</span>'
        pid = f'<span class="quiet mono">{s.pid}</span>' if s.pid else '<span class="quiet">—</span>'
        rows.append(
            f'<tr><th scope="row"><a href="{_e(s.url)}" class="port">'
            f'<span class="live" aria-hidden="true"></span>{s.port}</a></th>'
            f'<td class="tool">{tool}</td><td class="project">{project}</td>'
            f'<td class="num">{_e(servers.format_uptime(s.uptime))}</td><td class="num">{pid}</td></tr>'
        )
    head = (f'<thead><tr><th scope="col">{_e(_("Porta"))}</th><th scope="col">{_e(_("Strumento"))}</th>'
            f'<th scope="col">{_e(_("Cartella"))}</th><th scope="col" class="num">{_e(_("Attivo da"))}</th>'
            f'<th scope="col" class="num">PID</th></tr></thead>')
    cols = ('<colgroup><col class="c-port"><col class="c-tool"><col class="c-project">'
            '<col class="c-up"><col class="c-pid"></colgroup>')
    return f'<table class="servers">{cols}{head}<tbody>{"".join(rows)}</tbody></table>'


def _list_html(items, empty):
    if not items:
        return f'<p class="quiet">{_e(empty)}</p>'
    rows = "".join(
        f'<li><a href="{_e(url)}"><span class="title">{_e(title or url)}</span>'
        f'<span class="meta">{_e(meta)}</span></a></li>'
        for url, title, meta in items
    )
    return f'<ul class="links">{rows}</ul>'


def _privacy_line(config, filters_active=True):
    """Stato delle protezioni in una riga: quello che è acceso, detto con le parole giuste."""
    if not filters_active:
        # Il filtro dei contenuti non si è compilato: lo si dice per primo, non solo nel log
        return f'<span class="alert">{_e(_("blocklist e HTTPS-only non attivi: vedi il log"))}</span>'
    try:
        blocked = len(privacy.load_blocklist(privacy.blocklist_path()))
    except OSError:
        blocked = 0
    parts = []
    if config["https_only"]:
        parts.append(_("solo HTTPS"))
    parts.append(_("{n} domini bloccati").format(n=blocked))
    if config["send_gpc"]:
        parts.append("GPC")
    if config["fingerprint_protection"]:
        parts.append(_("anti-fingerprinting"))
    if not config["persistent_data"]:
        parts.append(_("niente su disco"))
    return _e(" · ".join(parts))


def render(config, storage, now=None, filters_active=True):
    now = now if now is not None else time.time()
    found = collect_servers(config["dev_ports"])
    recent = [(url, title, f"{navigation.http_host(url) or url} · {utils.format_ago(seen, now)}")
              for url, title, seen in storage.recent(RECENT_ROWS)] if config["history_enabled"] else []
    bookmarks = [(url, title, navigation.http_host(url) or url)
                 for url, title in storage.bookmarks()[:BOOKMARK_ROWS]
                 if url.startswith(("http://", "https://"))]
    if found:
        count = (_("1 server in ascolto") if len(found) == 1
                 else _("{n} server in ascolto").format(n=len(found)))
    else:
        count = _("nessun server")
    keys = "".join(f"<li><kbd>{_e(k)}</kbd> {_e(_(label))}</li>" for k, label in KEYS)
    engine = navigation.search_engine_name()
    return utils.render_template(
        "start.html",
        search_hint=_e(_("Le ricerche vanno su {engine}. Indirizzi e porte locali si aprono direttamente.")
                       .format(engine=engine)),
        privacy=_privacy_line(config, filters_active),
        servers_count=_e(count),
        servers=_servers_html(found, config["dev_ports"]),
        recent=_list_html(recent, _("Le pagine che apri compariranno qui.") if config["history_enabled"]
                          else _("Cronologia spenta in config.json.")),
        bookmarks=_list_html(bookmarks, _("Nessun preferito: Ctrl+D salva la pagina aperta.")),
        keys=keys,
    )
