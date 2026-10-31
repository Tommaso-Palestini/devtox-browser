"""Leggerezza: memoria e CPU dei processi del browser, letti da /proc."""

import collections
import os
import time

from gi.repository import GLib, Gtk

from . import theme, utils
from .i18n import _

_CLK_TCK = os.sysconf("SC_CLK_TCK")

ProcessInfo = collections.namedtuple("ProcessInfo", "pid name kind pss_kb cpu")


def _read_stat(pid):
    """(nome, ppid, tick di CPU usati) da /proc/<pid>/stat."""
    with open(f"/proc/{pid}/stat") as f:
        data = f.read()
    # Il nome sta tra parentesi e può contenere spazi: si taglia sull'ultima ")"
    end = data.rfind(")")
    name = data[data.find("(") + 1:end]
    fields = data[end + 2:].split()
    return name, int(fields[1]), int(fields[11]) + int(fields[12])


def _read_memory_kb(pid):
    """PSS (memoria proporzionale, conta le pagine condivise una volta sola)."""
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except OSError:
        pass
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    return 0


def browser_processes():
    """Il nostro processo e tutti i discendenti: {pid: ppid}."""
    children = collections.defaultdict(list)
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            _name, ppid, _ticks = _read_stat(entry)
        except (OSError, ValueError, IndexError):
            continue
        children[ppid].append(int(entry))

    root = os.getpid()
    parents, queue = {root: None}, [root]
    while queue:
        pid = queue.pop()
        for child in children.get(pid, []):
            parents[child] = pid
            queue.append(child)
    return parents


def _descends_from(pid, roots, parents):
    while pid is not None:
        if pid in roots:
            return True
        pid = parents.get(pid)
    return False


def kind_label(kind):
    return {
        "ui": _("Interfaccia"), "web": _("Pagine web"), "network": _("Rete"),
        "terminal": _("Terminale"), "helper": _("Ausiliario"),
    }.get(kind, kind)


def _kind(pid, name, terminal_roots, parents):
    if pid == os.getpid():
        return "ui"
    if name.startswith("WebKitWebProces"):
        return "web"
    if name.startswith("WebKitNetworkPr"):
        return "network"
    if _descends_from(pid, terminal_roots, parents):
        return "terminal"
    return "helper"  # es. gst-plugin-scanner di GStreamer


class ProcessSampler:
    """Ricorda la misura precedente per calcolare la CPU % tra due campioni."""

    def __init__(self, terminal_pids=None):
        # terminal_pids(): PID delle shell aperte nel pannello terminale
        self._terminal_pids = terminal_pids or (lambda: set())
        self._previous = {}  # pid -> (tick, istante)

    def sample(self):
        now = time.monotonic()
        current, rows = {}, []
        parents = browser_processes()
        terminal_roots = self._terminal_pids()
        for pid in parents:
            try:
                name, _ppid, ticks = _read_stat(pid)
                memory = _read_memory_kb(pid)
            except (OSError, ValueError, IndexError):
                continue  # processo appena terminato
            cpu = None
            previous = self._previous.get(pid)
            if previous is not None and now > previous[1]:
                cpu = (ticks - previous[0]) / _CLK_TCK / (now - previous[1]) * 100
            current[pid] = (ticks, now)
            rows.append(ProcessInfo(pid, name, _kind(pid, name, terminal_roots, parents), memory, cpu))
        self._previous = current
        return rows


def total_memory_kb():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    return 0


def summarize(rows):
    """Totali separati: il browser e i programmi lanciati dal terminale."""
    browser = sum(r.pss_kb for r in rows if r.kind != "terminal")
    terminal = sum(r.pss_kb for r in rows if r.kind == "terminal")
    return browser, terminal


class MemoryPanel(Gtk.Box):
    title = _("Memoria")
    REFRESH_SECONDS = 2

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        self.browser = window
        self.sampler = ProcessSampler(window.terminal_panel.shell_pids)
        self._timer = 0

        self.summary = Gtk.Label(xalign=0)
        self.summary.set_line_wrap(True)
        self.pack_start(self.summary, False, False, 0)

        # pid, tipo, nome, memoria (testo), cpu (testo), memoria (kB, per ordinare)
        self.store = Gtk.ListStore(int, str, str, str, str, int)
        self.store.set_sort_column_id(5, Gtk.SortType.DESCENDING)
        view = Gtk.TreeView(model=self.store)
        for title, column, sort in (("PID", 0, 0), (_("Tipo"), 1, 1), (_("Processo"), 2, 2),
                                    ("RAM", 3, 5), ("CPU", 4, 4)):
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(title, renderer, text=column)
            col.set_sort_column_id(sort)
            col.set_resizable(True)
            view.append_column(col)

        scrolled = Gtk.ScrolledWindow()
        scrolled.add(view)
        self.pack_start(scrolled, True, True, 0)

        note = Gtk.Label(
            label=_("RAM = PSS: la memoria condivisa è divisa tra i processi che la usano."),
            xalign=0,
        )
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim-label")
        self.pack_start(note, False, False, 0)

    def set_active(self, active):
        """Il timer gira solo mentre il pannello è visibile."""
        if active and not self._timer:
            self.refresh()
            self._timer = GLib.timeout_add_seconds(self.REFRESH_SECONDS, self.refresh)
        elif not active and self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def refresh(self):
        rows = self.sampler.sample()
        self.store.clear()
        for row in rows:
            cpu = "…" if row.cpu is None else f"{row.cpu:.0f}%"
            self.store.append([row.pid, kind_label(row.kind), row.name, utils.format_kb(row.pss_kb), cpu, row.pss_kb])

        browser_kb, terminal_kb = summarize(rows)
        open_tabs, suspended = self.browser.tab_counts()
        self.summary.set_text(
            _("Browser: {browser} · Terminale: {terminal}").format(
                browser=utils.format_kb(browser_kb), terminal=utils.format_kb(terminal_kb)) + "\n"
            + _("Tab: {open} aperte, {suspended} sospese").format(open=open_tabs, suspended=suspended)
        )
        return GLib.SOURCE_CONTINUE


class RamMeter(Gtk.Button):
    """Indicatore nella barra laterale: RAM del browser rispetto a quella del PC.

    Verde fino al 20% della RAM totale, ambra fino al 35%, poi rosso.
    Si aggiorna ogni pochi secondi e solo quando la finestra è visibile.
    """

    REFRESH_SECONDS = 3
    BAR_WIDTH = 4
    BAR_HEIGHT = 64

    def __init__(self, terminal_pids):
        super().__init__()
        self.set_name("ram-button")
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.sampler = ProcessSampler(terminal_pids)
        self.total_kb = total_memory_kb() or 1
        self._fraction = 0.0
        self._animation = theme.Animation(self)

        self.bar = Gtk.DrawingArea()
        self.bar.set_size_request(self.BAR_WIDTH, self.BAR_HEIGHT)
        self.bar.set_halign(Gtk.Align.CENTER)
        self.bar.connect("draw", self._on_draw)
        self.label = Gtk.Label()
        self.label.set_name("ram-label")
        self.label.set_justify(Gtk.Justification.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(self.bar, False, False, 0)
        box.pack_start(self.label, False, False, 0)
        self.add(box)

        self.refresh()
        GLib.timeout_add_seconds(self.REFRESH_SECONDS, self.refresh)

    def refresh(self):
        if self.get_mapped():
            browser_kb, _terminal_kb = summarize(self.sampler.sample())
            fraction = min(1.0, browser_kb / self.total_kb)
            mb = browser_kb / 1024
            self.label.set_text(f"{mb:.0f}\nMB" if mb < 1000 else f"{mb / 1024:.1f}\nGB")
            self.set_tooltip_text(
                _("Browser: {memory} ({fraction:.0%} della RAM)").format(
                    memory=utils.format_kb(browser_kb), fraction=fraction) + "\n"
                + _("Clic per i dettagli (Shift+Esc)")
            )
            self._animation.run(self._fraction, fraction, 600, self._set_fraction)
        return GLib.SOURCE_CONTINUE

    def _set_fraction(self, value):
        self._fraction = value
        self.bar.queue_draw()

    def _color(self):
        if self._fraction < 0.20:
            return theme.ACCENT
        if self._fraction < 0.35:
            return theme.WARNING
        return theme.NEGATIVE

    def _on_draw(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        radius = width / 2
        track = theme.rgba(theme.RULE)
        cr.set_source_rgba(track.red, track.green, track.blue, 1)
        _rounded_bar(cr, 0, 0, width, height, radius)
        cr.fill()
        # La barra si riempie dal basso; scala fino al 50% della RAM per essere leggibile
        filled = height * min(1.0, self._fraction / 0.5)
        if filled > 0:
            color = theme.rgba(self._color())
            cr.set_source_rgba(color.red, color.green, color.blue, 1)
            _rounded_bar(cr, 0, height - filled, width, filled, min(radius, filled / 2))
            cr.fill()
        return False


def _rounded_bar(cr, x, y, width, height, radius):
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -1.5708, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, 1.5708)
    cr.arc(x + radius, y + height - radius, radius, 1.5708, 3.1416)
    cr.arc(x + radius, y + radius, radius, 3.1416, 4.7124)
    cr.close_path()
