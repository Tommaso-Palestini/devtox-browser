"""Azioni del browser: l'elenco per la command palette e le scorciatoie da tastiera."""

from gi.repository import Gdk, Gtk

from . import navigation, privacy
from .i18n import _

# Tasto fisico a sinistra di "1" (evdev/X11): Ctrl+` come in VS Code su ogni layout
GRAVE_KEYCODE = 49


def commands(win):
    """(titolo, scorciatoia, icona, azione) di tutte le azioni del browser."""
    side = win.toggle_side_panel
    ai = [
        (_("Assistente IA"), "Ctrl+Shift+A", "dx-assistant-symbolic", lambda: side("ia")),
        (_("IA: riassumi la pagina"), "", "dx-assistant-symbolic",
         lambda: win.ask_ai(win.ai_panel.summarize_page)),
        (_("IA: spiega l'errore selezionato"), "", "dx-assistant-symbolic",
         lambda: win.ask_ai(win.ai_panel.explain_selection)),
    ] if win.config["ai_enabled"] else []
    return [
        (_("Nuova tab"), "Ctrl+T", "tab-new-symbolic", win.new_tab_and_focus),
        (_("Nuova tab privata"), "Ctrl+Shift+N", "user-not-tracked-symbolic", win.new_private_tab),
        (_("Riapri tab chiusa"), "Ctrl+Shift+T", "document-open-recent-symbolic", win.reopen_closed_tab),
        (_("Chiudi tab"), "Ctrl+W", "window-close-symbolic", lambda: win.close_tab(win.current_tab())),
        (_("Terminale"), "Ctrl+`", "dx-terminal-symbolic", win.toggle_terminal),
        (_("Nuovo terminale"), "Ctrl+Shift+`", "dx-terminal-symbolic", win.new_terminal),
        (_("Cerca nella pagina"), "Ctrl+F", "edit-find-symbolic", win.open_find),
        (_("Sorgente della pagina"), "Ctrl+U", "text-x-generic-symbolic", win.view_source),
        (_("Aggiungi o togli dai preferiti"), "Ctrl+D", "starred-symbolic", win.toggle_bookmark),
        (_("Scudi e connessione del sito"), "", "security-high-symbolic",
         lambda: win.shields_button.set_active(True)),
        (_("Richieste di rete"), "Ctrl+Shift+E", "dx-network-symbolic", lambda: side("rete")),
        (_("Memoria e processi"), "Shift+Esc", "dx-memory-symbolic", lambda: side("memoria")),
        (_("Download"), "Ctrl+Shift+Y", "dx-downloads-symbolic", lambda: side("download")),
        (_("Server locali"), "Ctrl+Shift+L", "dx-servers-symbolic", win.show_local_servers),
        (_("Vista responsive"), "Ctrl+Shift+M", "dx-responsive-symbolic", win.toggle_responsive),
        (_("Screenshot della pagina"), "Ctrl+Shift+S", "dx-screenshot-symbolic", win.take_screenshot),
        (_("Cookie e dati del sito"), _("Ctrl+Shift+Canc"), "dx-site-data-symbolic", win.show_site_data),
        (_("Zoom avanti"), "Ctrl++", "zoom-in-symbolic", lambda: win.zoom(1)),
        (_("Zoom indietro"), "Ctrl+-", "zoom-out-symbolic", lambda: win.zoom(-1)),
        (_("Zoom 100%"), "Ctrl+0", "zoom-original-symbolic", lambda: win.zoom(0)),
        (_("Copia indirizzo"), "", "edit-copy-symbolic", win.copy_url),
        (_("Copia link in Markdown"), "", "edit-copy-symbolic", lambda: win.copy_url(markdown=True)),
        (_("Strumenti sviluppatore"), "F12", "applications-engineering-symbolic", win.show_inspector),
        (_("Modifica blocklist"), "", "document-edit-symbolic", lambda: win.open_file(privacy.blocklist_path())),
        (_("Ricarica blocklist"), "", "view-refresh-symbolic", win.reload_blocklist),
        (_("Apri configurazione"), "", "emblem-system-symbolic", lambda: win.open_file(win.config.path)),
        (_("Cancella cronologia"), "", "user-trash-symbolic", win.clear_history),
        (_("Informazioni su Devtox"), "", "help-about-symbolic",
         lambda: win.new_tab(navigation.ABOUT_URL)),
        (_("Personalizza Devtox"), "", "preferences-desktop-symbolic",
         lambda: win.new_tab(navigation.SETUP_URL)),
        (_("Guida rapida"), "", "help-browser-symbolic", lambda: win.new_tab(navigation.WELCOME_URL)),
    ] + ai


def handle_key(win, event):
    """Scorciatoie della finestra; True se il tasto è stato gestito."""
    key = Gdk.keyval_to_lower(event.keyval)
    mods = event.state & Gtk.accelerator_get_default_mod_mask()
    ctrl = bool(mods & Gdk.ModifierType.CONTROL_MASK)
    shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)
    alt = bool(mods & Gdk.ModifierType.MOD1_MASK)
    grave = key == Gdk.KEY_grave or event.hardware_keycode == GRAVE_KEYCODE

    # Terminale: valgono ovunque, anche con il focus nella shell
    if ctrl and grave:
        win.new_terminal() if shift else win.toggle_terminal()
        return True
    if win.terminal_has_focus():
        if ctrl and key == Gdk.KEY_Page_Up:
            win.terminal_panel.select_relative(-1)
            return True
        if ctrl and key == Gdk.KEY_Page_Down:
            win.terminal_panel.select_relative(1)
            return True
        return False  # tutto il resto (Ctrl+W, Ctrl+R, Ctrl+L, ...) va alla shell
    if win.palette.is_open() and win.palette.entry.has_focus():
        return False  # la palette gestisce i suoi tasti

    if ctrl and shift:
        actions = {
            Gdk.KEY_p: win.open_palette,
            Gdk.KEY_n: win.new_private_tab,
            Gdk.KEY_t: win.reopen_closed_tab,
            Gdk.KEY_e: lambda: win.toggle_side_panel("rete"),
            Gdk.KEY_a: lambda: win.toggle_side_panel("ia"),
            Gdk.KEY_y: lambda: win.toggle_side_panel("download"),
            Gdk.KEY_l: win.show_local_servers,
            Gdk.KEY_s: win.take_screenshot,
            Gdk.KEY_m: win.toggle_responsive,
            Gdk.KEY_Delete: win.show_site_data,
            Gdk.KEY_ISO_Left_Tab: lambda: win.select_relative_tab(-1),
            Gdk.KEY_Tab: lambda: win.select_relative_tab(-1),
            Gdk.KEY_plus: lambda: win.zoom(1),  # su molte tastiere "+" richiede Shift
        }
        action = actions.get(key)
        if action is not None:
            action()
            return True
        return False

    if ctrl:
        actions = {
            Gdk.KEY_k: win.open_palette,
            Gdk.KEY_t: win.new_tab_and_focus,
            Gdk.KEY_w: lambda: win.close_tab(win.current_tab()),
            Gdk.KEY_l: win.focus_url_entry,
            Gdk.KEY_f: win.open_find,
            Gdk.KEY_d: win.toggle_bookmark,
            Gdk.KEY_u: win.view_source,
            Gdk.KEY_r: lambda: win.current_webview().reload(),
            Gdk.KEY_Tab: lambda: win.select_relative_tab(1),
            Gdk.KEY_plus: lambda: win.zoom(1),
            Gdk.KEY_equal: lambda: win.zoom(1),
            Gdk.KEY_KP_Add: lambda: win.zoom(1),
            Gdk.KEY_minus: lambda: win.zoom(-1),
            Gdk.KEY_KP_Subtract: lambda: win.zoom(-1),
            Gdk.KEY_0: lambda: win.zoom(0),
            Gdk.KEY_KP_0: lambda: win.zoom(0),
        }
        action = actions.get(key)
        if action is not None:
            action()
            return True
        return False

    if shift and key == Gdk.KEY_Escape:
        win.toggle_side_panel("memoria")
    elif key == Gdk.KEY_F5:
        win.current_webview().reload()
    elif alt and key == Gdk.KEY_Left:
        win.current_webview().go_back()
    elif alt and key == Gdk.KEY_Right:
        win.current_webview().go_forward()
    elif key == Gdk.KEY_F12:
        win.show_inspector()
    else:
        return False
    return True
