"""Pannello terminale: shell reale dell'utente su PTY (VTE), più terminali in tab.

Il terminale è un widget GTK nativo: nessuna pagina web può raggiungerlo,
perché non esiste nessun ponte JavaScript verso questo modulo.
"""

import os
import pwd

from gi.repository import Gdk, GLib, Gtk, Vte

from . import theme, utils
from .i18n import _

SCROLLBACK_LINES = 5000
# Indirizzi web nell'output (il "Local: http://localhost:5173/" di vite, ecc.): Ctrl+clic li apre.
# Stessa sintassi per PCRE2 (VTE) e per re (test): non finisce su punteggiatura o parentesi
URL_PATTERN = r"""(?<![\w/])https?://[^\s<>"'`]*[^\s<>"'`.,;:!?)\]]"""
_PCRE2_MULTILINE = 0x00000400


def user_shell():
    shell = os.environ.get("SHELL")
    if shell and os.access(shell, os.X_OK):
        return shell
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
    except KeyError:
        return "/bin/sh"


def shell_environment():
    """Ambiente della shell: quello del browser più DEVTOX_SOCKET e il comando dx nel PATH."""
    env = dict(os.environ)
    env["DEVTOX_SOCKET"] = utils.socket_path()
    env["TERM_PROGRAM"] = utils.APP_ID
    env["PATH"] = utils.BIN_DIR + os.pathsep + env.get("PATH", "")
    return [f"{key}={value}" for key, value in env.items()]


class TerminalPanel(Gtk.Box):
    def __init__(self, on_hide, on_open_url=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_open_url = on_open_url  # on_open_url(url): nuova tab nel browser
        self._url_regex = Vte.Regex.new_for_match(URL_PATTERN, -1, _PCRE2_MULTILINE)
        # on_hide: la finestra nasconde il pannello (con animazione); serve anche
        # quando si chiude l'ultimo terminale
        self._on_hide = on_hide
        self.get_style_context().add_class("terminal-panel")
        self._shell_pids = {}      # Vte.Terminal -> PID della shell

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_border_width(2)
        title = Gtk.Label(label=_("Terminale"), xalign=0)
        title.get_style_context().add_class("terminal-title")
        header.pack_start(title, True, True, 6)

        new_button = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.MENU)
        new_button.set_relief(Gtk.ReliefStyle.NONE)
        new_button.set_tooltip_text(_("Nuovo terminale (Ctrl+Shift+`)"))
        new_button.connect("clicked", lambda _b: self.new_terminal())
        header.pack_start(new_button, False, False, 0)

        hide_button = Gtk.Button.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.MENU)
        hide_button.set_relief(Gtk.ReliefStyle.NONE)
        hide_button.set_tooltip_text(_("Nascondi pannello (Ctrl+`)"))
        hide_button.connect("clicked", lambda _b: self._on_hide())
        header.pack_start(hide_button, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.set_show_border(False)
        self.notebook.get_style_context().add_class("terminal-tabs")

        self.pack_start(header, False, False, 0)
        self.pack_start(self.notebook, True, True, 0)

    # --- Gestione terminali ---------------------------------------------

    def new_terminal(self):
        terminal = Vte.Terminal()
        terminal.set_scrollback_lines(SCROLLBACK_LINES)
        terminal.set_mouse_autohide(True)
        theme.style_terminal(terminal)
        terminal.connect("child-exited", self._on_child_exited)
        terminal.connect("key-press-event", self._on_terminal_key)
        terminal.set_allow_hyperlink(True)  # link OSC 8 (ls --hyperlink, compilatori, ...)
        tag = terminal.match_add_regex(self._url_regex, 0)
        terminal.match_set_cursor_name(tag, "pointer")
        terminal.connect("button-press-event", self._on_terminal_click)

        label = Gtk.Label(label=os.path.basename(user_shell()))
        terminal.connect("window-title-changed", self._on_title_changed, label)

        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_button.set_relief(Gtk.ReliefStyle.NONE)
        close_button.connect("clicked", lambda _b: self._close(terminal))
        tab_label = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab_label.pack_start(label, True, True, 0)
        tab_label.pack_start(close_button, False, False, 0)
        tab_label.show_all()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(terminal)
        scrolled.show_all()

        index = self.notebook.append_page(scrolled, tab_label)
        self.notebook.set_current_page(index)

        # Shell interattiva vera, con il suo PTY, nella home dell'utente
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            GLib.get_home_dir(),
            [user_shell()],
            shell_environment(),
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self._on_spawned,
        )
        terminal.grab_focus()
        return terminal

    def current_terminal(self):
        page = self.notebook.get_current_page()
        if page < 0:
            return None
        return self.notebook.get_nth_page(page).get_child()

    def ensure_terminal(self):
        return self.current_terminal() or self.new_terminal()

    def select_relative(self, offset):
        count = self.notebook.get_n_pages()
        if count:
            self.notebook.set_current_page((self.notebook.get_current_page() + offset) % count)
            self.current_terminal().grab_focus()

    def focus(self):
        self.ensure_terminal().grab_focus()

    def selected_text(self):
        terminal = self.current_terminal()
        if terminal is None or not terminal.get_has_selection():
            return ""
        return terminal.get_text_selected(Vte.Format.TEXT) or ""

    def paste_command(self, command, run):
        """Incolla un comando (bracketed paste: non parte da solo). run=True invia Invio."""
        terminal = self.ensure_terminal()
        terminal.paste_text(command)
        if run:
            terminal.feed_child(b"\r")
        terminal.grab_focus()

    # --- Segnali --------------------------------------------------------

    def shell_pids(self):
        return set(self._shell_pids.values())

    def _on_spawned(self, terminal, pid, error, *_user_data):
        if error is not None:
            terminal.feed((_("Impossibile avviare la shell: {error}").format(error=error.message) + "\r\n").encode())
        elif pid > 0:
            self._shell_pids[terminal] = pid

    def _on_child_exited(self, terminal, _status):
        self._close(terminal)

    def _close(self, terminal):
        self._shell_pids.pop(terminal, None)
        page = self.notebook.page_num(terminal.get_parent())
        if page >= 0:
            self.notebook.remove_page(page)  # chiude il PTY: la shell riceve SIGHUP
        if self.notebook.get_n_pages() == 0:
            self._on_hide()

    def _on_title_changed(self, terminal, label):
        title = terminal.get_window_title()
        if title:
            label.set_text(title[:24])

    def _on_terminal_click(self, terminal, event):
        """Ctrl+clic su un indirizzo: si apre in una nuova tab (il clic semplice seleziona)."""
        if event.button != 1 or not event.state & Gdk.ModifierType.CONTROL_MASK or self._on_open_url is None:
            return False
        url = terminal.hyperlink_check_event(event)
        if not url:
            url, _tag = terminal.match_check_event(event)
        if url and url.startswith(("http://", "https://")):
            self._on_open_url(url)
            return True
        return False

    def _on_terminal_key(self, terminal, event):
        # Ctrl+Shift+C / Ctrl+Shift+V come nei terminali di GNOME
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        if mods == Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK:
            key = Gdk.keyval_to_lower(event.keyval)
            if key == Gdk.KEY_c:
                terminal.copy_clipboard_format(Vte.Format.TEXT)
                return True
            if key == Gdk.KEY_v:
                terminal.paste_clipboard()
                return True
        return False
