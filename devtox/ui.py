"""Componenti d'interfaccia: command palette, ricerca nella pagina, Scudi, pannello laterale."""

from gi.repository import Gdk, GLib, Gtk, Pango, WebKit2

from . import navigation
from .i18n import _

PALETTE_MAX_ROWS = 12
FIND_MAX_MATCHES = 1000
SIDE_PANEL_WIDTH = 400


def fuzzy_score(query, text):
    """>0 se la voce corrisponde: testo contenuto (meglio se all'inizio) o iniziali.

    "term" trova "Terminale"; "nt" trova "Nuova tab" (iniziali delle parole).
    """
    query, text = query.lower().strip(), text.lower()
    if not query:
        return 1
    index = text.find(query)
    if index >= 0:
        return 1000 - index
    initials = "".join(word[0] for word in text.split() if word)
    position = -1
    for char in query.replace(" ", ""):
        position = initials.find(char, position + 1)
        if position < 0:
            return 0
    return 500


class PaletteItem:
    """Una voce della palette: titolo, dettaglio a destra, icona e azione."""

    __slots__ = ("title", "detail", "icon", "action", "score")

    def __init__(self, title, detail, icon, action):
        self.title = title
        self.detail = detail
        self.icon = icon
        self.action = action
        self.score = 0


# --- Command palette -----------------------------------------------------


class CommandPalette(Gtk.Revealer):
    """Ctrl+K: un campo per comandi, tab aperte, preferiti, cronologia e ricerche.

    provide(text) restituisce le voci candidate; qui si filtrano e ordinano.
    """

    def __init__(self, provide, on_closed):
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.set_transition_duration(160)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(10)
        self._provide = provide
        self._on_closed = on_closed
        self._items = []

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(_("Comando, tab, preferito o indirizzo…"))
        self.entry.get_style_context().add_class("palette-entry")
        self.entry.connect("changed", lambda _e: self.refresh())
        self.entry.connect("key-press-event", self._on_key)
        self.entry.connect("activate", lambda _e: self._run_selected())
        self.entry.connect("focus-out-event", self._on_focus_out)

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.list.connect("row-activated", lambda _l, row: self._run(row.get_index()))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_max_content_height(420)
        scrolled.set_propagate_natural_height(True)
        scrolled.add(self.list)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("palette")
        box.set_size_request(640, -1)
        box.pack_start(self.entry, False, False, 0)
        box.pack_start(scrolled, False, False, 0)
        self.add(box)

    def is_open(self):
        return self.get_reveal_child()

    def open(self, text=""):
        self.show_all()
        self.set_reveal_child(True)
        self.entry.set_text(text)
        self.refresh()
        self.entry.grab_focus()
        self.entry.set_position(-1)

    def close(self):
        if self.is_open():
            self.set_reveal_child(False)
            self._on_closed()

    def refresh(self):
        text = self.entry.get_text().strip()
        items = []
        for item in self._provide(text):
            item.score = fuzzy_score(text, item.title + " " + item.detail) if item.score == 0 else item.score
            if item.score > 0:
                items.append(item)
        items.sort(key=lambda i: -i.score)
        self._items = items[:PALETTE_MAX_ROWS]

        for row in self.list.get_children():
            self.list.remove(row)
        for item in self._items:
            self.list.add(self._make_row(item))
        self.list.show_all()
        first = self.list.get_row_at_index(0)
        if first is not None:
            self.list.select_row(first)

    @staticmethod
    def _make_row(item):
        icon = Gtk.Image.new_from_icon_name(item.icon, Gtk.IconSize.MENU)
        title = Gtk.Label(label=item.title, xalign=0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        detail = Gtk.Label(label=item.detail, xalign=1)
        detail.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        detail.set_max_width_chars(36)
        detail.get_style_context().add_class("dim-label")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(6)
        box.pack_start(icon, False, False, 0)
        box.pack_start(title, True, True, 0)
        box.pack_start(detail, False, False, 0)
        row = Gtk.ListBoxRow()
        row.add(box)
        return row

    def _move(self, offset):
        row = self.list.get_selected_row()
        index = (row.get_index() if row else -1) + offset
        target = self.list.get_row_at_index(max(0, min(index, len(self._items) - 1)))
        if target is not None:
            self.list.select_row(target)
            target.grab_focus()
            self.entry.grab_focus_without_selecting()

    def _on_key(self, _entry, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self._move(1)
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab):
            self._move(-1)
            return True
        return False

    def _on_focus_out(self, _entry, _event):
        # Il clic su una riga sposta il focus: chiudiamo solo se esce davvero dalla palette
        GLib.idle_add(self._close_if_unfocused)
        return False

    def _close_if_unfocused(self):
        focus = self.get_toplevel().get_focus()
        if focus is None or not focus.is_ancestor(self):
            self.close()
        return GLib.SOURCE_REMOVE

    def _run_selected(self):
        row = self.list.get_selected_row()
        if row is not None:
            self._run(row.get_index())

    def _run(self, index):
        if 0 <= index < len(self._items):
            action = self._items[index].action
            self.close()
            action()


# --- Ricerca nella pagina ------------------------------------------------


class FindBar(Gtk.Revealer):
    """Ctrl+F: ricerca nella pagina, in alto a destra come in VS Code."""

    def __init__(self, current_webview):
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.set_transition_duration(140)
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(8)
        self.set_margin_end(16)
        self._current_webview = current_webview
        self._controller = None
        self._handlers = []

        self.entry = Gtk.SearchEntry()
        self.entry.set_width_chars(28)
        self.entry.connect("search-changed", lambda _e: self._search())
        self.entry.connect("activate", lambda _e: self.next())
        self.entry.connect("key-press-event", self._on_key)
        self.count = Gtk.Label()
        self.count.get_style_context().add_class("find-count")

        previous_button = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.BUTTON)
        previous_button.set_tooltip_text(_("Precedente (Shift+Invio)"))
        previous_button.connect("clicked", lambda _b: self.previous())
        next_button = Gtk.Button.new_from_icon_name("go-down-symbolic", Gtk.IconSize.BUTTON)
        next_button.set_tooltip_text(_("Successivo (Invio)"))
        next_button.connect("clicked", lambda _b: self.next())
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
        close_button.set_tooltip_text(_("Chiudi (Esc)"))
        close_button.connect("clicked", lambda _b: self.close())

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.get_style_context().add_class("findbar")
        for widget in (self.entry, self.count, previous_button, next_button, close_button):
            box.pack_start(widget, False, False, 0)
        self.add(box)

    def is_open(self):
        return self.get_reveal_child()

    def open(self):
        self.show_all()
        self.set_reveal_child(True)
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self._search()

    def close(self):
        if self._controller is not None:
            self._controller.search_finish()
        self._detach()
        self.set_reveal_child(False)
        webview = self._current_webview()
        if webview is not None:
            webview.grab_focus()

    def next(self):
        if self._controller is not None and self.entry.get_text():
            self._controller.search_next()

    def previous(self):
        if self._controller is not None and self.entry.get_text():
            self._controller.search_previous()

    def _attach(self):
        controller = self._current_webview().get_find_controller()
        if controller is self._controller:
            return controller
        self._detach()
        self._controller = controller
        self._handlers = [
            controller.connect("counted-matches", self._on_counted),
            controller.connect("failed-to-find-text", self._on_failed),
        ]
        return controller

    def _detach(self):
        for handler in self._handlers:
            self._controller.disconnect(handler)
        self._handlers = []
        self._controller = None

    def _search(self):
        text = self.entry.get_text()
        controller = self._attach()
        if not text:
            controller.search_finish()
            self.count.set_text("")
            return
        options = WebKit2.FindOptions.CASE_INSENSITIVE | WebKit2.FindOptions.WRAP_AROUND
        controller.count_matches(text, options, FIND_MAX_MATCHES)
        controller.search(text, options, FIND_MAX_MATCHES)

    def _on_counted(self, _controller, count):
        self.count.get_style_context().remove_class("error")
        self.count.set_text(_("1 risultato") if count == 1 else _("{count} risultati").format(count=count))

    def _on_failed(self, _controller):
        self.count.get_style_context().add_class("error")
        self.count.set_text(_("Nessun risultato"))

    def _on_key(self, _entry, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and event.state & Gdk.ModifierType.SHIFT_MASK:
            self.previous()
            return True
        return False


# --- Scudi e connessione -------------------------------------------------


def connection_summary(webview):
    """(icona, testo breve, livello) per la connessione della pagina corrente.

    livello: "secure", "local", "internal" o "insecure".
    """
    uri = webview.get_uri() or ""
    if uri.startswith(navigation.INTERNAL_SCHEME + "://") or uri.startswith("about:") or not uri:
        return "view-reveal-symbolic", _("Pagina interna di Devtox"), "internal"
    host = navigation.http_host(uri)
    if host and navigation.is_local_host(host):
        return "computer-symbolic", _("Server locale: il traffico non lascia questo PC"), "local"
    if uri.startswith("https://"):
        ok, certificate, errors = webview.get_tls_info()
        if ok and certificate is not None and not errors:
            issuer = _common_name(certificate.get_property("issuer-name"))
            expiry = certificate.get_property("not-valid-after")
            if expiry:
                text = _("Connessione cifrata. Certificato di {issuer}, valido fino al {date}").format(
                    issuer=issuer, date=expiry.format("%x"))
            else:
                text = _("Connessione cifrata. Certificato di {issuer}").format(issuer=issuer)
            return "channel-secure-symbolic", text, "secure"
    return "channel-insecure-symbolic", _("Connessione NON cifrata: chi è sulla rete può leggerla"), "insecure"


def _common_name(distinguished_name):
    for part in (distinguished_name or "").split(","):
        key, _sep, value = part.strip().partition("=")
        if key == "CN":
            return value
    return distinguished_name or _("sconosciuto")


class ShieldsPopover(Gtk.Popover):
    """Stato della connessione e scudi per il sito corrente.

    on_toggle(host, scudo, attivo) applica la modifica; scudo è
    "trackers", "fingerprint" o "javascript".
    """

    SHIELDS = (
        ("trackers", _("Blocca tracker"), _("Usa la blocklist locale su questo sito")),
        ("fingerprint", _("Anti-fingerprinting"), _("Canvas e WebGL restituiscono valori alterati")),
        ("javascript", "JavaScript", _("Spegnilo per leggere pagine senza script")),
    )

    def __init__(self, on_toggle):
        super().__init__()
        self._on_toggle = on_toggle
        self._host = None
        self._syncing = False

        self.host_label = Gtk.Label(xalign=0)
        self.host_label.get_style_context().add_class("shields-host")
        self.host_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.connection_icon = Gtk.Image()
        self.connection_label = Gtk.Label(xalign=0)
        self.connection_label.set_line_wrap(True)
        self.connection_label.set_max_width_chars(42)
        connection = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        connection.pack_start(self.connection_icon, False, False, 0)
        connection.pack_start(self.connection_label, True, True, 0)

        grid = Gtk.Grid(column_spacing=16, row_spacing=10)
        self.switches = {}
        for row, (key, title, hint) in enumerate(self.SHIELDS):
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            text.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
            hint_label = Gtk.Label(label=hint, xalign=0)
            hint_label.get_style_context().add_class("dim-label")
            text.pack_start(hint_label, False, False, 0)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            switch.connect("notify::active", self._on_switch, key)
            grid.attach(text, 0, row, 1, 1)
            grid.attach(switch, 1, row, 1, 1)
            self.switches[key] = switch

        self.private_label = Gtk.Label(
            label=_("Tab privata: niente cronologia; cookie e dati spariscono quando chiudi l'ultima tab privata."),
            xalign=0,
        )
        self.private_label.get_style_context().add_class("private-note")
        self.private_label.set_line_wrap(True)
        self.private_label.set_no_show_all(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(14)
        box.pack_start(self.host_label, False, False, 0)
        box.pack_start(connection, False, False, 0)
        box.pack_start(Gtk.Separator(), False, False, 0)
        box.pack_start(grid, False, False, 0)
        box.pack_start(self.private_label, False, False, 0)
        box.show_all()
        self.add(box)

    def update(self, webview, host, states, private, available=None):
        """states: {"trackers": bool, ...}; available: scudi regolabili (gli altri sono spenti
        nelle impostazioni generali, quindi il loro interruttore non avrebbe effetto)."""
        self._host = host
        icon, text, level = connection_summary(webview)
        self.host_label.set_text(host or "Devtox")
        self.connection_icon.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
        self.connection_label.set_text(text)
        style = self.connection_label.get_style_context()
        style.add_class("insecure") if level == "insecure" else style.remove_class("insecure")
        self._syncing = True
        for key, switch in self.switches.items():
            switch.set_active(states[key])
            switch.set_sensitive(host is not None and (available is None or key in available))
        self._syncing = False
        self.private_label.set_visible(private)

    def _on_switch(self, switch, _param, key):
        if not self._syncing and self._host is not None:
            self._on_toggle(self._host, key, switch.get_active())


class SidePanel(Gtk.Revealer):
    """Pannello a destra (Rete, Memoria, Download, IA) che scivola dentro e fuori."""

    def __init__(self, panels, on_change):
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.set_transition_duration(220)
        self.panels = panels
        self._on_change = on_change
        self._active = None

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        for name, panel in panels.items():
            self.stack.add_titled(panel, name, panel.title)
        self.stack.connect("notify::visible-child", lambda *_: self._update_active())

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_border_width(6)
        header.pack_start(Gtk.StackSwitcher(stack=self.stack), True, False, 0)
        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_button.set_tooltip_text(_("Chiudi pannello"))
        close_button.connect("clicked", lambda _b: self.close())
        header.pack_end(close_button, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_size_request(SIDE_PANEL_WIDTH, -1)
        box.get_style_context().add_class("side-panel")
        box.pack_start(header, False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        self.add(box)
        self.connect("notify::reveal-child", lambda *_: self._update_active())

    def is_open(self):
        return self.get_reveal_child()

    def current(self):
        return self.stack.get_visible_child_name()

    def open(self, name):
        self.stack.set_visible_child_name(name)
        self.set_reveal_child(True)

    def close(self):
        self.set_reveal_child(False)

    def toggle(self, name):
        if self.is_open() and self.current() == name:
            self.close()
        else:
            self.open(name)

    def _update_active(self):
        """Attiva solo il pannello visibile (es. il timer della memoria)."""
        active = self.panels[self.current()] if self.is_open() else None
        if active is not self._active:
            if self._active is not None:
                self._active.set_active(False)
            self._active = active
            if active is not None:
                active.set_active(True)
        self._on_change()
