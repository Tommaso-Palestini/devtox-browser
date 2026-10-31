"""Controllo del browser dal terminale: socket Unix locale usato dal comando dx.

Protocollo: una riga JSON di richiesta, una riga JSON di risposta.
  {"cmd": "open", "url": "localhost:5173"}
  {"cmd": "tabs"}
  {"cmd": "mem"}
  {"cmd": "servers"}
"""

import json
import os
import socket

from gi.repository import Gio, GLib

from . import monitor, servers, startpage, utils
from .i18n import _
from .log import logger

MAX_REQUEST_BYTES = 64 * 1024
MAX_SOCKET_PATH = 108  # sun_path di Linux, terminatore compreso


class ControlServer:
    def __init__(self, window):
        self.window = window
        self.path = utils.socket_path()
        self.service = None

    def start(self):
        if os.path.exists(self.path):
            if _socket_alive(self.path):
                logger.warning("un'altra istanza usa già %s: comando dx disattivato", self.path)
                return
            os.unlink(self.path)  # socket rimasto da un'esecuzione interrotta

        if len(os.fsencode(self.path)) >= MAX_SOCKET_PATH:
            logger.warning("percorso del socket troppo lungo (%s): comando dx disattivato", self.path)
            return
        service = Gio.SocketService()
        try:
            service.add_address(
                Gio.UnixSocketAddress.new(self.path),
                Gio.SocketType.STREAM,
                Gio.SocketProtocol.DEFAULT,
                None,
            )
            os.chmod(self.path, 0o600)
        except (GLib.Error, OSError) as e:
            # Senza socket il browser funziona lo stesso: si perde solo il comando dx
            logger.warning("socket %s non disponibile, comando dx disattivato: %s", self.path, e)
            return
        self.service = service
        self.service.connect("incoming", self._on_incoming)
        self.service.start()

    def stop(self):
        if self.service is not None:
            self.service.stop()
            self.service.close()
            self.service = None
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass

    def _on_incoming(self, _service, connection, _source):
        # Solo processi dello stesso utente (oltre ai permessi 0600 del file)
        credentials = connection.get_socket().get_credentials()
        if credentials.get_unix_user() != os.getuid():
            connection.close(None)
            return True
        stream = Gio.DataInputStream.new(connection.get_input_stream())
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, self._on_line, connection)
        return True

    def _on_line(self, stream, result, connection):
        try:
            line, length = stream.read_line_finish_utf8(result)
        except GLib.Error as e:
            response = {"ok": False, "error": e.message}
        else:
            if line is None or length > MAX_REQUEST_BYTES:
                response = {"ok": False, "error": _("richiesta vuota o troppo lunga")}
            else:
                response = self._handle(line)
        try:
            data = (json.dumps(response, ensure_ascii=False) + "\n").encode()
            connection.get_output_stream().write_all(data, None)
        except GLib.Error:
            pass  # il client ha chiuso prima della risposta
        connection.close(None)

    def _handle(self, line):
        try:
            request = json.loads(line)
            command = request["cmd"]
        except (ValueError, KeyError, TypeError):
            return {"ok": False, "error": _("JSON non valido")}

        if command == "open":
            url = self.window.open_from_cli(str(request.get("url", "")))
            if url is None:
                return {"ok": False, "error": _("indirizzo vuoto")}
            return {"ok": True, "url": url}
        if command == "tabs":
            return {"ok": True, "tabs": self.window.list_tabs()}
        if command == "mem":
            rows = monitor.ProcessSampler(self.window.terminal_panel.shell_pids).sample()
            browser_kb, terminal_kb = monitor.summarize(rows)
            return {
                "ok": True,
                "browser_kb": browser_kb,
                "terminal_kb": terminal_kb,
                "processes": [
                    {"pid": r.pid, "kind": monitor.kind_label(r.kind), "name": r.name, "pss_kb": r.pss_kb} for r in rows
                ],
            }
        if command == "servers":
            return {
                "ok": True,
                "servers": [
                    {"port": s.port, "tool": s.tool, "project": s.project, "pid": s.pid,
                     "uptime": servers.format_uptime(s.uptime), "url": s.url}
                    for s in startpage.collect_servers(self.window.config["dev_ports"])
                ],
            }
        return {"ok": False, "error": _("comando sconosciuto: {command}").format(command=command)}


def _socket_alive(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        try:
            probe.connect(path)
            return True
        except OSError:
            return False


def send_to_running(request):
    """Inoltra una richiesta all'istanza già aperta; None se non ce n'è una."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        try:
            sock.connect(utils.socket_path())
            sock.sendall((json.dumps(request) + "\n").encode())
            data = sock.makefile("rb").readline()
        except OSError:
            return None
    try:
        return json.loads(data)
    except ValueError:
        return None
