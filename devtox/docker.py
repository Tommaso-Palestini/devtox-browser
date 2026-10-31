"""Container Docker (o Podman) dell'utente, tramite la Engine API sul socket Unix locale.

Nessuna dipendenza e nessuna rete: si parla solo con un socket Unix sul PC
(Docker, Docker rootless o Podman, che espone la stessa API). Un DOCKER_HOST
remoto (tcp://, ssh://) viene ignorato di proposito. Le azioni possibili sono
tre: avvia, ferma, riavvia. Niente rimozioni.
"""

import http.client
import json
import os
import socket
from dataclasses import dataclass, field

from .i18n import _

ACTIONS = ("start", "stop", "restart")
TIMEOUT = 5
STOP_TIMEOUT = 15  # un container che non si ferma in tempo riceve SIGKILL dal demone
# Etichette con cui gli strumenti raggruppano i container in un progetto
PROJECT_LABELS = ("com.docker.compose.project", "com.supabase.cli.project", "io.podman.compose.project")


class DockerError(Exception):
    pass


@dataclass
class Container:
    id: str
    name: str
    image: str
    state: str
    status: str
    project: str = ""
    ports: list = field(default_factory=list)  # porte pubblicate su questo PC

    @property
    def running(self):
        return self.state == "running"


def find_socket(env=None, candidates=None):
    """Primo socket Unix utilizzabile; None se Docker non c'è o non è accessibile."""
    env = os.environ if env is None else env
    host = env.get("DOCKER_HOST", "")
    if host:
        # Un DOCKER_HOST esplicito vince, ma solo se è locale
        path = host[len("unix://"):] if host.startswith("unix://") else None
        return path if path and os.path.exists(path) else None
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    if candidates is None:
        candidates = [os.path.join(runtime, "docker.sock"), "/var/run/docker.sock",
                      os.path.join(runtime, "podman", "podman.sock")]
    for path in candidates:
        if os.path.exists(path) and os.access(path, os.R_OK | os.W_OK):
            return path
    return None


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=TIMEOUT)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def _short_image(image):
    """'public.ecr.aws/supabase/postgres:17' -> 'supabase/postgres:17'; un id -> 12 caratteri."""
    if image.startswith("sha256:"):
        return image[7:19]
    parts = image.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        parts = parts[1:]  # il registro non serve a riconoscere l'immagine
    return "/".join(parts)


class DockerClient:
    def __init__(self, path):
        self.path = path

    def _request(self, method, url, timeout=TIMEOUT):
        connection = _UnixConnection(self.path)
        connection.timeout = timeout
        try:
            connection.request(method, url)
            response = connection.getresponse()
            body = response.read()
        except OSError as e:
            raise DockerError(_("Docker non risponde: {error}").format(error=e)) from e
        finally:
            connection.close()
        if response.status >= 400:
            try:
                message = json.loads(body).get("message", "")
            except ValueError:
                message = body.decode(errors="replace")[:200]
            raise DockerError(message or f"HTTP {response.status}")
        return json.loads(body) if body else None

    def containers(self):
        """Tutti i container (anche fermi), i progetti raggruppati e i più recenti per primi."""
        found = []
        for item in self._request("GET", "/containers/json?all=1") or []:
            labels = item.get("Labels") or {}
            project = next((labels[k] for k in PROJECT_LABELS if labels.get(k)), "")
            ports = sorted({p["PublicPort"] for p in item.get("Ports") or [] if p.get("PublicPort")})
            names = item.get("Names") or [item.get("Id", "")[:12]]
            found.append(Container(
                id=item.get("Id", ""), name=names[0].lstrip("/"), image=_short_image(item.get("Image", "")),
                state=item.get("State", ""), status=item.get("Status", ""), project=project, ports=ports,
            ))
        return found

    def action(self, container_id, action):
        if action not in ACTIONS:
            raise ValueError(action)
        url = f"/containers/{container_id}/{action}"
        if action in ("stop", "restart"):
            url += f"?t={STOP_TIMEOUT}"
        self._request("POST", url, timeout=STOP_TIMEOUT + TIMEOUT)
