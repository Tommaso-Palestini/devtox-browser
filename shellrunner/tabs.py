"""Una tab: WebView (o segnaposto se sospesa), etichetta, log di rete, responsive."""

import collections
import time

from gi.repository import Gtk, Pango, WebKit2

from .i18n import _

DEFAULT_TITLE = _("Nuova tab")
NETWORK_LOG_LIMIT = 500


class DeviceFrame(Gtk.Bin):
    """Contenitore che misura esattamente come lo schermo simulato.

    Il WebView chiede una larghezza "naturale" ampia: senza questo
    contenitore GTK 3 lo allargherebbe oltre la misura del dispositivo.
    """

    def __init__(self, width, height):
        super().__init__()
        self.width, self.height = width, height

    def do_get_preferred_width(self):
        return self.width, self.width

    def do_get_preferred_height(self):
        return self.height, self.height

    def do_size_allocate(self, allocation):
        self.set_allocation(allocation)
        child = self.get_child()
        if child is not None:
            child.size_allocate(allocation)


class BrowserTab:
    """restore=(uri, titolo, sessione o None): la tab nasce sospesa e carica solo
    quando la selezioni (ripristino della sessione, riapertura di tab chiuse)."""

    def __init__(self, create_webview, on_close, related_view=None, private=False, restore=None):
        # create_webview(tab, related_view) lo fornisce la finestra: collega i segnali
        self._create_webview = create_webview
        self.private = private
        self.webview = None
        self.last_active = time.monotonic()
        self.network_log = collections.deque(maxlen=NETWORK_LOG_LIMIT)
        self.responsive_size = None

        self._content = None
        self._saved_session = None
        self._saved_uri = None
        self._saved_title = None

        # Pagina del Gtk.Notebook: contiene il WebView o il segnaposto
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.container.show()

        self._placeholder = Gtk.Label(
            label=_("Tab sospesa per risparmiare memoria.\nSi riapre quando la selezioni.")
        )
        self._placeholder.set_justify(Gtk.Justification.CENTER)
        self._placeholder.get_style_context().add_class("suspended-placeholder")

        self.title_label = Gtk.Label(label=DEFAULT_TITLE)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_width_chars(16)
        self.title_label.set_max_width_chars(16)
        self.title_label.set_xalign(0)

        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.set_tooltip_text(_("Chiudi tab (Ctrl+W)"))
        close_button.connect("clicked", lambda _b: on_close(self))

        # Widget usato come "linguetta" nel Gtk.Notebook
        self.label_widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        if private:
            mask = Gtk.Image.new_from_icon_name("user-not-tracked-symbolic", Gtk.IconSize.MENU)
            self.label_widget.pack_start(mask, False, False, 0)
            self.label_widget.get_style_context().add_class("private")
        self.label_widget.pack_start(self.title_label, True, True, 0)
        self.label_widget.pack_start(close_button, False, False, 0)
        self.label_widget.show_all()

        if restore is not None:
            self._saved_uri, self._saved_title, self._saved_session = restore
            self._place(self._placeholder)
            self._update_label()
        else:
            self._attach(create_webview(self, related_view))

    # --- Stato ----------------------------------------------------------

    @property
    def suspended(self):
        return self.webview is None

    @property
    def uri(self):
        return self.webview.get_uri() if self.webview else self._saved_uri

    @property
    def title(self):
        if self.webview is None:
            return self._saved_title or self._saved_uri or DEFAULT_TITLE
        return self.webview.get_title() or self.webview.get_uri() or DEFAULT_TITLE

    def snapshot(self):
        """(uri, titolo, sessione) per riaprire la tab con la sua cronologia."""
        if self.webview is None:
            return self._saved_uri, self._saved_title, self._saved_session
        return self.webview.get_uri(), self.webview.get_title(), self.webview.get_session_state().serialize()

    def can_suspend(self):
        view = self.webview
        return view is not None and not view.is_loading() and not view.is_playing_audio()

    # --- Sospensione ----------------------------------------------------

    def suspend(self):
        """Salva la cronologia della tab e distrugge il WebView per liberare RAM."""
        webview = self.webview
        self._saved_session = webview.get_session_state().serialize()
        self._saved_uri = webview.get_uri()
        self._saved_title = webview.get_title()
        self.webview = None
        self._place(self._placeholder)
        webview.destroy()
        self._update_label()

    def resume(self):
        """Ricrea il WebView e ripristina cronologia e pagina."""
        if self.webview is not None:
            return
        webview = self._create_webview(self, None)
        self._attach(webview)
        item = None
        if self._saved_session is not None:
            webview.restore_session_state(WebKit2.WebViewSessionState.new(self._saved_session))
            item = webview.get_back_forward_list().get_current_item()
        if item is not None:
            webview.go_to_back_forward_list_item(item)
        elif self._saved_uri:
            webview.load_uri(self._saved_uri)
        self._saved_session = None

    def destroy(self):
        if self.webview is not None:
            self.webview.destroy()
            self.webview = None

    # --- Modalità responsive --------------------------------------------

    def set_responsive(self, size):
        """size = (larghezza, altezza) oppure None per tornare normale."""
        self.responsive_size = size
        if self.webview is not None:
            self._place(self.webview)

    def _place(self, widget):
        """Mette il widget nel contenitore, dentro uno scroll se è in responsive."""
        if self._content is not None and self._content.get_parent() is not None:
            self._content.get_parent().remove(self._content)
        for child in self.container.get_children():
            self.container.remove(child)
        self._content = widget

        if self.responsive_size is not None and widget is self.webview:
            width, height = self.responsive_size
            device = DeviceFrame(width, height)
            device.add(widget)
            # Cornice luminosa (Gtk.Frame disegna il bordo dal CSS) e misura sopra
            frame = Gtk.Frame()
            frame.get_style_context().add_class("device-frame")
            frame.add(device)
            size_label = Gtk.Label(label=f"{width} × {height}")
            size_label.get_style_context().add_class("device-size")
            device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            device_box.set_halign(Gtk.Align.CENTER)
            device_box.set_valign(Gtk.Align.START)
            device_box.pack_start(size_label, False, False, 0)
            device_box.pack_start(frame, False, False, 0)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            inner.set_border_width(18)
            inner.pack_start(device_box, True, True, 0)
            viewport = Gtk.Viewport()
            viewport.set_shadow_type(Gtk.ShadowType.NONE)
            viewport.add(inner)
            scrolled = Gtk.ScrolledWindow()
            scrolled.add(viewport)
            self.container.pack_start(scrolled, True, True, 0)
            scrolled.show_all()
        else:
            self.container.pack_start(widget, True, True, 0)
            widget.show()

    # --- Interni --------------------------------------------------------

    def _attach(self, webview):
        self.webview = webview
        webview.connect("notify::title", lambda *_: self._update_label())
        self._place(webview)
        self._update_label()

    def _update_label(self):
        text = self.title if self.webview else "⏸ " + self.title
        self.title_label.set_text(text)
        self.label_widget.set_tooltip_text(text)
