"""Tema di Devtox: CSS GTK, palette del terminale e animazioni leggere.

Le animazioni usano il frame clock di GTK solo mentre sono in corso:
a riposo non consumano CPU. Se nel sistema le animazioni sono spente,
ogni transizione arriva subito allo stato finale.
"""

import os

from gi.repository import Gdk, GLib, Gtk, Pango, Vte

from . import utils

# Stessi valori di resources/theme.css e delle pagine devtox://
PAGE = "#0e0e10"
CHROME = "#161618"
RULE = "#26262a"
TEXT = "#ececee"
MUTED = "#94969d"
ACCENT = "#73c991"      # il verde del prompt: l'unico accento
WARNING = "#d9a441"
NEGATIVE = "#e5566f"
TERMINAL_BG = PAGE

TERMINAL_FONT = "Fira Mono 10"
# Ordine ANSI: nero, rosso, verde, giallo, blu, magenta, ciano, bianco (+ versioni chiare).
# Toni smorzati: in una sessione lunga il testo conta più dei colori.
TERMINAL_PALETTE = [
    "#26262a", "#e5566f", "#73c991", "#d9a441", "#6aa1e0", "#c78bd4", "#5fbfc4", "#cfd0d4",
    "#5c5e64", "#f07c90", "#98dcae", "#e8c171", "#93bdee", "#dcaee5", "#8fd6da", "#ffffff",
]


def rgba(hex_color, alpha=1.0):
    color = Gdk.RGBA()
    color.parse(hex_color)
    color.alpha = alpha
    return color


def _cairo_rgb(hex_color):
    color = rgba(hex_color)
    return color.red, color.green, color.blue


def install():
    """Tema scuro di base + il nostro CSS sopra, per tutta l'applicazione."""
    settings = Gtk.Settings.get_default()
    settings.set_property("gtk-application-prefer-dark-theme", True)
    provider = Gtk.CssProvider()
    provider.load_from_path(os.path.join(utils.RESOURCES_DIR, "theme.css"))
    # Icone del rail disegnate per Devtox: uguali con qualunque tema di icone
    Gtk.IconTheme.get_default().append_search_path(os.path.join(utils.RESOURCES_DIR, "icons"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def animations_enabled():
    return Gtk.Settings.get_default().get_property("gtk-enable-animations")


# VTE aggiunge il suo CSS (padding 1px) direttamente al widget, con la stessa
# priorità del nostro tema: serve un provider sul terminale, un gradino sopra
_TERMINAL_CSS = b"vte-terminal { padding: 6px 10px; }"


def style_terminal(terminal):
    provider = Gtk.CssProvider()
    provider.load_from_data(_TERMINAL_CSS)
    terminal.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    terminal.set_colors(rgba(TEXT), rgba(TERMINAL_BG), [rgba(c) for c in TERMINAL_PALETTE])
    terminal.set_color_cursor(rgba(ACCENT))
    terminal.set_color_cursor_foreground(rgba(TERMINAL_BG))
    terminal.set_color_highlight(rgba(ACCENT, 0.28))
    terminal.set_color_highlight_foreground(rgba(TEXT))
    terminal.set_font(Pango.FontDescription(TERMINAL_FONT))
    terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


class Animation:
    """Interpola un valore sui frame di un widget; una nuova corsa annulla la precedente."""

    def __init__(self, widget):
        self.widget = widget
        self._tick_id = 0

    def run(self, start, end, duration_ms, apply, on_done=None):
        self.cancel()
        if not animations_enabled() or start == end:
            apply(end)
            if on_done is not None:
                on_done()
            return
        begin = None

        def tick(_widget, clock):
            nonlocal begin
            now = clock.get_frame_time()
            if begin is None:
                begin = now
            progress = min(1.0, (now - begin) / (duration_ms * 1000))
            apply(start + (end - start) * ease_out_cubic(progress))
            if progress < 1.0:
                return GLib.SOURCE_CONTINUE
            self._tick_id = 0
            if on_done is not None:
                on_done()
            return GLib.SOURCE_REMOVE

        self._tick_id = self.widget.add_tick_callback(tick)

    def cancel(self):
        if self._tick_id:
            self.widget.remove_tick_callback(self._tick_id)
            self._tick_id = 0


class LoadTrace(Gtk.DrawingArea):
    """Linea di caricamento nel colore d'accento: insegue il progresso, poi sfuma."""

    HEIGHT = 2

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, self.HEIGHT)
        self._target = 0.0
        self._shown = 0.0
        self._opacity = 0.0
        self._loading = False
        self._tick_id = 0
        self.connect("draw", self._on_draw)

    def set_progress(self, fraction, loading):
        if loading and not self._loading:
            self._shown = 0.0  # nuovo caricamento: si riparte da sinistra
        self._loading = loading
        self._target = 1.0 if not loading else max(0.05, fraction)
        if not animations_enabled():
            self._shown = self._target
            self._opacity = 1.0 if loading else 0.0
            self.queue_draw()
            return
        if not self._tick_id:
            self._tick_id = self.add_tick_callback(self._tick)

    def _tick(self, _widget, _clock):
        # Inseguimento morbido: ogni frame copre il 18% della distanza rimasta
        self._shown += (self._target - self._shown) * 0.18
        if self._loading:
            self._opacity = min(1.0, self._opacity + 0.15)
        elif self._shown > 0.995:
            self._opacity = max(0.0, self._opacity - 0.06)
        self.queue_draw()
        if not self._loading and self._opacity <= 0.0:
            self._shown = 0.0
            self._tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_draw(self, widget, cr):
        width = widget.get_allocated_width() * self._shown
        height = widget.get_allocated_height()
        if width <= 0 or self._opacity <= 0:
            return False
        cr.set_source_rgba(*_cairo_rgb(ACCENT), self._opacity)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        return False
