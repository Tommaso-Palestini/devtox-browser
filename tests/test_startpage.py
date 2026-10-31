"""Pagina iniziale: dati locali, testi dei siti sempre escapati, stato dei filtri visibile."""

import os
import tempfile
import time
import unittest
from unittest import mock

from devtox import servers, startpage
from devtox.config import Config
from devtox.storage import Storage


class StartPageTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.config = Config(os.path.join(folder, "config.json"))
        self.storage = Storage(os.path.join(folder, "db.sqlite"))
        self.addCleanup(self.storage.close)

    def render(self, found=(), **kwargs):
        with mock.patch.object(startpage, "collect_servers", return_value=list(found)):
            return startpage.render(self.config, self.storage, now=time.time(), **kwargs)

    def test_titles_from_sites_are_escaped(self):
        self.storage.record_visit("https://evil.example/", "<img src=x onerror=alert(1)>")
        page = self.render()
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;img src=x", page)

    def test_servers_table(self):
        found = [servers.Server(5173, "127.0.0.1", 42, "vite", "~/progetti/sito", 3600)]
        page = self.render(found)
        self.assertIn('href="http://localhost:5173/"', page)
        self.assertIn("~/progetti/sito", page)
        self.assertIn("1 server in ascolto", page)

    def test_empty_state(self):
        self.assertIn("Niente è in ascolto", self.render())

    def test_stop_links_carry_the_token(self):
        found = [servers.Server(5173, "127.0.0.1", 42, "vite", "~/sito", 60),
                 servers.Server(8000, "127.0.0.1", 43, "django", "~/api", 60),
                 servers.Server(3000, "localhost")]  # di un altro utente: niente pulsante
        page = self.render(found)
        self.assertIn(f"devtox://stop?token={startpage.STOP_TOKEN}&amp;port=5173", page)
        self.assertNotIn("port=3000", page)
        self.assertIn(f"devtox://stop?token={startpage.STOP_TOKEN}&amp;port=all", page)
        # Con un solo server fermabile basta la croce della riga
        self.assertNotIn("port=all", self.render(found[:1]))

    def test_stop_page(self):
        found = [servers.Server(5173, "127.0.0.1", 42, "vite")]
        with mock.patch.object(startpage, "collect_servers", return_value=found), \
                mock.patch.object(servers.os, "kill") as kill:
            startpage.render_stop({"token": "sbagliato", "port": "all"}, self.config)
            kill.assert_not_called()
            startpage.render_stop({"token": startpage.STOP_TOKEN, "port": "x"}, self.config)
            kill.assert_not_called()
            page = startpage.render_stop({"token": startpage.STOP_TOKEN, "port": "5173"}, self.config)
            kill.assert_called_once()
        self.assertIn("devtox://start", page)

    def test_inactive_filters_are_shown(self):
        self.assertNotIn("non attivi", self.render(filters_active=True))
        self.assertIn("non attivi", self.render(filters_active=False))


if __name__ == "__main__":
    unittest.main()
