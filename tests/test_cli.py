"""Il comando sr contro un socket finto: protocollo e messaggi d'errore."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

SR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "sr")


class FakeBrowser(threading.Thread):
    def __init__(self, path, reply):
        super().__init__(daemon=True)
        self.reply = reply
        self.requests = []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen(1)

    def run(self):
        connection, _ = self.sock.accept()
        with connection:
            self.requests.append(json.loads(connection.makefile("rb").readline()))
            connection.sendall((json.dumps(self.reply) + "\n").encode())
        self.sock.close()


class SrTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sr.sock")

    def run_sr(self, *args):
        env = dict(os.environ, SHELLRUNNER_SOCKET=self.path)
        return subprocess.run([sys.executable, SR, *args], env=env, capture_output=True, text=True, timeout=10)

    def test_open_joins_words(self):
        browser = FakeBrowser(self.path, {"ok": True, "url": "https://duckduckgo.com/?q=a+b"})
        browser.start()
        result = self.run_sr("open", "a", "b")
        browser.join(5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(browser.requests, [{"cmd": "open", "url": "a b"}])
        self.assertIn("aperto:", result.stdout)

    def test_tabs(self):
        tab = {"index": 1, "title": "Esempio", "uri": "https://a.it/", "suspended": True, "current": True}
        browser = FakeBrowser(self.path, {"ok": True, "tabs": [tab]})
        browser.start()
        result = self.run_sr("tabs")
        browser.join(5)
        self.assertIn("*z Esempio", result.stdout)

    def test_servers(self):
        server = {"port": 5173, "tool": "vite", "project": "~/progetti/sito", "pid": 42,
                  "uptime": "2 h 14 min", "url": "http://localhost:5173/"}
        browser = FakeBrowser(self.path, {"ok": True, "servers": [server]})
        browser.start()
        result = self.run_sr("servers")
        browser.join(5)
        self.assertEqual(browser.requests, [{"cmd": "servers"}])
        self.assertRegex(result.stdout, r"5173\s+vite\s+~/progetti/sito\s+2 h 14 min")

    def test_no_servers(self):
        browser = FakeBrowser(self.path, {"ok": True, "servers": []})
        browser.start()
        result = self.run_sr("servers")
        browser.join(5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("nessun server", result.stdout)

    def test_error_from_browser(self):
        browser = FakeBrowser(self.path, {"ok": False, "error": "indirizzo vuoto"})
        browser.start()
        result = self.run_sr("open", "x")
        browser.join(5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("indirizzo vuoto", result.stderr)

    def test_not_running(self):
        result = self.run_sr("tabs")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non è in esecuzione", result.stderr)


if __name__ == "__main__":
    unittest.main()
