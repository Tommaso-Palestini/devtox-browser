"""Finestra principale: header, barra laterale, tab, pannelli, terminale e scorciatoie."""

import collections
import os
import time

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, WebKit2

from . import actions, ai, devtools, monitor, navigation, privacy, theme, utils
from .downloads import DownloadsPanel
from .i18n import _
from .tabs import BrowserTab
from .terminal import TerminalPanel
from .ui import CommandPalette, FindBar, PaletteItem, ShieldsPopover, SidePanel, connection_summary

SUSPEND_CHECK_SECONDS = 30
SESSION_SAVE_SECONDS = 15
TERMINAL_SHARE = 0.38       # quota di altezza del terminale quando si apre
TERMINAL_SLIDE_MS = 260
CLOSED_TABS_LIMIT = 20
ZOOM_LEVELS = (0.5, 0.67, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)


class BrowserWindow(Gtk.Window):
    def __init__(self, config, context, content_manager, content_filter, content_scripts,
                 storage, pages):
        super().__init__(title=utils.APP_TITLE)
        self.config = config
        self.context = context
        self.content_manager = content_manager
        self.content_filter = content_filter
        self.content_scripts = content_scripts
        self.storage = storage
        self._pages = pages                # pagine devtox:// da registrare anche sul profilo privato
        self._private_context = None       # creato alla prima tab privata
        self.https_guard = privacy.HttpsGuard(config, content_filter, self._is_private_view)
        self._tabs = {}                    # contenitore del Notebook -> BrowserTab
        self._view_tabs = {}               # WebView -> BrowserTab
        self._closed_tabs = collections.deque(maxlen=CLOSED_TABS_LIMIT)
        self._syncing = False              # i toggle non reagiscono agli aggiornamenti dal codice
        self._status_timer = 0
        self._last_responsive = devtools.DEFAULT_RESPONSIVE
        self._terminal_open = False
        self._session_dirty = False
        self._restoring = False            # durante il ripristino nessuna tab si carica da sola

        self.set_default_size(1280, 820)
        self.connect("key-press-event", lambda _w, event: actions.handle_key(self, event))

        # Pannelli (il terminale per primo: monitor e RAM ne leggono i PID delle shell)
        self.terminal_panel = TerminalPanel(on_hide=self.hide_terminal)
        self.network_panel = devtools.NetworkPanel(self)
        self.memory_panel = monitor.MemoryPanel(self)
        self.downloads_panel = DownloadsPanel(self)
        self.downloads_panel.attach(context)
        self.ai_panel = ai.AIPanel(self)
        self.side_panel = SidePanel(
            {"rete": self.network_panel, "memoria": self.memory_panel,
             "download": self.downloads_panel, "ia": self.ai_panel},
            on_change=self._sync_rail,
        )

        # Tab del browser con sopra: avvisi, ricerca nella pagina e palette
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_show_border(False)
        self.notebook.get_style_context().add_class("browser-tabs")
        self.notebook.connect("switch-page", self._on_switch_page)
        self.notebook.connect("page-reordered", lambda *_: self._mark_session_dirty())

        self.status_label = Gtk.Label()
        self.status_label.get_style_context().add_class("status-toast")
        self.status_revealer = Gtk.Revealer()
        self.status_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.status_revealer.set_transition_duration(200)
        self.status_revealer.set_halign(Gtk.Align.CENTER)
        self.status_revealer.set_valign(Gtk.Align.END)
        self.status_revealer.add(self.status_label)
        self.find_bar = FindBar(self.current_webview)
        self.palette = CommandPalette(self._palette_items, on_closed=self._focus_page)

        overlay = Gtk.Overlay()
        overlay.add(self.notebook)
        overlay.add_overlay(self.status_revealer)
        overlay.set_overlay_pass_through(self.status_revealer, True)
        overlay.add_overlay(self.find_bar)
        overlay.add_overlay(self.palette)

        browser_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        browser_row.pack_start(overlay, True, True, 0)
        browser_row.pack_start(self.side_panel, False, False, 0)

        # Browser sopra, terminale sotto: il divisore resta trascinabile
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.main_paned.pack1(browser_row, True, False)
        self.main_paned.pack2(self.terminal_panel, False, False)
        self._paned_animation = theme.Animation(self.main_paned)

        self.load_trace = theme.LoadTrace()
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.pack_start(self._build_rail(), False, False, 0)
        body.pack_start(self.main_paned, True, True, 0)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(self.load_trace, False, False, 0)
        root.pack_start(body, True, True, 0)

        self.set_titlebar(self._build_header())
        self.add(root)

        root.show_all()
        self.terminal_panel.hide()
        self._open_initial_tabs()
        self._sync_rail()

        GLib.timeout_add_seconds(SUSPEND_CHECK_SECONDS, self._suspend_inactive_tabs)
        GLib.timeout_add_seconds(SESSION_SAVE_SECONDS, self._save_session_if_dirty)

    # --- Costruzione interfaccia ----------------------------------------

    def _build_header(self):
        """Header compatto al posto della barra del titolo, come nei browser moderni."""
        self.back_button = self._icon_button("go-previous-symbolic", _("Indietro (Alt+←)"))
        self.back_button.connect("clicked", lambda _b: self.current_webview().go_back())
        self.forward_button = self._icon_button("go-next-symbolic", _("Avanti (Alt+→)"))
        self.forward_button.connect("clicked", lambda _b: self.current_webview().go_forward())
        self.reload_button = self._icon_button("view-refresh-symbolic", _("Ricarica (F5)"))
        self.reload_button.get_style_context().add_class("reload")
        self.reload_button.connect("clicked", self._on_reload_clicked)

        self.url_entry = Gtk.Entry()
        self.url_entry.get_style_context().add_class("url-entry")
        self.url_entry.set_hexpand(True)
        self.url_entry.set_placeholder_text(
            _("Cerca con {engine} o scrivi un indirizzo").format(engine=navigation.search_engine_name())
        )
        self.url_entry.connect("activate", self._on_url_activate)
        self.url_entry.connect("changed", self._on_url_typed)
        self.url_entry.connect("icon-press", self._on_url_icon_press)
        self._build_completion()

        self.shields_popover = ShieldsPopover(self._on_shield_toggled)
        self.shields_button = Gtk.MenuButton()
        self.shields_button.set_image(
            Gtk.Image.new_from_icon_name("security-high-symbolic", Gtk.IconSize.BUTTON)
        )
        self.shields_button.get_style_context().add_class("shields")
        self.shields_button.set_tooltip_text(_("Scudi e connessione del sito"))
        self.shields_button.set_popover(self.shields_popover)
        self.shields_popover.connect("show", lambda _p: self._update_shields_popover())

        menu_button = Gtk.MenuButton()
        menu_button.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        menu_button.set_tooltip_text("Menu")
        menu_button.set_popup(self._build_menu())

        # Il marchio sopra il rail: dice di che prodotto si tratta e apre una nuova tab
        mark = Gtk.Button()
        mark.set_name("mark")
        mark.set_image(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(
            os.path.join(utils.RESOURCES_DIR, "devtox.svg"), 24, 24)))
        mark.set_tooltip_text(_("Devtox: nuova tab (Ctrl+T)"))
        mark.connect("clicked", lambda _b: self.new_tab_and_focus())

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.get_style_context().add_class("deck-header")
        for widget in (mark, self.back_button, self.forward_button, self.reload_button):
            header.pack_start(widget)
        header.set_custom_title(self.url_entry)
        header.pack_end(menu_button)
        header.pack_end(self.shields_button)
        header.show_all()
        return header

    def _build_completion(self):
        """Suggerimenti dalla cronologia locale mentre scrivi l'indirizzo."""
        self.completion_store = Gtk.ListStore(str, str)  # url, titolo
        completion = Gtk.EntryCompletion(model=self.completion_store)
        completion.set_minimum_key_length(2)
        completion.set_match_func(lambda *_: True, None)  # il filtro lo fa già SQLite
        title_cell = Gtk.CellRendererText(ellipsize=3, max_width_chars=50)
        url_cell = Gtk.CellRendererText(ellipsize=2, foreground=theme.MUTED, max_width_chars=60)
        completion.pack_start(title_cell, True)
        completion.add_attribute(title_cell, "text", 1)
        completion.pack_start(url_cell, False)
        completion.add_attribute(url_cell, "text", 0)
        completion.connect("match-selected", self._on_completion_selected)
        self.url_entry.set_completion(completion)

    def _build_rail(self):
        """Barra laterale: strumenti sempre a portata, RAM sempre visibile."""
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        rail.set_name("rail")

        def rail_icon(icon):
            image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            image.set_pixel_size(18)
            return image

        def rail_toggle(icon, tooltip, callback, shell=False):
            button = Gtk.ToggleButton()
            button.set_image(rail_icon(icon))
            button.set_tooltip_text(tooltip)
            if shell:
                button.get_style_context().add_class("shell")
            button.connect("toggled", lambda _b: None if self._syncing else callback())
            rail.pack_start(button, False, False, 0)
            return button

        def rail_button(icon, tooltip, callback):
            button = Gtk.Button()
            button.set_image(rail_icon(icon))
            button.set_tooltip_text(tooltip)
            button.connect("clicked", lambda _b: callback())
            rail.pack_start(button, False, False, 0)
            return button

        self.rail_terminal = rail_toggle(
            "dx-terminal-symbolic", _("Terminale (Ctrl+`)"), self.toggle_terminal, shell=True
        )
        self.servers_button = Gtk.MenuButton()
        self.servers_button.set_image(rail_icon("dx-servers-symbolic"))
        self.servers_button.set_tooltip_text(_("Server locali (Ctrl+Shift+L)"))
        self.servers_button.get_style_context().add_class("shell")
        self.servers_button.set_direction(Gtk.ArrowType.RIGHT)
        self.servers_button.set_popover(
            devtools.LocalServersPopover(self.config["dev_ports"], self.new_tab)
        )
        rail.pack_start(self.servers_button, False, False, 0)
        rail.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        self.rail_panels = {
            "rete": rail_toggle("dx-network-symbolic", _("Richieste di rete (Ctrl+Shift+E)"),
                                lambda: self.toggle_side_panel("rete")),
            "memoria": rail_toggle("dx-memory-symbolic", _("Memoria e processi (Shift+Esc)"),
                                   lambda: self.toggle_side_panel("memoria")),
            "download": rail_toggle("dx-downloads-symbolic", _("Download (Ctrl+Shift+Y)"),
                                    lambda: self.toggle_side_panel("download")),
            "ia": rail_toggle("dx-assistant-symbolic", _("IA locale con Ollama (Ctrl+Shift+A)"),
                              lambda: self.toggle_side_panel("ia")),
        }
        if not self.config["ai_enabled"]:
            self.rail_panels["ia"].set_no_show_all(True)
        rail.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        self.rail_responsive = rail_toggle("dx-responsive-symbolic", _("Vista responsive (Ctrl+Shift+M)"),
                                           self.toggle_responsive)
        rail_button("dx-screenshot-symbolic", _("Screenshot della pagina (Ctrl+Shift+S)"),
                    self.take_screenshot)
        rail_button("dx-site-data-symbolic", _("Cookie e dati del sito (Ctrl+Shift+Canc)"),
                    self.show_site_data)

        self.ram_meter = monitor.RamMeter(self.terminal_panel.shell_pids)
        self.ram_meter.connect("clicked", lambda _b: self.toggle_side_panel("memoria"))
        rail.pack_end(self.ram_meter, False, False, 0)
        return rail

    def _build_menu(self):
        menu = Gtk.Menu()

        def item(label, accel, callback, parent=menu):
            menu_item = Gtk.MenuItem()
            accel_label = Gtk.AccelLabel(label=label, xalign=0)
            if accel:
                key, mods = Gtk.accelerator_parse(accel)
                accel_label.set_accel(key, mods)
            menu_item.add(accel_label)
            menu_item.connect("activate", lambda _i: callback())
            parent.append(menu_item)

        item(_("Palette dei comandi"), "<Control>k", self.open_palette)
        menu.append(Gtk.SeparatorMenuItem())
        item(_("Nuova tab"), "<Control>t", self.new_tab_and_focus)
        item(_("Nuova tab privata"), "<Control><Shift>n", self.new_private_tab)
        item(_("Riapri tab chiusa"), "<Control><Shift>t", self.reopen_closed_tab)
        item(_("Nuovo terminale"), "<Control><Shift>grave", self.new_terminal)
        menu.append(Gtk.SeparatorMenuItem())
        responsive_item = Gtk.MenuItem(label=_("Vista responsive"))
        responsive_menu = Gtk.Menu()
        item(_("Disattivata"), None, lambda: self.set_responsive(None), responsive_menu)
        for name, size in devtools.RESPONSIVE_PRESETS:
            item(f"{name}  {size[0]}×{size[1]}", None,
                 lambda s=size: self.set_responsive(s), responsive_menu)
        responsive_item.set_submenu(responsive_menu)
        menu.append(responsive_item)
        item(_("Modifica blocklist"), None, lambda: self.open_file(privacy.blocklist_path()))
        item(_("Ricarica blocklist"), None, self.reload_blocklist)
        item(_("Personalizza Devtox"), None, lambda: self.new_tab(navigation.SETUP_URL))
        item(_("Apri configurazione"), None, lambda: self.open_file(self.config.path))
        item(_("Strumenti sviluppatore"), "F12", self.show_inspector)
        menu.append(Gtk.SeparatorMenuItem())
        item(_("Guida rapida"), None, lambda: self.new_tab(navigation.WELCOME_URL))
        item(_("Informazioni su Devtox"), None, lambda: self.new_tab(navigation.ABOUT_URL))
        menu.show_all()
        return menu

    @staticmethod
    def _icon_button(icon_name, tooltip):
        button = Gtk.Button.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        button.set_tooltip_text(tooltip)
        return button

    # --- Tab ------------------------------------------------------------

    def _open_initial_tabs(self):
        """Ripristina la sessione precedente (tab sospese) oppure apre la pagina iniziale."""
        saved = self.storage.load_session() if self.config["restore_session"] else []
        if not saved:
            self.new_tab(navigation.START_URL)
            return
        current = 0
        # GTK seleziona da solo la prima pagina inserita: senza questo flag
        # verrebbe caricata anche se non è la tab su cui eri
        self._restoring = True
        for index, entry in enumerate(saved):
            tab = BrowserTab(self._create_webview, self.close_tab,
                             restore=(entry["uri"], entry.get("title"), None))
            self._insert_tab(tab, index, select=False)
            if entry.get("current"):
                current = index
        self._restoring = False
        self.notebook.set_current_page(current)
        if self.current_tab().suspended:
            # set_current_page sulla pagina già attiva non emette switch-page
            self._activate_tab(self.current_tab())

    def _insert_tab(self, tab, position, select=True):
        self._tabs[tab.container] = tab
        index = self.notebook.insert_page(tab.container, tab.label_widget, position)
        self.notebook.set_tab_reorderable(tab.container, True)
        if select:
            self.notebook.set_current_page(index)
        self._mark_session_dirty()
        return index

    def new_tab(self, url=None, related_view=None, private=None):
        """Apre una tab subito dopo quella corrente e la rende attiva."""
        if private is None:
            # Una pagina aperta da una tab privata resta privata
            opener = self._view_tabs.get(related_view) if related_view is not None else None
            private = opener.private if opener is not None else False
        tab = BrowserTab(self._create_webview, self.close_tab, related_view, private=private)
        self._insert_tab(tab, self.notebook.get_current_page() + 1)
        if url:
            tab.webview.load_uri(url)
        return tab

    def new_tab_and_focus(self, private=False):
        self.new_tab(navigation.START_URL, private=private)
        self.focus_url_entry()

    def new_private_tab(self):
        self.new_tab_and_focus(private=True)
        self.show_status(_("Tab privata: niente cronologia, i dati spariscono con l'ultima tab privata"))

    def close_tab(self, tab):
        """Chiude una tab; chiudendo l'ultima si chiude la finestra."""
        if self.notebook.get_n_pages() <= 1:
            self.destroy()
            return
        uri, title, session = tab.snapshot()
        if not tab.private and uri and uri != navigation.START_URL:
            self._closed_tabs.append((uri, title, session))
        self.notebook.remove_page(self.notebook.page_num(tab.container))
        del self._tabs[tab.container]
        self._view_tabs.pop(tab.webview, None)
        tab.destroy()
        if tab.private and not any(t.private for t in self._tabs.values()):
            # Ultima tab privata chiusa: il profilo usa-e-getta sparisce con i suoi dati
            self._private_context = None
        self._mark_session_dirty()

    def reopen_closed_tab(self):
        if not self._closed_tabs:
            self.show_status(_("Nessuna tab chiusa da riaprire"))
            return
        tab = BrowserTab(self._create_webview, self.close_tab, restore=self._closed_tabs.pop())
        self._insert_tab(tab, self.notebook.get_current_page() + 1)

    def current_tab(self):
        page = self.notebook.get_current_page()
        if page < 0:
            return None
        return self._tabs[self.notebook.get_nth_page(page)]

    def current_webview(self):
        tab = self.current_tab()
        return tab.webview if tab is not None else None

    def tab_counts(self):
        tabs = list(self._tabs.values())
        return len(tabs), sum(1 for t in tabs if t.suspended)

    def _ordered_tabs(self):
        return [self._tabs[self.notebook.get_nth_page(i)] for i in range(self.notebook.get_n_pages())]

    def list_tabs(self):
        current = self.current_tab()
        return [
            {"index": index + 1, "title": tab.title, "uri": tab.uri,
             "suspended": tab.suspended, "current": tab is current, "private": tab.private}
            for index, tab in enumerate(self._ordered_tabs())
        ]

    def open_from_cli(self, text):
        url = navigation.resolve_input(text)
        if url:
            self.new_tab(url, private=False)
            self.present()
        return url

    def select_relative_tab(self, offset):
        count = self.notebook.get_n_pages()
        self.notebook.set_current_page((self.notebook.get_current_page() + offset) % count)

    def _select_tab(self, tab):
        self.notebook.set_current_page(self.notebook.page_num(tab.container))

    def _is_private_view(self, webview):
        tab = self._view_tabs.get(webview)
        return tab is not None and tab.private

    def _context_for(self, private):
        if not private:
            return self.context
        if self._private_context is None:
            context = privacy.create_web_context(self.config, private=True)
            navigation.register_internal_scheme(context, self._pages)
            self.downloads_panel.attach(context)
            self._private_context = context
        return self._private_context

    def _create_webview(self, tab, related_view):
        """Crea un WebView con le impostazioni del profilo e collega i segnali."""
        properties = {
            "settings": privacy.create_settings(),
            "user_content_manager": self.content_manager,
            "website_policies": privacy.create_website_policies(),
        }
        if related_view is not None:
            # Popup / target=_blank: WebKit vuole un view "imparentato" (stesso profilo)
            properties["related_view"] = related_view
        else:
            properties["web_context"] = self._context_for(tab.private)
        webview = WebKit2.WebView(**properties)
        # Sfondo scuro anche prima che la pagina disegni: niente lampi bianchi
        webview.set_background_color(theme.rgba(theme.PAGE))
        self._view_tabs[webview] = tab

        webview.connect("notify::uri", self._on_uri_changed)
        webview.connect("notify::title", self._on_title_changed)
        webview.connect("notify::is-loading", self._on_loading_changed)
        webview.connect("notify::estimated-load-progress", self._on_progress_changed)
        webview.connect("load-changed", self._on_load_changed)
        webview.connect("load-failed", self.https_guard.on_load_failed)
        webview.connect("load-failed-with-tls-errors", self.https_guard.on_tls_error)
        webview.connect("decide-policy", self.https_guard.on_decide_policy)
        webview.connect("permission-request", privacy.deny_permission_request)
        webview.connect("resource-load-started", self._on_resource_load_started)
        webview.connect("web-process-terminated", self._on_web_process_terminated)
        webview.connect("create", self._on_create)
        webview.connect("close", self._on_close_request)
        return webview

    # --- Sessione -------------------------------------------------------

    def _mark_session_dirty(self):
        self._session_dirty = True

    def _save_session_if_dirty(self):
        if self._session_dirty:
            self.save_session()
        return GLib.SOURCE_CONTINUE

    def save_session(self):
        """Salva le tab non private (le private non lasciano traccia)."""
        if not self.config["restore_session"]:
            return
        current = self.current_tab()
        tabs = [
            {"uri": tab.uri, "title": tab.title, "current": tab is current}
            for tab in self._ordered_tabs()
            if not tab.private and tab.uri and not navigation.is_one_shot(tab.uri)
        ]
        self.storage.save_session(tabs)
        self._session_dirty = False

    # --- Sospensione tab inattive ---------------------------------------

    def _suspend_inactive_tabs(self):
        minutes = self.config["suspend_after_minutes"]
        if minutes > 0:
            limit = time.monotonic() - minutes * 60
            current = self.current_tab()
            for tab in list(self._tabs.values()):
                if tab is not current and tab.last_active < limit and tab.can_suspend():
                    self._view_tabs.pop(tab.webview, None)
                    tab.suspend()
        return GLib.SOURCE_CONTINUE

    # --- Sincronizzazione con la tab attiva -----------------------------

    def _sync_toolbar(self, webview):
        self.url_entry.set_text(navigation.display_uri(webview.get_uri()))
        self._update_nav_buttons(webview)
        self._update_loading(webview)
        self._update_window_title(webview)
        self._update_site_indicators(webview)
        self._sync_rail()

    def _update_nav_buttons(self, webview):
        self.back_button.set_sensitive(webview.can_go_back())
        self.forward_button.set_sensitive(webview.can_go_forward())

    def _update_loading(self, webview):
        loading = webview.is_loading()
        icon = "process-stop-symbolic" if loading else "view-refresh-symbolic"
        self.reload_button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        style = self.reload_button.get_style_context()
        style.add_class("loading") if loading else style.remove_class("loading")
        self.load_trace.set_progress(webview.get_estimated_load_progress(), loading)

    def _update_window_title(self, webview):
        title = webview.get_title()
        self.set_title(f"{title} - {utils.APP_TITLE}" if title else utils.APP_TITLE)

    def _update_site_indicators(self, webview):
        """Lucchetto e stella nella barra, colore del pulsante Scudi."""
        uri = webview.get_uri()
        host = navigation.http_host(uri)
        icon, text, level = connection_summary(webview)
        primary = None if level == "internal" else icon
        self.url_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, primary)
        self.url_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.PRIMARY, text)
        entry_style = self.url_entry.get_style_context()
        entry_style.add_class("insecure") if level == "insecure" else entry_style.remove_class("insecure")

        if host is not None:
            starred = self.storage.is_bookmarked(uri)
            self.url_entry.set_icon_from_icon_name(
                Gtk.EntryIconPosition.SECONDARY, "starred-symbolic" if starred else "non-starred-symbolic"
            )
            self.url_entry.set_icon_tooltip_text(
                Gtk.EntryIconPosition.SECONDARY,
                _("Togli dai preferiti (Ctrl+D)") if starred else _("Aggiungi ai preferiti (Ctrl+D)"),
            )
        else:
            self.url_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, None)

        states = self._shield_states(host)
        shields_style = self.shields_button.get_style_context()
        lowered = host is not None and not all(states.values())
        shields_style.add_class("shields-down") if lowered else shields_style.remove_class("shields-down")

    def _is_current(self, webview):
        tab = self.current_tab()
        return tab is not None and tab.webview is webview

    def _sync_rail(self):
        """Allinea i pulsanti della barra laterale allo stato reale dei pannelli."""
        self._syncing = True
        self.rail_terminal.set_active(self._terminal_open)
        for name, button in self.rail_panels.items():
            button.set_active(self.side_panel.is_open() and self.side_panel.current() == name)
        tab = self.current_tab()
        self.rail_responsive.set_active(tab is not None and tab.responsive_size is not None)
        self._syncing = False

    # --- Scudi per sito -------------------------------------------------

    _SHIELD_LISTS = {
        "trackers": "shields_down_hosts",
        "fingerprint": "fingerprint_off_hosts",
        "javascript": "javascript_disabled_hosts",
    }

    def _shield_states(self, host):
        return {
            "trackers": host not in self.config["shields_down_hosts"],
            "fingerprint": self.config["fingerprint_protection"]
                           and host not in self.config["fingerprint_off_hosts"],
            "javascript": host not in self.config["javascript_disabled_hosts"],
        }

    def _update_shields_popover(self):
        tab = self.current_tab()
        host = navigation.http_host(tab.webview.get_uri())
        available = {"trackers", "javascript"}
        if self.config["fingerprint_protection"]:
            available.add("fingerprint")
        self.shields_popover.update(tab.webview, host, self._shield_states(host), tab.private, available)

    def _on_shield_toggled(self, host, shield, enabled):
        key = self._SHIELD_LISTS[shield]
        hosts = set(self.config[key])
        hosts.discard(host) if enabled else hosts.add(host)
        self.config.set(key, sorted(hosts))
        webview = self.current_webview()
        names = {"trackers": _("Blocco tracker"), "fingerprint": _("Anti-fingerprinting"),
                 "javascript": "JavaScript"}
        message = _("{shield} attivo su {host}") if enabled else _("{shield} spento su {host}")
        self.show_status(message.format(shield=names[shield], host=host))
        if shield == "trackers":
            self.content_filter.reload(on_done=webview.reload)
        elif shield == "fingerprint":
            self.content_scripts.rebuild()
            webview.reload()
        else:
            webview.reload()
        self._update_site_indicators(webview)

    def _js_allowed(self, uri):
        host = navigation.http_host(uri)
        return host is None or host not in self.config["javascript_disabled_hosts"]

    # --- Segnali dei WebView --------------------------------------------

    def _on_switch_page(self, _notebook, page, _index):
        previous = self.current_tab()
        if previous is not None:
            previous.last_active = time.monotonic()
        if self.find_bar.is_open():
            self.find_bar.close()
        if not self._restoring:
            self._activate_tab(self._tabs[page])

    def _activate_tab(self, tab):
        tab.last_active = time.monotonic()
        if tab.suspended:
            tab.resume()
        # Il focus va alla pagina: la barra indirizzi torna a seguire la tab
        tab.webview.grab_focus()
        self.network_panel.show_tab(tab)
        self._mark_session_dirty()
        GLib.idle_add(self._sync_after_switch, tab)

    def _sync_after_switch(self, tab):
        # Durante "switch-page" la tab corrente è ancora la vecchia
        if tab.webview is not None and self._is_current(tab.webview):
            self._sync_toolbar(tab.webview)
        return GLib.SOURCE_REMOVE

    def _on_uri_changed(self, webview, _param):
        self._mark_session_dirty()
        # Non sovrascrivere quello che l'utente sta scrivendo
        if self._is_current(webview) and not self.url_entry.has_focus():
            self.url_entry.set_text(navigation.display_uri(webview.get_uri()))

    def _on_title_changed(self, webview, _param):
        tab = self._view_tabs.get(webview)
        uri = webview.get_uri()
        if tab is not None and not tab.private and navigation.http_host(uri) and self.config["history_enabled"]:
            self.storage.update_title(uri, webview.get_title())
        if self._is_current(webview):
            self._update_window_title(webview)

    def _on_loading_changed(self, webview, _param):
        if self._is_current(webview):
            self._update_loading(webview)

    def _on_progress_changed(self, webview, _param):
        if self._is_current(webview):
            self.load_trace.set_progress(webview.get_estimated_load_progress(), webview.is_loading())

    def _on_load_changed(self, webview, event):
        tab = self._view_tabs.get(webview)
        if event in (WebKit2.LoadEvent.STARTED, WebKit2.LoadEvent.REDIRECTED):
            # Il JS si decide prima che la pagina arrivi (solo frame principale)
            webview.get_settings().set_enable_javascript(self._js_allowed(webview.get_uri()))
        if event == WebKit2.LoadEvent.STARTED and tab is not None:
            tab.network_log.clear()
            self.network_panel.log_cleared(tab)
        if event == WebKit2.LoadEvent.FINISHED and tab is not None and not tab.private:
            uri = webview.get_uri()
            if navigation.http_host(uri) and self.config["history_enabled"]:
                self.storage.record_visit(uri, webview.get_title())
        if self._is_current(webview):
            self._update_nav_buttons(webview)
            if event in (WebKit2.LoadEvent.COMMITTED, WebKit2.LoadEvent.FINISHED):
                self._update_site_indicators(webview)

    def _on_resource_load_started(self, webview, resource, request):
        tab = self._view_tabs.get(webview)
        if tab is None:
            return
        entry = devtools.NetworkEntry(request)
        tab.network_log.append(entry)
        self.network_panel.entry_added(tab, entry)

        def on_failed(_resource, error):
            entry.fail(error)

        def on_finished(res):
            entry.finish(res)
            self.network_panel.entry_updated(tab, entry)

        resource.connect("failed", on_failed)
        resource.connect("finished", on_finished)

    def _on_web_process_terminated(self, webview, reason):
        if reason == WebKit2.WebProcessTerminationReason.EXCEEDED_MEMORY_LIMIT:
            message = _("Pagina chiusa: aveva superato il limite di memoria. F5 per ricaricare.")
        elif reason == WebKit2.WebProcessTerminationReason.CRASHED:
            message = _("Il processo della pagina si è bloccato. F5 per ricaricare.")
        else:
            return
        if self._is_current(webview):
            self.show_status(message, seconds=8)

    def _on_create(self, webview, _navigation_action):
        # Link con target=_blank e window.open(): nuova tab invece di nuova finestra
        return self.new_tab(related_view=webview).webview

    def _on_close_request(self, webview):
        tab = self._view_tabs.get(webview)
        if tab is not None:
            self.close_tab(tab)

    # --- Barra indirizzi ------------------------------------------------

    def _on_url_activate(self, entry):
        self.load_in_current(entry.get_text())

    def load_in_current(self, text):
        url = navigation.resolve_input(text)
        if url:
            webview = self.current_webview()
            webview.load_uri(url)
            webview.grab_focus()

    def _on_url_typed(self, entry):
        """Riempie i suggerimenti solo mentre scrivi tu (non quando cambia pagina)."""
        if not entry.has_focus():
            return
        text = entry.get_text().strip()
        self.completion_store.clear()
        if len(text) >= 2:
            for url, title in self.storage.search_history(text):
                self.completion_store.append([url, title or url])

    def _on_completion_selected(self, _completion, model, tree_iter):
        url = model[tree_iter][0]
        self.url_entry.set_text(url)
        self.load_in_current(url)
        return True

    def _on_url_icon_press(self, _entry, position, _event):
        if position == Gtk.EntryIconPosition.PRIMARY:
            self.shields_button.set_active(True)
        else:
            self.toggle_bookmark()

    def _on_reload_clicked(self, _button):
        # Durante il caricamento il pulsante fa da "stop"
        webview = self.current_webview()
        if webview.is_loading():
            webview.stop_loading()
        else:
            webview.reload()

    def focus_url_entry(self):
        self.url_entry.grab_focus()
        self.url_entry.select_region(0, -1)

    def _focus_page(self):
        webview = self.current_webview()
        if webview is not None:
            webview.grab_focus()

    # --- Azioni ---------------------------------------------------------

    def toggle_bookmark(self):
        webview = self.current_webview()
        uri = webview.get_uri()
        if navigation.http_host(uri) is None:
            self.show_status(_("Si possono salvare solo pagine web"))
            return
        saved = self.storage.toggle_bookmark(uri, webview.get_title())
        self.show_status(_("Aggiunto ai preferiti") if saved else _("Tolto dai preferiti"))
        self._update_site_indicators(webview)

    def zoom(self, direction):
        """direction: +1, -1, oppure 0 per tornare al 100%."""
        webview = self.current_webview()
        level = webview.get_zoom_level()
        if direction == 0:
            level = 1.0
        elif direction > 0:
            level = next((z for z in ZOOM_LEVELS if z > level + 0.001), ZOOM_LEVELS[-1])
        else:
            level = next((z for z in reversed(ZOOM_LEVELS) if z < level - 0.001), ZOOM_LEVELS[0])
        webview.set_zoom_level(level)
        self.show_status(_("Zoom {level:.0%}").format(level=level), seconds=2)

    def view_source(self):
        webview = self.current_webview()
        if navigation.http_host(webview.get_uri()) is None:
            self.show_status(_("Il sorgente è disponibile per le pagine web"))
            return
        tab = self.current_tab()
        devtools.open_source(webview, lambda url: self.new_tab(url, private=tab.private))

    def open_find(self):
        self.find_bar.open()

    def open_palette(self):
        if self.find_bar.is_open():
            self.find_bar.close()
        self.palette.open()

    def show_inspector(self):
        self.current_webview().get_inspector().show()

    def copy_url(self, markdown=False):
        webview = self.current_webview()
        uri = webview.get_uri() or ""
        text = f"[{webview.get_title() or uri}]({uri})" if markdown else uri
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.show_status(_("Link Markdown copiato") if markdown else _("Indirizzo copiato"))

    def clear_history(self):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL, text=_("Cancellare tutta la cronologia?"),
        )
        dialog.format_secondary_text(_("Preferiti e cookie restano. Non si può annullare."))
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self.storage.clear_history()
            self.show_status(_("Cronologia cancellata"))

    def open_file(self, path):
        """Apre un file di configurazione nell'editor di sistema."""
        Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(path, None), None)

    def ask_ai(self, action):
        self.side_panel.open("ia")
        action()

    # --- Command palette ------------------------------------------------

    def _palette_items(self, text):
        items = [PaletteItem(title, accel, icon, action) for title, accel, icon, action in actions.commands(self)]
        for tab in self._ordered_tabs():
            items.append(PaletteItem(tab.title, _("tab aperta"), "view-paged-symbolic",
                                     lambda t=tab: self._select_tab(t)))
        if not text:
            return items
        for url, title in self.storage.bookmarks():
            items.append(PaletteItem(title, url, "starred-symbolic", lambda u=url: self.load_in_current(u)))
        for url, title in self.storage.search_history(text, limit=6):
            items.append(PaletteItem(title or url, url, "document-open-recent-symbolic",
                                     lambda u=url: self.load_in_current(u)))
        # Ultima risorsa: aprire o cercare il testo; in cima se sembra un indirizzo
        target = navigation.resolve_input(text)
        fallback = PaletteItem(_("Apri o cerca «{text}»").format(text=text), _("Invio"), "system-search-symbolic",
                               lambda: self.load_in_current(text))
        fallback.score = 2000 if target and not navigation.is_search_url(target) else 1
        items.append(fallback)
        return items

    # --- Pannelli e strumenti -------------------------------------------

    def toggle_side_panel(self, name):
        if name == "ia" and not self.config["ai_enabled"]:
            return
        self.side_panel.toggle(name)

    def show_terminal(self):
        """Il terminale sale dal basso; il divisore resta trascinabile."""
        if not self._terminal_open:
            self._terminal_open = True
            total = self.main_paned.get_allocated_height()
            self.terminal_panel.show()
            self.main_paned.set_position(total)
            target = int(total * (1 - TERMINAL_SHARE))
            self._paned_animation.run(
                total, target, TERMINAL_SLIDE_MS, lambda v: self.main_paned.set_position(int(v))
            )
            self._sync_rail()
        self.terminal_panel.focus()

    def hide_terminal(self):
        if not self._terminal_open:
            return
        self._terminal_open = False
        self._paned_animation.run(
            self.main_paned.get_position(),
            self.main_paned.get_allocated_height(),
            TERMINAL_SLIDE_MS,
            lambda v: self.main_paned.set_position(int(v)),
            on_done=self.terminal_panel.hide,
        )
        self._focus_page()
        self._sync_rail()

    def toggle_terminal(self):
        if self._terminal_open:
            self.hide_terminal()
        else:
            self.show_terminal()

    def new_terminal(self):
        self.show_terminal()
        self.terminal_panel.new_terminal()

    def terminal_has_focus(self):
        focus = self.get_focus()
        return focus is not None and focus.is_ancestor(self.terminal_panel)

    def show_local_servers(self):
        self.servers_button.set_active(True)

    def show_site_data(self):
        webview = self.current_webview()
        if navigation.http_host(webview.get_uri()) is None:
            self.show_status(_("Apri un sito web per vederne cookie e dati"))
            return
        devtools.SiteDataDialog(self, webview)

    def take_screenshot(self):
        def done(path, error):
            if path:
                self.show_status(_("Screenshot salvato in {path}").format(path=path))
            else:
                self.show_status(_("Screenshot non riuscito: {error}").format(error=error))

        devtools.take_screenshot(self.current_webview(), done)

    def set_responsive(self, size):
        tab = self.current_tab()
        tab.set_responsive(size)
        if size is not None:
            self._last_responsive = size
            self.show_status(_("Vista responsive {width}×{height}").format(width=size[0], height=size[1]))
        else:
            self.show_status(_("Vista responsive disattivata"))
        tab.webview.grab_focus()
        self._sync_rail()

    def toggle_responsive(self):
        tab = self.current_tab()
        self.set_responsive(None if tab.responsive_size else self._last_responsive)

    def reload_blocklist(self):
        self.content_filter.reload(
            on_done=lambda: self.show_status(
                _("Blocklist ricaricata: {count} domini").format(count=len(self.content_filter.blocked_domains))
            )
        )

    def show_status(self, text, seconds=4):
        self.status_label.set_text(text)
        self.status_revealer.set_reveal_child(True)
        if self._status_timer:
            GLib.source_remove(self._status_timer)
        self._status_timer = GLib.timeout_add_seconds(seconds, self._hide_status)

    def _hide_status(self):
        self.status_revealer.set_reveal_child(False)
        self._status_timer = 0
        return GLib.SOURCE_REMOVE
