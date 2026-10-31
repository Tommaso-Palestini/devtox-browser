"""Gestore password nella finestra: chiave nella barra, proposta di salvataggio, devtox://passwords.

Il canale con le pagine è un gestore di messaggi registrato solo nel mondo isolato
"devtox-passwords": gli script della pagina non lo vedono. Prima di compilare si
ricontrolla l'origine della tab qui e dentro la pagina; si compila solo dopo un clic.
"""

import html
import json
import os
import secrets
import threading
import urllib.parse

from gi.repository import GLib, Gtk, Pango, WebKit2

from . import passwords, utils
from .i18n import _
from .log import logger

WORLD = "devtox-passwords"
HANDLER = "devtoxPasswords"
URL = "devtox://passwords"
TOKEN = secrets.token_urlsafe(18)


def user_script():
    return WebKit2.UserScript.new_for_world(
        utils.read_resource("passwords.js"), WebKit2.UserContentInjectedFrames.TOP_FRAME,
        WebKit2.UserScriptInjectionTime.END, WORLD, None, None)


def _in_thread(work, done):
    """Il portachiavi parla via D-Bus e può chiedere lo sblocco: mai nel thread di GTK."""
    def worker():
        try:
            result, error = work(), None
        except Exception as e:  # noqa: BLE001  errori di libsecret: si mostrano, non si propagano
            logger.warning("portachiavi: %s", e)
            result, error = None, str(e)
        GLib.idle_add(lambda: done(result, error) and False)
    threading.Thread(target=worker, daemon=True).start()


def _host(origin):
    return urllib.parse.urlsplit(origin).hostname or origin


class PasswordController:
    def __init__(self, window, content_manager, vault):
        self.window = window
        self.vault = vault
        self._form_origins = set()  # origini in cui è comparso un modulo di accesso

        content_manager.register_script_message_handler_in_world(HANDLER, WORLD)
        content_manager.connect(f"script-message-received::{HANDLER}", self._on_message)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.list_box.set_border_width(8)
        self.popover = Gtk.Popover()
        self.popover.add(self.list_box)
        self.button = Gtk.MenuButton(popover=self.popover)
        self.button.set_image(Gtk.Image.new_from_icon_name("dialog-password-symbolic", Gtk.IconSize.BUTTON))
        self.button.get_style_context().add_class("passwords")
        self.button.set_no_show_all(True)

    # --- Messaggi dalla pagina -------------------------------------------

    def _current_origin(self):
        webview = self.window.current_webview()
        return passwords.origin_of(webview.get_uri()) if webview is not None else None

    def _on_message(self, _manager, result):
        try:
            message = json.loads(result.get_js_value().to_string())
        except (ValueError, AttributeError):
            return
        origin = message.get("origin")
        # Un messaggio vale solo per la tab attiva e solo se lì una password si può usare
        if not isinstance(origin, str) or origin != self._current_origin():
            return
        if message.get("type") == "form":
            self._form_origins.add(origin)
            self.refresh()
        elif message.get("type") == "submit":
            self._offer_save(origin, str(message.get("username", ""))[:256], str(message.get("password", ""))[:1024])

    # --- Chiave nella barra e compilazione ------------------------------

    def page_changed(self):
        """Tab cambiata o pagina nuova: la chiave si rimostra solo dove c'è un modulo."""
        self.button.hide()
        self.refresh()

    def refresh(self):
        origin = self._current_origin()
        if origin is None or origin not in self._form_origins:
            self.button.hide()
            return

        def done(users, error):
            if error or not users or origin != self._current_origin():
                self.button.hide()
                return
            self._fill_list(origin, users)
            self.button.set_tooltip_text(_("Password salvate per {host}").format(host=_host(origin)))
            self.button.show()
        _in_thread(lambda: self.vault.usernames(origin), done)

    def _fill_list(self, origin, users):
        for child in self.list_box.get_children():
            self.list_box.remove(child)
        title = Gtk.Label(label=_("Accedi a {host} come").format(host=_host(origin)), xalign=0)
        title.get_style_context().add_class("dim-label")
        self.list_box.pack_start(title, False, False, 4)
        for user in users:
            row = Gtk.Button(label=user or _("(senza nome utente)"))
            row.set_relief(Gtk.ReliefStyle.NONE)
            row.get_child().set_xalign(0)
            row.get_child().set_ellipsize(Pango.EllipsizeMode.END)
            row.connect("clicked", lambda _b, u=user: self.fill(origin, u))
            self.list_box.pack_start(row, False, False, 0)
        manage = Gtk.ModelButton(text=_("Gestisci password…"))
        manage.connect("clicked", lambda _b: self.window.new_tab(URL))
        self.list_box.pack_start(Gtk.Separator(), False, False, 4)
        self.list_box.pack_start(manage, False, False, 0)
        self.list_box.show_all()

    def open(self):
        """Ctrl+K "Compila password": apre la scelta, se c'è qualcosa da compilare."""
        if self.button.get_visible():
            self.button.set_active(True)
        else:
            self.window.show_status(_("Nessuna password salvata per questa pagina"))

    def fill(self, origin, username):
        self.popover.popdown()

        def done(password, error):
            webview = self.window.current_webview()
            # L'origine si ricontrolla adesso: nel frattempo la tab potrebbe aver cambiato pagina
            if error or password is None or webview is None or self._current_origin() != origin:
                return
            script = f"window.__devtoxFill({json.dumps(origin)}, {json.dumps(username)}, {json.dumps(password)})"
            webview.run_javascript_in_world(script, WORLD, None, None)
        _in_thread(lambda: self.vault.password(origin, username), done)

    # --- Salvataggio ------------------------------------------------------

    def _offer_save(self, origin, username, password):
        tab = self.window.current_tab()
        if not password or tab is None or tab.private:
            return  # nelle tab private niente si salva

        def done(current, error):
            if error or current == password:
                return
            question = (_("Aggiornare la password per {host}?") if current is not None
                        else _("Salvare la password per {host}?")).format(host=_host(origin))
            self.window.show_status(question, seconds=15,
                                    action=(_("Salva"), lambda: self._save(origin, username, password)))
        _in_thread(lambda: self.vault.password(origin, username), done)

    def _save(self, origin, username, password):
        def done(_result, error):
            if error:
                self.window.show_status(_("Portachiavi non disponibile: {error}").format(error=error), seconds=8)
                return
            self._form_origins.add(origin)
            self.window.show_status(_("Password salvata nel portachiavi del sistema"))
            self.refresh()
        _in_thread(lambda: self.vault.save(origin, username, password), done)

    # --- Import da CSV ----------------------------------------------------

    def import_csv(self):
        dialog = Gtk.FileChooserNative.new(_("Importa password da un file CSV"), self.window,
                                           Gtk.FileChooserAction.OPEN, _("Importa"), _("Annulla"))
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV")
        csv_filter.add_pattern("*.csv")
        dialog.add_filter(csv_filter)
        if dialog.run() != Gtk.ResponseType.ACCEPT:
            return
        path = dialog.get_filename()
        try:
            rows, skipped = passwords.read_csv(path)
        except (OSError, ValueError, UnicodeDecodeError):
            self.window.show_status(_("Questo file non sembra un export di password"), seconds=8)
            return

        def work():
            return sum(1 for origin, user, pw in rows if self.vault.save(origin, user, pw) != "same")

        def done(saved, error):
            if error:
                self.window.show_status(_("Portachiavi non disponibile: {error}").format(error=error), seconds=8)
                return
            self.window.show_status(_("{n} password importate, {skipped} scartate (http in chiaro o app)").format(
                n=saved, skipped=skipped), seconds=8)
            self._offer_delete(path)
            self.window.reload_internal(URL)
        _in_thread(work, done)

    def _offer_delete(self, path):
        """Il CSV contiene tutte le password in chiaro: si propone subito di eliminarlo."""
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.YES_NO,
                                   text=_("Eliminare il file CSV?"))
        dialog.format_secondary_text(
            _("{path} contiene le tue password in chiaro. Ora sono nel portachiavi: il file non serve più.").format(
                path=path))
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.YES:
            try:
                os.remove(path)
            except OSError as e:
                self.window.show_status(_("Non sono riuscito a eliminarlo: {error}").format(error=e), seconds=8)

    # --- devtox://passwords -----------------------------------------------

    def render_page(self, params):
        if secrets.compare_digest(params.get("token", ""), TOKEN):
            if params.get("import") == "1":
                GLib.idle_add(lambda: self.import_csv() and False)
            elif params.get("delete") == "1" and params.get("origin"):
                self.vault.delete(params["origin"], params.get("username", ""))
            return f'<!doctype html><meta charset="utf-8"><script>location.replace("{URL}");</script>'
        return render_list(self.vault.entries())


def render_list(entries):
    e = html.escape
    rows = "".join(
        f'<tr><th>{e(_host(origin))}<br><small class="hint">{e(origin)}</small></th><td>{e(user) or "—"}</td>'
        f'<td class="act"><a href="{URL}?token={TOKEN}&amp;delete=1&amp;origin={e(urllib.parse.quote(origin))}'
        f'&amp;username={e(urllib.parse.quote(user))}" '
        f'onclick="return confirm({e(json.dumps(_("Eliminare questa password?")))})">{e(_("Elimina"))}</a></td></tr>'
        for origin, user in entries
    )
    table = (f"<table>{rows}</table>" if entries
             else f'<p class="hint">{e(_("Nessuna password salvata. Accedi a un sito e Devtox ti chiederà se salvarla."))}</p>')
    lead = _("Stanno nel portachiavi del sistema, cifrate e sbloccate con il tuo login. "
             "Devtox le compila solo sul sito esatto in cui le hai salvate, e solo quando lo chiedi tu.")
    how = _("Per portarle da un altro browser, esportale in CSV (Firefox: about:logins → Esporta; "
            "Chrome, Opera, Brave, Edge: Gestore password → Esporta; Bitwarden: Esporta in .csv), poi importale qui.")
    body = (
        f"<h1>{e(_('Password'))}</h1><p class=\"lead\">{e(lead)}</p>"
        f'<p class="actions compact"><a class="button" href="{URL}?token={TOKEN}&amp;import=1">'
        f"{e(_('Importa da CSV…'))}</a></p><p class=\"hint\">{e(how)}</p><h2>{e(_('Salvate'))}</h2>{table}"
    )
    return utils.render_template("info.html", title=e(_("Password")), body=body)


def unavailable_page():
    e = html.escape
    text = _("Il portachiavi del sistema (Secret Service: GNOME Keyring o KWallet) non risponde, "
             "quindi Devtox non salva password. Installa gnome-keyring o attiva KWallet, poi riavvia.")
    return utils.render_template("info.html", title=e(_("Password")),
                                 body=f"<h1>{e(_('Password'))}</h1><p>{e(text)}</p>")
