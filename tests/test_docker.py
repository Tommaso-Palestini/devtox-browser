"""Client Docker: Engine API su socket Unix, contro un demone finto."""

import http.server
import json
import os
import socketserver
import tempfile
import threading
import unittest

from devtox import docker

CONTAINERS = [
    {"Id": "a" * 64, "Names": ["/supabase_db_app"], "Image": "public.ecr.aws/supabase/postgres:17.1",
     "State": "running", "Status": "Up 2 hours (healthy)",
     "Ports": [{"IP": "0.0.0.0", "PrivatePort": 5432, "PublicPort": 54322, "Type": "tcp"},
               {"IP": "::", "PrivatePort": 5432, "PublicPort": 54322, "Type": "tcp"},
               {"PrivatePort": 9999, "Type": "tcp"}],
     "Labels": {"com.supabase.cli.project": "app"}},
    {"Id": "b" * 64, "Names": ["/web-1"], "Image": "nginx:1.27", "State": "exited",
     "Status": "Exited (0) 3 minutes ago", "Ports": [],
     "Labels": {"com.docker.compose.project": "shop"}},
    {"Id": "c" * 64, "Names": ["/solo"], "Image": "sha256:" + "d" * 64, "State": "running",
     "Status": "Up 5 seconds", "Ports": [], "Labels": {}},
]


class FakeDocker(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class Handler(http.server.BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *args):
        pass

    def _reply(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Handler.calls.append(("GET", self.path))
        if self.path.startswith("/containers/json"):
            self._reply(200, json.dumps(CONTAINERS).encode())
        else:
            self._reply(404, b'{"message": "not found"}')

    def do_POST(self):
        Handler.calls.append(("POST", self.path))
        if "/stop" in self.path and "missing" in self.path:
            self._reply(404, b'{"message": "No such container: missing"}')
        else:
            self._reply(204)


class DockerTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "docker.sock")
        self.server = FakeDocker(self.path, Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        Handler.calls = []
        self.client = docker.DockerClient(self.path)

    def test_containers(self):
        found = self.client.containers()
        self.assertEqual([c.name for c in found], ["supabase_db_app", "web-1", "solo"])
        db = found[0]
        self.assertTrue(db.running)
        self.assertEqual(db.project, "app")
        self.assertEqual(db.ports, [54322])          # pubblicate, senza doppioni IPv4/IPv6
        self.assertEqual(db.image, "supabase/postgres:17.1")  # niente registro davanti
        self.assertEqual(found[1].project, "shop")
        self.assertFalse(found[1].running)
        self.assertEqual(found[2].image, "dddddddddddd")  # immagine senza nome: id corto
        self.assertIn(("GET", "/containers/json?all=1"), Handler.calls)

    def test_actions(self):
        self.client.action("a" * 64, "restart")
        self.assertIn(("POST", f"/containers/{'a' * 64}/restart?t={docker.STOP_TIMEOUT}"), Handler.calls)
        with self.assertRaises(ValueError):
            self.client.action("a" * 64, "rm")  # solo stop, start, restart

    def test_errors_are_readable(self):
        with self.assertRaisesRegex(docker.DockerError, "No such container"):
            self.client.action("missing", "stop")

    def test_no_daemon(self):
        client = docker.DockerClient(os.path.join(tempfile.mkdtemp(), "none.sock"))
        with self.assertRaises(docker.DockerError):
            client.containers()


class FindSocketTest(unittest.TestCase):
    def test_only_local_unix_sockets(self):
        folder = tempfile.mkdtemp()
        sock = os.path.join(folder, "d.sock")
        open(sock, "w").close()
        self.assertEqual(docker.find_socket({"DOCKER_HOST": "unix://" + sock}, candidates=[]), sock)
        # Un demone remoto non si usa mai: Devtox non apre connessioni di rete per Docker
        self.assertIsNone(docker.find_socket({"DOCKER_HOST": "tcp://10.0.0.5:2375"}, candidates=[]))
        self.assertEqual(docker.find_socket({}, candidates=["/nope.sock", sock]), sock)


if __name__ == "__main__":
    unittest.main()
