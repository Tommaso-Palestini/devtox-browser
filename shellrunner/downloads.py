"""Download sicuri: mai aperti da soli, mai sovrascritti, conferma per gli eseguibili."""

import os
import time

from gi.repository import Gio, GLib, Gtk, Pango

from .i18n import _

# File che, se aperti per sbaglio, eseguono codice sul PC
DANGEROUS_EXTENSIONS = {
    ".sh", ".bash", ".zsh", ".run", ".bin", ".appimage", ".deb", ".rpm", ".snap",
    ".flatpakref", ".desktop", ".jar", ".py", ".pl", ".exe", ".msi", ".bat", ".cmd",
    ".ps1", ".vbs", ".apk", ".dmg", ".pkg",
}


def download_dir(config):
    configured = os.path.expanduser(config["download_dir"]) if config["download_dir"] else ""
    return (
        configured
        or GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        or os.path.join(GLib.get_home_dir(), "Downloads")
    )


def safe_filename(name):
    """Solo il nome del file: niente percorsi, niente file nascosti."""
    name = os.path.basename(name.replace("\\", "/")).strip().lstrip(".")
    return name or "download"


def unique_path(directory, name):
    """'file.txt' -> 'file (1).txt' se esiste già: nessun file viene sovrascritto."""
    stem, ext = os.path.splitext(name)
    candidate, number = os.path.join(directory, name), 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem} ({number}){ext}")
        number += 1
    return candidate


def is_dangerous(name):
    return os.path.splitext(name)[1].lower() in DANGEROUS_EXTENSIONS


class DownloadRow(Gtk.ListBoxRow):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.name = Gtk.Label(label=os.path.basename(path), xalign=0)
        self.name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.failed = False
        self.state = Gtk.Label(label=_("In corso…"), xalign=0)
        self.state.get_style_context().add_class("dim-label")
        self.progress = Gtk.ProgressBar()
        self.folder_button = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        self.folder_button.set_tooltip_text(_("Mostra nella cartella"))
        self.folder_button.set_valign(Gtk.Align.CENTER)
        self.folder_button.connect("clicked", lambda _b: self.show_in_folder())

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        text.pack_start(self.name, False, False, 0)
        text.pack_start(self.progress, False, False, 0)
        text.pack_start(self.state, False, False, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_border_width(6)
        box.pack_start(text, True, True, 0)
        box.pack_start(self.folder_button, False, False, 0)
        self.add(box)
        self.show_all()

    def show_in_folder(self):
        # Apre la cartella, non il file: niente esecuzioni accidentali
        uri = GLib.filename_to_uri(os.path.dirname(self.path), None)
        Gio.AppInfo.launch_default_for_uri(uri, None)


class DownloadsPanel(Gtk.Box):
    """Pannello laterale con i download della sessione."""

    title = _("Download")

    def __init__(self, browser):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        self.browser = browser
        self._rows = {}  # WebKit2.Download -> DownloadRow

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.empty = Gtk.Label(label=_("Nessun download in questa sessione."))
        self.empty.get_style_context().add_class("dim-label")
        self.list.set_placeholder(self.empty)
        self.empty.show()
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(self.list)
        self.pack_start(scrolled, True, True, 0)

        note = Gtk.Label(
            label=_("I file non vengono mai aperti in automatico e non sovrascrivono quelli esistenti."),
            xalign=0,
        )
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim-label")
        self.pack_start(note, False, False, 0)

    def set_active(self, active):
        pass

    def attach(self, context):
        context.connect("download-started", self._on_download_started)

    def _on_download_started(self, _context, download):
        download.connect("decide-destination", self._on_decide_destination)
        download.connect("notify::estimated-progress", self._on_progress)
        download.connect("failed", self._on_failed)
        download.connect("finished", self._on_finished)

    def _on_decide_destination(self, download, suggested):
        name = safe_filename(suggested)
        if is_dangerous(name) and not self._confirm_dangerous(name, download):
            download.cancel()
            self.browser.show_status(_("Download annullato: {name}").format(name=name))
            return True
        directory = download_dir(self.browser.config)
        os.makedirs(directory, exist_ok=True)
        path = unique_path(directory, name)
        download.set_allow_overwrite(False)
        download.set_destination(GLib.filename_to_uri(path, None))

        row = DownloadRow(path)
        self._rows[download] = row
        self.list.prepend(row)
        self.browser.show_status(_("Download avviato: {name}").format(name=os.path.basename(path)))
        return True

    def _confirm_dangerous(self, name, download):
        response = download.get_response()
        source = response.get_uri() if response is not None else ""
        dialog = Gtk.MessageDialog(
            transient_for=self.browser,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=_("«{name}» può eseguire programmi sul tuo PC").format(name=name),
        )
        dialog.format_secondary_text(
            _("Origine: {source}").format(source=source) + "\n"
            + _("Scaricalo solo se ti fidi del sito. Non verrà aperto in automatico.")
        )
        dialog.add_button(_("Annulla"), Gtk.ResponseType.CANCEL)
        keep = dialog.add_button(_("Scarica comunque"), Gtk.ResponseType.ACCEPT)
        keep.get_style_context().add_class("destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.ACCEPT

    def _on_progress(self, download, _param):
        row = self._rows.get(download)
        if row is not None:
            row.progress.set_fraction(download.get_estimated_progress())

    def _on_failed(self, download, error):
        row = self._rows.get(download)
        if row is not None:
            row.failed = True
            row.state.set_text(_("Non riuscito: {error}").format(error=error.message))

    def _on_finished(self, download):
        row = self._rows.pop(download, None)
        if row is None or row.failed:
            return
        row.progress.set_fraction(1.0)
        row.state.set_text(_("Completato alle {time}").format(time=time.strftime("%H:%M")))
        self.browser.show_status(_("Scaricato: {name}").format(name=os.path.basename(row.path)))
