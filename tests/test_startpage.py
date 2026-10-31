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

    def test_inactive_filters_are_shown(self):
        self.assertNotIn("non attivi", self.render(filters_active=True))
        self.assertIn("non attivi", self.render(filters_active=False))


if __name__ == "__main__":
    unittest.main()
