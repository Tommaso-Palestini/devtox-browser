"""Tema "Neon Deck": CSS GTK, palette del terminale e animazioni leggere.

Le animazioni usano il frame clock di GTK solo mentre sono in corso:
a riposo non consumano CPU. Se nel sistema le animazioni sono spente,
ogni transizione arriva subito allo stato finale.
"""

import os

import cairo
from gi.repository import Gdk, GLib, Gtk, Pango, Vte

from . import utils

# Stessi valori di resources/theme.css e delle pagine sr://
VOID = "#0e0b19"
DECK = "#171228"
SEAM = "#2c2348"
INK = "#e9e4ff"
HAZE = "#8d84b8"
MAGENTA = "#ff2e88"
CYAN = "#2de2e6"
AMBER = "#ffb627"
TERMINAL_BG = "#0b0915"

TERMINAL_FONT = "Fira Mono 10"
# Ordine ANSI: nero, rosso, verde, giallo, blu, magenta, ciano, bianco (+ versioni chiare)
TERMINAL_PALETTE = [
    "#1d1733", "#ff2e88", "#3ddc97", "#ffb627", "#6c8cff", "#c86bff", "#2de2e6", "#d8d2f5",
    "#4a3f73", "#ff6aa9", "#7af0bd", "#ffd166", "#9db1ff", "#dd9bff", "#8ff3f5", "#ffffff",
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
    terminal.set_colors(rgba(INK), rgba(TERMINAL_BG), [rgba(c) for c in TERMINAL_PALETTE])
    terminal.set_color_cursor(rgba(MAGENTA))
    terminal.set_color_cursor_foreground(rgba(TERMINAL_BG))
    terminal.set_color_highlight(rgba(MAGENTA, 0.35))
    terminal.set_color_highlight_foreground(rgba(INK))
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
    """Linea di caricamento magenta→ciano: insegue il progresso, poi sfuma."""

    HEIGHT = 3

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
        gradient = cairo.LinearGradient(0, 0, max(width, 1), 0)
        gradient.add_color_stop_rgba(0, *_cairo_rgb(MAGENTA), self._opacity)
        gradient.add_color_stop_rgba(1, *_cairo_rgb(CYAN), self._opacity)
        cr.set_source(gradient)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        # Punta più luminosa: dà l'idea di una scia in movimento
        if self._loading:
            cr.set_source_rgba(1, 1, 1, 0.8 * self._opacity)
            cr.rectangle(max(0, width - 14), 0, 14, height)
            cr.fill()
        return False
