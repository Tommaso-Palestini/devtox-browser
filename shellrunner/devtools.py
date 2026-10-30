"""Strumenti da sviluppatore: server locali, rete, dati del sito, screenshot, responsive."""

import collections
import html
import itertools
import json
import os
import re
import shlex
import socket
import time

import cairo
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, WebKit2

from . import navigation, utils
from .i18n import _

# Mondo JavaScript isolato: gli script della pagina non vedono il nostro codice
TOOLS_WORLD = "shellrunner-tools"

RESPONSIVE_PRESETS = [
    (_("Telefono Android"), (360, 800)),
    ("iPhone", (390, 844)),
    (_("Tablet"), (768, 1024)),
    (_("Laptop"), (1280, 800)),
]
DEFAULT_RESPONSIVE = RESPONSIVE_PRESETS[1][1]

# Su localhost una porta chiusa rifiuta subito: il timeout scatta solo in casi rari
_QUICK_TIMEOUT = 0.05


# --- Server locali -------------------------------------------------------


def listening_ports(ports):
    """Porte che accettano connessioni su localhost (IPv4 o IPv6), controllo rapido."""
    found = []
    for port in ports:
        for host in ("127.0.0.1", "::1"):
            try:
                socket.create_connection((host, port), timeout=_QUICK_TIMEOUT).close()
            except OSError:
                continue
            found.append(port)
            break
    return found


def render_start_page(ports, bookmarks=()):
    """Pagina iniziale: preferiti e server locali attivi in questo momento."""
    bookmarks_html = ""
    if bookmarks:
        items = "".join(
            f'<li><a href="{html.escape(url, quote=True)}"><span class="title">{html.escape(title)}</span>'
            f'<span class="site">{html.escape(navigation.http_host(url) or url)}</span></a></li>'
            for url, title in bookmarks
            if url.startswith(("http://", "https://"))
        )
        bookmarks_html = f'<h2>{html.escape(_("Preferiti"))}</h2><ul class="bookmarks">{items}</ul>'
    active = listening_ports(ports)
    if active:
        items = "".join(
            f'<li><a href="http://localhost:{port}/"><span class="port">{port}</span>'
            f'<span class="host">localhost</span></a></li>'
            for port in active
        )
        servers = f'<ul class="servers">{items}</ul>'
    elif not ports:
        servers = '<p class="empty">' + _(
            "Nessuna porta da controllare: aggiungile alla voce <code>dev_ports</code> di config.json."
        ) + "</p>"
    else:
        watched = ", ".join(str(p) for p in ports)
        servers = '<p class="empty">' + _(
            "Nessun server in ascolto su {ports}. Avvialo dal terminale (<kbd>Ctrl+`</kbd>), per esempio "
            "con <code>npm run dev</code> o <code>python3 -m http.server</code>, poi apri una nuova tab."
        ).format(ports=html.escape(watched)) + "</p>"
    hint = _("Le ricerche vanno su {engine}. Indirizzi e porte locali si aprono direttamente.").format(
        engine=navigation.search_engine_name())
    return utils.render_template("start.html", servers=servers, bookmarks=bookmarks_html,
                                 search_hint=html.escape(hint))


# --- Sorgente della pagina -----------------------------------------------

SOURCE_LIMIT = 2 * 1024 * 1024
_SOURCE_CACHE = collections.OrderedDict()  # id -> (url, testo); solo in memoria
_SOURCE_IDS = itertools.count(1)
_TAG_RE = re.compile(r"(&lt;/?)([a-zA-Z][\w:-]*)")


def open_source(webview, open_url):
    """Legge i byte originali della pagina (non il DOM modificato dagli script)."""
    resource = webview.get_main_resource()
    if resource is None:
        return
    url = webview.get_uri()

    def received(res, result):
        try:
            data = res.get_data_finish(result)
        except GLib.Error:
            return
        source_id = next(_SOURCE_IDS)
        _SOURCE_CACHE[source_id] = (url, data[:SOURCE_LIMIT].decode("utf-8", errors="replace"),
                                    len(data) > SOURCE_LIMIT)
        while len(_SOURCE_CACHE) > 10:
            _SOURCE_CACHE.popitem(last=False)
        open_url(f"{navigation.INTERNAL_SCHEME}://source?id={source_id}")

    resource.get_data(None, received)


def _highlight(line):
    """Escape HTML e colore sui nomi dei tag: il sorgente resta solo testo."""
    return _TAG_RE.sub(r'\1<span class="tag">\2</span>', html.escape(line))


def render_source_page(params):
    source_id = params.get("id", "")
    entry = _SOURCE_CACHE.get(int(source_id)) if source_id.isdigit() else None
    if entry is None:
        return ('<!doctype html><meta charset="utf-8"><body style="background:#0e0b19;color:#8d84b8;'
                'font-family:Fira Sans Condensed,sans-serif;padding:24px">'
                + html.escape(_("Sorgente non più disponibile: riaprila con Ctrl+U dalla pagina.")) + "</body>")
    url, text, truncated = entry
    lines = "\n".join(f'<span class="line">{_highlight(line)}</span>' for line in text.splitlines())
    note = f'<p class="note">{html.escape(_("Mostrati solo i primi 2 MB."))}</p>' if truncated else ""
    return utils.render_template(
        "source.html", title=html.escape(_("Sorgente: {url}").format(url=url)), url=html.escape(url),
        lines=lines, note=note,
    )


class LocalServersPopover(Gtk.Popover):
    """Controlla quali porte di sviluppo rispondono su localhost (IPv4 e IPv6)."""

    def __init__(self, ports, on_open):
        super().__init__()
        self.ports = ports
        self.on_open = on_open
        self._generation = 0
        self._pending = 0
        self._found = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(8)
        self.status = Gtk.Label(xalign=0)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(self.status, False, False, 0)
        box.pack_start(self.list_box, False, False, 0)
        box.show_all()
        self.add(box)
        self.connect("show", lambda _p: self.scan())

    def scan(self):
        self._generation += 1
        generation = self._generation
        self._pending = len(self.ports)
        self._found = []
        for child in self.list_box.get_children():
            self.list_box.remove(child)
        if not self.ports:
            self.status.set_text(_("Nessuna porta da controllare: aggiungile a dev_ports in config.json"))
            return
        self.status.set_text(_("Cerco server locali…"))

        client = Gio.SocketClient()
        client.set_timeout(1)
        for port in self.ports:
            client.connect_to_host_async(
                f"localhost:{port}", port, None, self._on_connected, (generation, port)
            )

    def _on_connected(self, client, result, data):
        generation, port = data
        try:
            client.connect_to_host_finish(result).close(None)
            reachable = True
        except GLib.Error:
            reachable = False
        if generation != self._generation:
            return  # risultato di una scansione vecchia
        if reachable:
            self._found.append(port)
        self._pending -= 1
        if self._pending == 0:
            self._show_results()

    def _show_results(self):
        if not self._found:
            ports = ", ".join(str(p) for p in self.ports)
            self.status.set_text(_("Nessun server attivo su {ports}").format(ports=ports))
            return
        self.status.set_text(_("Server attivi (Alt+numero per aprire):"))
        for number, port in enumerate(sorted(self._found), 1):
            url = f"http://localhost:{port}/"
            label = f"_{number}  localhost:{port}" if number < 10 else f"localhost:{port}"
            button = Gtk.Button.new_with_mnemonic(label)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_child().set_xalign(0)
            button.connect("clicked", self._on_button_clicked, url)
            self.list_box.pack_start(button, False, False, 0)
            button.show()
            if number == 1:
                button.grab_focus()

    def _on_button_clicked(self, _button, url):
        self.popdown()
        self.on_open(url)


# --- Pannello rete -------------------------------------------------------


class NetworkEntry:
    """Una richiesta vista dal WebView: metodo, URL, stato, tipo, durata."""

    def __init__(self, request):
        self.method = request.get_http_method() or "GET"
        self.uri = request.get_uri()
        self.status = None
        self.mime = ""
        self.error = None
        self.duration_ms = None
        self.headers = []
        headers = request.get_http_headers()
        if headers is not None:
            headers.foreach(lambda name, value, *_: self.headers.append((name, value)))
        self._start = time.monotonic()

    def fail(self, error):
        self.error = error.message

    def finish(self, resource):
        self.duration_ms = int((time.monotonic() - self._start) * 1000)
        response = resource.get_response()
        if response is not None:
            self.status = response.get_status_code() or None
            self.mime = response.get_mime_type() or ""

    @property
    def status_text(self):
        if self.error:
            return _("errore")
        if self.duration_ms is None:
            return "…"
        return str(self.status) if self.status else "—"

    def row(self):
        kind = self.mime.split("/")[-1][:12] if self.mime else ""
        timing = "" if self.duration_ms is None else f"{self.duration_ms} ms"
        return [self.method, self.status_text, kind, timing, self.uri, self]


def curl_command(entry):
    """Comando curl equivalente (header noti all'interfaccia, corpo non disponibile)."""
    parts = ["curl"]
    if entry.method != "GET":
        parts += ["-X", entry.method]
    for name, value in entry.headers:
        parts += ["-H", f"{name}: {value}"]
    parts.append(entry.uri)
    return " ".join(shlex.quote(p) for p in parts)


class NetworkPanel(Gtk.Box):
    title = _("Rete")

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        self.browser = window
        self.tab = None

        # metodo, stato, tipo, tempo, url, NetworkEntry
        self.store = Gtk.ListStore(str, str, str, str, str, object)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_tooltip_column(4)
        for title, column in ((_("Metodo"), 0), (_("Stato"), 1), (_("Tipo"), 2), (_("Tempo"), 3), ("URL", 4)):
            renderer = Gtk.CellRendererText()
            if column == 4:
                renderer.set_property("ellipsize", Pango.EllipsizeMode.MIDDLE)
            col = Gtk.TreeViewColumn(title, renderer, text=column)
            col.set_resizable(True)
            col.set_expand(column == 4)
            self.view.append_column(col)

        scrolled = Gtk.ScrolledWindow()
        scrolled.add(self.view)
        self.pack_start(scrolled, True, True, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        clear_button = Gtk.Button(label=_("Pulisci"))
        clear_button.connect("clicked", self._on_clear)
        curl_button = Gtk.Button(label=_("Copia come curl"))
        curl_button.connect("clicked", self._on_copy_curl)
        buttons.pack_start(clear_button, False, False, 0)
        buttons.pack_start(curl_button, False, False, 0)
        self.pack_start(buttons, False, False, 0)

    def set_active(self, active):
        pass

    def show_tab(self, tab):
        self.tab = tab
        self.store.clear()
        for entry in tab.network_log:
            self.store.append(entry.row())

    def entry_added(self, tab, entry):
        if tab is not self.tab:
            return
        self.store.append(entry.row())
        while len(self.store) > len(tab.network_log):
            self.store.remove(self.store.get_iter_first())

    def entry_updated(self, tab, entry):
        if tab is not self.tab:
            return
        for row in self.store:
            if row[5] is entry:
                row[1], row[2], row[3] = entry.row()[1:4]
                break

    def log_cleared(self, tab):
        if tab is self.tab:
            self.store.clear()

    def _on_clear(self, _button):
        if self.tab is not None:
            self.tab.network_log.clear()
        self.store.clear()

    def _on_copy_curl(self, _button):
        model, tree_iter = self.view.get_selection().get_selected()
        if tree_iter is None:
            self.browser.show_status(_("Seleziona prima una richiesta"))
            return
        command = curl_command(model[tree_iter][5])
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(command, -1)
        self.browser.show_status(_("Comando curl copiato negli appunti"))


# --- Dati del sito -------------------------------------------------------

_LOCAL_STORAGE_JS = "JSON.stringify(Object.entries(window.localStorage))"


def _record_matches(record_name, host):
    return host == record_name or host.endswith("." + record_name)


class SiteDataDialog(Gtk.Dialog):
    """Cookie e localStorage del sito corrente, con pulizia dei dati.

    Tutto ciò che arriva dalla pagina è mostrato come semplice testo.
    """

    def __init__(self, window, webview):
        self.host = navigation.http_host(webview.get_uri())
        super().__init__(title=_("Dati del sito: {host}").format(host=self.host), transient_for=window)
        self.set_default_size(720, 420)
        self.browser = window
        self.webview = webview
        self._closed = False

        self.cookies = Gtk.ListStore(str, str, str, str, str, str)
        self.storage = Gtk.ListStore(str, str)
        notebook = Gtk.Notebook()
        notebook.append_page(
            self._table(self.cookies, (_("Nome"), _("Valore"), _("Dominio"), _("Percorso"), _("Scadenza"),
                                       _("Flag"))),
            Gtk.Label(label=_("Cookie")),
        )
        notebook.append_page(self._table(self.storage, (_("Chiave"), _("Valore"))), Gtk.Label(label="localStorage"))
        self.get_content_area().pack_start(notebook, True, True, 0)

        clear_button = self.add_button(_("Cancella dati del sito"), 1)
        clear_button.get_style_context().add_class("destructive-action")
        self.add_button(_("Chiudi"), Gtk.ResponseType.CLOSE)
        self.connect("response", self._on_response)
        self.connect("destroy", self._on_destroy)
        self.show_all()
        self.refresh()

    @staticmethod
    def _table(store, titles):
        view = Gtk.TreeView(model=store)
        for column, title in enumerate(titles):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, renderer, text=column)
            col.set_resizable(True)
            col.set_expand(column == 1)
            view.append_column(col)
        view.set_tooltip_column(1)
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(view)
        return scrolled

    def _on_destroy(self, _dialog):
        self._closed = True

    def refresh(self):
        if self._closed:
            return  # finestra chiusa prima del ricaricamento: il WebView potrebbe non esserci più
        self.cookies.clear()
        self.storage.clear()
        uri = self.webview.get_uri()
        self.webview.get_context().get_cookie_manager().get_cookies(uri, None, self._on_cookies)
        self.webview.evaluate_javascript(
            _LOCAL_STORAGE_JS, -1, TOOLS_WORLD, None, None, self._on_storage
        )

    def _on_cookies(self, manager, result):
        try:
            cookies = manager.get_cookies_finish(result)
        except GLib.Error as e:
            self.browser.show_status(_("Cookie non leggibili: {error}").format(error=e.message))
            return
        for cookie in cookies:
            expires = cookie.get_expires()
            flags = [name for name, on in (("HttpOnly", cookie.get_http_only()),
                                           ("Secure", cookie.get_secure())) if on]
            self.cookies.append([
                cookie.get_name(), cookie.get_value(), cookie.get_domain(), cookie.get_path(),
                expires.format("%Y-%m-%d %H:%M") if expires else _("sessione"), " ".join(flags),
            ])

    def _on_storage(self, webview, result):
        try:
            value = webview.evaluate_javascript_finish(result)
            entries = json.loads(value.to_string())
        except (GLib.Error, ValueError):
            return  # pagina senza localStorage (es. sr://, about:blank)
        for key, item in entries:
            self.storage.append([str(key), str(item)])

    def _on_response(self, _dialog, response):
        if response == 1:
            self._confirm_clear()
        else:
            self.destroy()

    def _confirm_clear(self):
        confirm = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=_("Cancellare cookie, storage e cache di {host}?").format(host=self.host),
        )
        confirm.format_secondary_text(_("Verrai disconnesso dal sito. Non si può annullare."))
        answer = confirm.run()
        confirm.destroy()
        if answer == Gtk.ResponseType.OK:
            manager = self.webview.get_context().get_website_data_manager()
            manager.fetch(WebKit2.WebsiteDataTypes.ALL, None, self._on_fetched)

    def _on_fetched(self, manager, result):
        try:
            records = [r for r in manager.fetch_finish(result) if _record_matches(r.get_name(), self.host)]
        except GLib.Error as e:
            self.browser.show_status(_("Dati del sito non leggibili: {error}").format(error=e.message))
            return
        manager.remove(WebKit2.WebsiteDataTypes.ALL, records, None, self._on_removed)

    def _on_removed(self, manager, result):
        try:
            manager.remove_finish(result)
        except GLib.Error as e:
            self.browser.show_status(_("Dati del sito non cancellati: {error}").format(error=e.message))
            return
        self.browser.show_status(_("Dati di {host} cancellati").format(host=self.host))
        self.webview.reload()
        GLib.timeout_add(800, lambda: self.refresh() or GLib.SOURCE_REMOVE)


# --- Screenshot ----------------------------------------------------------


def screenshot_dir():
    pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    return pictures or GLib.get_home_dir()


def take_screenshot(webview, on_done):
    """Cattura l'intera pagina in PNG; on_done(percorso, errore)."""

    def finished(view, result):
        try:
            surface = view.get_snapshot_finish(result)
            path = os.path.join(screenshot_dir(), time.strftime("shellrunner-%Y%m%d-%H%M%S.png"))
            surface.write_to_png(path)
        except (GLib.Error, OSError, cairo.Error) as e:
            on_done(None, getattr(e, "message", str(e)))
            return
        on_done(path, None)

    webview.get_snapshot(
        WebKit2.SnapshotRegion.FULL_DOCUMENT, WebKit2.SnapshotOptions.NONE, None, finished
    )
