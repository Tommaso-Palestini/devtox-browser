"""Server locali dell'utente, letti da /proc: nessuna porta da configurare.

Per ogni socket TCP in ascolto che appartiene all'utente troviamo il processo
che lo tiene aperto, la cartella da cui è partito (di solito il progetto),
lo strumento (vite, next, http.server, ...) e da quanto tempo è attivo.
Si leggono solo file di /proc dell'utente stesso: niente privilegi, niente rete.
"""

import ipaddress
import os
import signal
import socket
import struct
import time
from dataclasses import dataclass

from .i18n import _

CLOCK_TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
LISTEN = "0A"
# Porte sotto 1024 e quelle effimere alte sono quasi sempre servizi di sistema o client
MIN_PORT, MAX_PORT = 1024, 32767

# Nome mostrato -> parole che lo rivelano nella riga di comando (in ordine di priorità)
_TOOLS = [
    ("vite", ("vite",)),
    ("next", ("next-server", "/next/dist/", "/.bin/next", "next dev", "next start")),
    ("nuxt", ("nuxt", "nuxi")),
    ("astro", ("astro",)),
    ("sveltekit", ("svelte-kit",)),
    ("remix", ("remix",)),
    ("webpack", ("webpack",)),
    ("parcel", ("parcel",)),
    ("storybook", ("storybook",)),
    ("http.server", ("http.server", "SimpleHTTPServer")),
    ("django", ("runserver",)),
    ("flask", ("flask",)),
    ("uvicorn", ("uvicorn",)),
    ("gunicorn", ("gunicorn",)),
    ("fastapi", ("fastapi",)),
    ("jupyter", ("jupyter",)),
    ("rails", ("rails",)),
    ("jekyll", ("jekyll",)),
    ("hugo", ("hugo",)),
    ("php", ("php",)),
    ("ollama", ("ollama",)),
    ("deno", ("deno",)),
    ("bun", ("bun",)),
]
# App desktop che stanno in ascolto su localhost ma non sono server di sviluppo:
# non compaiono nell'elenco e "Ferma tutti" non le tocca mai
_DESKTOP_APPS = {
    "steam", "steamwebhelper", "spotify", "syncthing", "kdeconnectd", "code", "code-oss", "codium",
    "cursor", "slack", "discord", "zoom", "teams", "telegram-desktop", "signal-desktop", "dropbox",
    "nextcloud", "obsidian", "jetbrains-toolbox", "chrome", "chromium", "firefox", "opera", "brave",
    "thunderbird", "gnome-shell", "plasmashell", "kdeconnect", "warp-svc", "tailscaled", "devtox",
}
_GENERIC = {"node", "python", "python3", "ruby", "java", "sh", "bash", "npm", "npx", "pnpm", "yarn"}


@dataclass
class Server:
    port: int
    host: str
    pid: int | None = None
    tool: str = ""
    project: str = ""
    uptime: float | None = None
    dev: bool = True

    @property
    def url(self):
        return f"http://localhost:{self.port}/"


def parse_address(text):
    """'0100007F:1435' -> ('127.0.0.1', 5173); gestisce anche gli indirizzi IPv6 di /proc."""
    hex_ip, hex_port = text.split(":")
    raw = bytes.fromhex(hex_ip)
    if len(raw) == 4:
        host = socket.inet_ntoa(struct.pack("<I", struct.unpack(">I", raw)[0]))
    else:
        # IPv6: quattro parole a 32 bit, ognuna in ordine little-endian
        words = struct.unpack(">4I", raw)
        host = str(ipaddress.IPv6Address(b"".join(struct.pack("<I", w) for w in words)))
    return host, int(hex_port, 16)


def guess_tool(comm, argv):
    """Nome breve dello strumento che serve la porta, dalla riga di comando."""
    line = " ".join(argv)
    for name, needles in _TOOLS:
        if any(n in line for n in needles):
            return name
    if comm and comm not in _GENERIC:
        return comm
    first = os.path.basename(argv[0]) if argv else ""
    return first or comm or "?"


def is_dev_process(comm, argv):
    """False per le app desktop note (Steam, Syncthing, l'editor...), True per tutto il resto."""
    names = {comm.lower(), os.path.basename(argv[0]).lower() if argv else ""}
    return not names & _DESKTOP_APPS


def _listeners(proc, uid):
    """{inode: (host, porta)} dei socket in ascolto dell'utente."""
    found = {}
    for name in ("tcp", "tcp6"):
        try:
            with open(os.path.join(proc, "net", name), encoding="ascii") as f:
                lines = f.readlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != LISTEN or fields[7] != str(uid):
                continue
            host, port = parse_address(fields[1])
            address = ipaddress.ip_address(host)
            # Solo ciò che si apre come localhost: loopback o tutte le interfacce
            if MIN_PORT <= port <= MAX_PORT and (address.is_loopback or address.is_unspecified):
                found.setdefault(fields[9], (host, port))
    return found


def _boot_time(proc):
    try:
        with open(os.path.join(proc, "stat"), encoding="ascii") as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def _read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except OSError:
        return None


def _describe(server, proc, pid, boot, now):
    base = os.path.join(proc, str(pid))
    comm = (_read(os.path.join(base, "comm")) or "").strip()
    raw = _read(os.path.join(base, "cmdline"), "rb") or b""
    argv = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
    server.pid = pid
    server.tool = guess_tool(comm, argv)
    server.dev = is_dev_process(comm, argv)
    try:
        cwd = os.readlink(os.path.join(base, "cwd"))
    except OSError:
        cwd = ""
    home = os.path.expanduser("~")
    if cwd == home or cwd.startswith(home + os.sep):
        cwd = "~" + cwd[len(home):]
    server.project = cwd
    stat = _read(os.path.join(base, "stat"))
    if stat and boot is not None:
        # Il nome del processo può contenere spazi e parentesi: si riparte dall'ultima ")"
        fields = stat[stat.rfind(")") + 2:].split()
        try:
            started = boot + int(fields[19]) / CLOCK_TICKS
            server.uptime = max(0, (now if now is not None else time.time()) - started)
        except (IndexError, ValueError):
            pass


def scan(proc="/proc", now=None):
    """Server in ascolto dell'utente, ordinati per porta. Lista vuota se /proc non c'è."""
    listeners = _listeners(proc, os.getuid())
    if not listeners:
        return []
    by_port = {}
    for inode, (host, port) in listeners.items():
        by_port.setdefault(port, Server(port=port, host=host))
    wanted = {f"socket:[{inode}]": port for inode, (_h, port) in listeners.items()}
    boot = _boot_time(proc)
    own = str(os.getpid())
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit() and p != own]
    except OSError:
        pids = []
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue  # processo di un altro utente o già finito
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            port = wanted.pop(target, None)
            if port is not None and by_port[port].pid is None:
                _describe(by_port[port], proc, int(pid), boot, now)
        if not wanted:
            break
    return sorted((s for s in by_port.values() if s.dev), key=lambda s: s.port)


def stop(found):
    """SIGTERM al processo di ogni server (la chiusura pulita, come Ctrl+C).

    Restituisce [(server, errore o None)]. Si fermano solo i processi trovati in /proc
    (quindi dell'utente) e mai Devtox stesso; un processo già finito non è un errore.
    """
    results = []
    for server in found:
        if server.pid is None:
            results.append((server, _("di un altro utente o di sistema: non si può fermare da qui")))
            continue
        if server.pid == os.getpid():
            results.append((server, _("è Devtox stesso")))
            continue
        try:
            os.kill(server.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # già finito
        except PermissionError:
            results.append((server, _("permesso negato")))
            continue
        results.append((server, None))
    return results


def format_uptime(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return _("{n} s").format(n=seconds)
    minutes = seconds // 60
    if minutes < 60:
        return _("{n} min").format(n=minutes)
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return _("{h} h {m} min").format(h=hours, m=minutes) if minutes else _("{n} h").format(n=hours)
    days, hours = divmod(hours, 24)
    return _("{d} g {h} h").format(d=days, h=hours) if hours else _("{n} g").format(n=days)


def select(found, ports):
    """I server da fermare: ports è "all" oppure un elenco di porte."""
    if ports == "all":
        return list(found)
    wanted = {int(p) for p in ports}
    return [s for s in found if s.port in wanted]


def appeared(previous_ports, found):
    """Server tuoi (con un processo) che non c'erano al controllo precedente."""
    return [s for s in found if s.port not in previous_ports and s.pid is not None]
