"""Pagina iniziale (devtox://start): il prompt, i server che girano su questo PC, le ultime pagine.

Tutto viene da dati locali letti al momento: /proc per i server, il database
della cronologia e dei preferiti, config.json per lo stato della privacy.
"""

import html
import json
import secrets
import time

from . import navigation, privacy, servers, utils
from .devtools import listening_ports
from .i18n import N_, _

RECENT_ROWS = 6
# I pulsanti "ferma" passano da devtox://stop con questo token: solo la pagina iniziale lo conosce
STOP_TOKEN = secrets.token_urlsafe(18)
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
        stop = (f'<a class="stop" href="devtox://stop?token={STOP_TOKEN}&amp;port={s.port}" '
                f'title="{_e(_("Ferma il server (come Ctrl+C)"))}" '
                f'aria-label="{_e(_("Ferma il server sulla porta {port}").format(port=s.port))}">×</a>'
                if s.pid else "")
        rows.append(
            f'<tr><th scope="row"><a href="{_e(s.url)}" class="port">'
            f'<span class="live" aria-hidden="true"></span>{s.port}</a></th>'
            f'<td class="tool">{tool}</td><td class="project">{project}</td>'
            f'<td class="num">{_e(servers.format_uptime(s.uptime))}</td><td class="num">{pid}</td>'
            f'<td class="act">{stop}</td></tr>'
        )
    head = (f'<thead><tr><th scope="col">{_e(_("Porta"))}</th><th scope="col">{_e(_("Strumento"))}</th>'
            f'<th scope="col">{_e(_("Cartella"))}</th><th scope="col" class="num">{_e(_("Attivo da"))}</th>'
            f'<th scope="col" class="num">PID</th><th scope="col"><span class="sr-only">'
            f'{_e(_("Ferma"))}</span></th></tr></thead>')
    cols = ('<colgroup><col class="c-port"><col class="c-tool"><col class="c-project">'
            '<col class="c-up"><col class="c-pid"><col class="c-act"></colgroup>')
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
        count = _e(_("1 server in ascolto") if len(found) == 1
                   else _("{n} server in ascolto").format(n=len(found)))
        if sum(1 for s in found if s.pid) > 1:
            question = json.dumps(_("Fermare tutti i server di sviluppo?")).replace("<", "\\u003c")
            count += (f' · <a class="stop-all" href="devtox://stop?token={STOP_TOKEN}&amp;port=all" '
                      f'onclick=\'return confirm({_e(question)})\'>{_e(_("Ferma tutti"))}</a>')
    else:
        count = _e(_("nessun server"))
    keys = "".join(f"<li><kbd>{_e(k)}</kbd> {_e(_(label))}</li>" for k, label in KEYS)
    engine = navigation.search_engine_name()
    return utils.render_template(
        "start.html",
        search_hint=_e(_("Le ricerche vanno su {engine}. Indirizzi e porte locali si aprono direttamente.")
                       .format(engine=engine)),
        privacy=_privacy_line(config, filters_active),
        servers_count=count,
        servers=_servers_html(found, config["dev_ports"]),
        recent=_list_html(recent, _("Le pagine che apri compariranno qui.") if config["history_enabled"]
                          else _("Cronologia spenta in config.json.")),
        bookmarks=_list_html(bookmarks, _("Nessun preferito: Ctrl+D salva la pagina aperta.")),
        keys=keys,
    )


def render_stop(params, config):
    """devtox://stop?token=...&port=5173|all: ferma e torna alla pagina iniziale."""
    if secrets.compare_digest(params.get("token", ""), STOP_TOKEN):
        port = params.get("port", "")
        if port == "all" or port.isdigit():
            chosen = servers.select(collect_servers(config["dev_ports"]), "all" if port == "all" else [int(port)])
            servers.stop(chosen)
    # Un attimo per lasciar chiudere i processi, poi la lista si rilegge da /proc
    return ('<!doctype html><meta charset="utf-8"><body style="background:#0e0e10">'
            '<script>setTimeout(() => location.replace("devtox://start"), 600);</script>')
