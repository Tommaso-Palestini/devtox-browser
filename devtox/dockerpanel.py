"""Pannello Docker nella barra laterale: container raggruppati per progetto, con le azioni.

Le chiamate al demone girano in un thread (il socket può rispondere lento) e
il pannello si aggiorna solo mentre è aperto. I widget vengono ricostruiti
solo quando i dati cambiano: un menu aperto non si chiude a ogni giro.
"""

import shlex
import shutil
import threading

from gi.repository import GLib, Gtk, Pango

from . import docker
from .i18n import _

REFRESH_SECONDS = 4


def _run_in_thread(work, done):
    """work() in un thread; done(risultato, errore) nel thread di GTK."""
    def worker():
        try:
            result, error = work(), None
        except docker.DockerError as e:
            result, error = None, str(e)
        GLib.idle_add(lambda: done(result, error) and False)
    threading.Thread(target=worker, daemon=True).start()


def group_by_project(containers):
    """[(progetto, [container])]: prima i progetti con qualcosa acceso, poi per nome."""
    groups = {}
    for container in containers:
        groups.setdefault(container.project, []).append(container)
    for items in groups.values():
        items.sort(key=lambda c: (not c.running, c.name))
    return sorted(groups.items(), key=lambda g: (not any(c.running for c in g[1]), g[0] == "", g[0]))


class DockerPanel(Gtk.Box):
    title = "Docker"

    def __init__(self, browser):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_border_width(8)
        self.browser = browser
        self._timer = 0
        self._busy = False
        self._signature = None
        self._containers = []
        self.client = None

        top = Gtk.Box(spacing=8)
        self.summary = Gtk.Label(xalign=0)
        self.summary.set_line_wrap(True)
        self.stop_all_button = Gtk.Button(label=_("Ferma tutti"))
        self.stop_all_button.get_style_context().add_class("danger")
        self.stop_all_button.set_tooltip_text(_("Ferma tutti i container accesi"))
        self.stop_all_button.connect("clicked", lambda _b: self._confirm_stop(
            [c for c in self._containers if c.running], _("Fermare tutti i container accesi?")))
        top.pack_start(self.summary, True, True, 0)
        top.pack_end(self.stop_all_button, False, False, 0)
        self.pack_start(top, False, False, 0)

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.list)
        self.pack_start(scrolled, True, True, 0)

    # --- Aggiornamento --------------------------------------------------

    def set_active(self, active):
        """Docker si interroga solo a pannello aperto."""
        if active and not self._timer:
            self.refresh()
            self._timer = GLib.timeout_add_seconds(REFRESH_SECONDS, self.refresh)
        elif not active and self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def refresh(self):
        if self._busy:
            return GLib.SOURCE_CONTINUE
        path = docker.find_socket()
        if path is None:
            self._show_message(_("Docker non trovato. Se è installato, il tuo utente deve poter usare il "
                                 "socket: sudo usermod -aG docker $USER, poi esci e rientra."))
            return GLib.SOURCE_CONTINUE
        if self.client is None or self.client.path != path:
            self.client = docker.DockerClient(path)
        self._busy = True
        _run_in_thread(self.client.containers, self._on_containers)
        return GLib.SOURCE_CONTINUE

    def _on_containers(self, containers, error):
        self._busy = False
        if error is not None:
            self._show_message(error)
            return
        signature = [(c.id, c.state, c.status, tuple(c.ports)) for c in containers]
        self._containers = containers
        running = sum(c.running for c in containers)
        self.summary.set_text(_("{running} accesi su {total}").format(running=running, total=len(containers)))
        self.stop_all_button.set_visible(running > 0)
        if signature != self._signature:
            self._signature = signature
            self._rebuild(containers)

    def _show_message(self, text):
        self._signature = None
        self._containers = []
        self.summary.set_text("")
        self.stop_all_button.hide()
        self._clear()
        label = Gtk.Label(label=text, xalign=0)
        label.set_line_wrap(True)
        label.set_selectable(True)
        label.get_style_context().add_class("dim-label")
        self.list.pack_start(label, False, False, 0)
        label.show()

    def _clear(self):
        for child in self.list.get_children():
            self.list.remove(child)

    # --- Righe ------------------------------------------------------------

    def _rebuild(self, containers):
        self._clear()
        if not containers:
            self._show_message(_("Nessun container. Quelli che crei con docker o docker compose compaiono qui."))
            return
        for project, items in group_by_project(containers):
            self.list.pack_start(self._group(project, items), False, False, 0)
        self.list.show_all()
        self.stop_all_button.set_visible(any(c.running for c in containers))

    def _group(self, project, items):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        running = [c for c in items if c.running]
        header = Gtk.Box(spacing=6)
        name = Gtk.Label(label=project or _("Senza progetto"), xalign=0)
        name.get_style_context().add_class("docker-project")
        count = Gtk.Label(label=f"{len(running)}/{len(items)}", xalign=0)
        count.get_style_context().add_class("dim-label")
        header.pack_start(name, False, False, 0)
        header.pack_start(count, False, False, 0)
        if project:
            if running:
                button = self._icon_button("media-playback-stop-symbolic", _("Ferma il progetto"))
                button.connect("clicked", lambda _b: self._confirm_stop(
                    running, _("Fermare il progetto {name}?").format(name=project)))
            else:
                button = self._icon_button("media-playback-start-symbolic", _("Avvia il progetto"))
                button.connect("clicked", lambda _b: self._act(items, "start"))
            header.pack_end(button, False, False, 0)
        box.pack_start(header, False, False, 0)

        stopped = [c for c in items if not c.running]
        for container in running:
            box.pack_start(self._row(container), False, False, 0)
        if stopped:
            # I container fermi non servono a colpo d'occhio: stanno sotto un espansore
            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            for container in stopped:
                rows.pack_start(self._row(container), False, False, 0)
            if running:
                expander = Gtk.Expander(label=_("{n} fermi").format(n=len(stopped)))
                expander.get_style_context().add_class("docker-stopped")
                expander.add(rows)
                box.pack_start(expander, False, False, 0)
            else:
                box.pack_start(rows, False, False, 0)
        return box

    def _row(self, container):
        row = Gtk.Box(spacing=8)
        row.get_style_context().add_class("docker-row")
        dot = Gtk.Label(label="●")
        dot.get_style_context().add_class("docker-on" if container.running else "docker-off")
        dot.set_valign(Gtk.Align.START)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(label=container.name, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        detail = Gtk.Label(label=f"{container.image} · {container.status}", xalign=0,
                           ellipsize=Pango.EllipsizeMode.END)
        detail.get_style_context().add_class("dim-label")
        detail.set_tooltip_text(f"{container.image}\n{container.status}")
        text.pack_start(name, False, False, 0)
        text.pack_start(detail, False, False, 0)
        if container.running and container.ports:
            ports = Gtk.Box(spacing=4)
            for port in container.ports[:4]:
                link = Gtk.Button(label=f":{port}")
                link.set_relief(Gtk.ReliefStyle.NONE)
                link.get_style_context().add_class("docker-port")
                link.set_tooltip_text(_("Apri http://localhost:{port}/").format(port=port))
                link.connect("clicked", lambda _b, p=port: self.browser.new_tab(f"http://localhost:{p}/"))
                ports.pack_start(link, False, False, 0)
            text.pack_start(ports, False, False, 0)
        row.pack_start(dot, False, False, 0)
        row.pack_start(text, True, True, 0)
        row.pack_end(self._menu(container), False, False, 0)
        return row

    def _menu(self, container):
        menu = Gtk.Menu()

        def item(label, callback):
            entry = Gtk.MenuItem(label=label)
            entry.connect("activate", lambda _i: callback())
            menu.append(entry)

        if container.running:
            item(_("Ferma"), lambda: self._act([container], "stop"))
            item(_("Riavvia"), lambda: self._act([container], "restart"))
        else:
            item(_("Avvia"), lambda: self._act([container], "start"))
        item(_("Log nel terminale"), lambda: self._logs(container))
        menu.show_all()
        button = Gtk.MenuButton(popup=menu)
        button.set_image(Gtk.Image.new_from_icon_name("view-more-symbolic", Gtk.IconSize.MENU))
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_valign(Gtk.Align.START)
        button.set_tooltip_text(_("Azioni"))
        return button

    @staticmethod
    def _icon_button(icon, tooltip):
        button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.MENU)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_tooltip_text(tooltip)
        return button

    # --- Azioni -----------------------------------------------------------

    def _confirm_stop(self, containers, question):
        if not containers:
            return
        dialog = Gtk.MessageDialog(transient_for=self.get_toplevel(), modal=True,
                                   message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.OK_CANCEL, text=question)
        names = "\n".join(c.name for c in containers[:12])
        more = len(containers) - 12
        dialog.format_secondary_text(names + (f"\n… +{more}" if more > 0 else ""))
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self._act(containers, "stop")

    def _act(self, containers, action):
        client = self.client
        words = {"start": _("Avvio"), "stop": _("Arresto"), "restart": _("Riavvio")}
        self.browser.show_status(_("{action} di {n} container…").format(action=words[action], n=len(containers)))

        def work():
            errors = []
            for container in containers:
                try:
                    client.action(container.id, action)
                except docker.DockerError as e:
                    errors.append(f"{container.name}: {e}")
            return errors

        def done(errors, error):
            errors = errors or ([error] if error else [])
            if errors:
                self.browser.show_status(_("Non riuscito: {error}").format(error=errors[0]), seconds=8)
            else:
                self.browser.show_status(_("Fatto: {action} di {n} container").format(
                    action=words[action].lower(), n=len(containers)))
            self.refresh()

        _run_in_thread(work, done)

    def _logs(self, container):
        if shutil.which("docker") is None:
            self.browser.show_status(_("Per i log serve il comando docker"))
            return
        self.browser.show_terminal()
        self.browser.terminal_panel.new_terminal()
        # Il comando si vede nel terminale e parte subito: è quello che hai chiesto
        self.browser.terminal_panel.paste_command(
            f"docker logs -f --tail 200 {shlex.quote(container.name)}", run=True)
