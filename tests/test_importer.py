"""Import di preferiti e cronologia da Firefox e dai browser Chromium, su profili finti."""

import json
import os
import sqlite3
import tempfile
import time
import unittest

from devtox import importer
from devtox.storage import Storage

NOW = 1_800_000_000  # secondi Unix
CHROME_EPOCH = 11_644_473_600  # secondi tra il 1601 e il 1970


def make_chromium(home, rel):
    profile = os.path.join(home, rel, "Default")
    os.makedirs(profile)
    bookmarks = {"roots": {
        "bookmark_bar": {"type": "folder", "children": [
            {"type": "url", "name": "Docs", "url": "https://docs.example/"},
            {"type": "folder", "name": "Dev", "children": [
                {"type": "url", "name": "Repo", "url": "https://git.example/repo"},
                {"type": "url", "name": "Locale", "url": "file:///etc/passwd"},
            ]},
        ]},
        "other": {"type": "folder", "children": []},
        # Opera: speed dial e cestino in una radice propria
        "custom_root": {
            "speedDial": {"type": "folder", "children": [{"type": "url", "name": "Dial", "url": "https://dial.example/"}]},
            "trash": {"type": "folder", "children": [{"type": "url", "name": "Buttato", "url": "https://trash.example/"}]},
            "unsyncedPinboard": {"type": "folder", "children": [{"type": "url", "name": "P", "url": "https://pinboard.opera.com/x"}]},
        },
    }}
    with open(os.path.join(profile, "Bookmarks"), "w") as f:
        json.dump(bookmarks, f)
    db = sqlite3.connect(os.path.join(profile, "History"))
    db.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, "
               "typed_count INTEGER, last_visit_time INTEGER, hidden INTEGER)")
    rows = [("https://docs.example/", "Docs", 7, NOW - 3600, 0),
            ("https://old.example/", "Vecchia", 1, NOW - 400 * 86400, 0),
            ("https://hidden.example/", "Nascosta", 1, NOW - 60, 1),
            ("chrome://settings/", "Impostazioni", 3, NOW - 60, 0)]
    for url, title, visits, when, hidden in rows:
        db.execute("INSERT INTO urls (url, title, visit_count, typed_count, last_visit_time, hidden) "
                   "VALUES (?, ?, ?, 0, ?, ?)", (url, title, visits, (when + CHROME_EPOCH) * 1_000_000, hidden))
    db.commit()
    db.close()
    return profile


def make_firefox(home, rel):
    profile = os.path.join(home, rel, "abcd.default-release")
    os.makedirs(profile)
    db = sqlite3.connect(os.path.join(profile, "places.sqlite"))
    db.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, "
               "last_visit_date INTEGER)")
    db.execute("CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER, title TEXT, "
               "dateAdded INTEGER)")
    db.execute("INSERT INTO moz_places VALUES (1, 'https://mdn.example/', 'MDN', 12, ?)", ((NOW - 600) * 1_000_000,))
    db.execute("INSERT INTO moz_places VALUES (2, 'place:sort=8', NULL, 0, NULL)")
    db.execute("INSERT INTO moz_places VALUES (3, 'https://never.example/', 'Mai visitata', 0, NULL)")
    db.execute("INSERT INTO moz_bookmarks VALUES (1, 1, 1, 'MDN web docs', 0)")
    db.execute("INSERT INTO moz_bookmarks VALUES (2, 1, 2, 'Più visitati', 0)")
    db.execute("INSERT INTO moz_bookmarks VALUES (3, 1, 3, 'Da leggere', 0)")
    db.commit()
    db.close()
    return profile


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_finds_profiles_with_data(self):
        make_chromium(self.home, ".var/app/com.opera.opera-gx/config/opera-gx")
        make_chromium(self.home, ".config/google-chrome")
        make_firefox(self.home, ".mozilla/firefox")
        os.makedirs(os.path.join(self.home, ".config/BraveSoftware/Brave-Browser/Default"))  # vuoto
        found = importer.discover(self.home)
        names = sorted(source.name for source in found)
        self.assertEqual(names, ["Firefox", "Google Chrome", "Opera GX (Flatpak)"])

    def test_tor_browser_is_never_offered(self):
        make_firefox(self.home, ".var/app/org.torproject.torbrowser-launcher/data/torbrowser/tbb/x86_64/"
                                "tor-browser/Browser/TorBrowser/Data/Browser/profile.default/..")
        self.assertEqual(importer.discover(self.home), [])


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_chromium(self):
        source = importer.Source("Chrome", "chromium", make_chromium(self.home, ".config/google-chrome"))
        bookmarks = source.bookmarks()
        self.assertEqual([b[0] for b in bookmarks],
                         ["https://docs.example/", "https://git.example/repo", "https://dial.example/"])
        history = source.history(since=NOW - 90 * 86400)
        self.assertEqual([(h[0], h[2]) for h in history], [("https://docs.example/", 7)])
        self.assertAlmostEqual(history[0][3], NOW - 3600, delta=1)

    def test_firefox(self):
        source = importer.Source("Firefox", "firefox", make_firefox(self.home, ".mozilla/firefox"))
        self.assertEqual(source.bookmarks(), [("https://mdn.example/", "MDN web docs"),
                                              ("https://never.example/", "Da leggere")])
        history = source.history(since=0)
        self.assertEqual([(h[0], h[2]) for h in history], [("https://mdn.example/", 12)])

    def test_locked_database_is_read_from_a_copy(self):
        # Il browser aperto tiene il database bloccato: si legge una copia
        profile = make_firefox(self.home, ".mozilla/firefox")
        lock = sqlite3.connect(os.path.join(profile, "places.sqlite"))
        lock.execute("BEGIN EXCLUSIVE")
        try:
            self.assertEqual(len(importer.Source("Firefox", "firefox", profile).history(since=0)), 1)
        finally:
            lock.rollback()
            lock.close()


class StorageImportTest(unittest.TestCase):
    def setUp(self):
        self.storage = Storage(os.path.join(tempfile.mkdtemp(), "db.sqlite"))
        self.addCleanup(self.storage.close)

    def test_import_twice_adds_nothing_new(self):
        rows = [("https://a.example/", "A"), ("https://b.example/", "B")]
        self.assertEqual(self.storage.import_bookmarks(rows), 2)
        self.assertEqual(self.storage.import_bookmarks(rows), 0)
        history = [("https://a.example/", "A", 5, time.time() - 60)]
        self.assertEqual(self.storage.import_history(history), 1)
        self.storage.import_history(history)
        visits = self.storage.db.execute("SELECT visits FROM history").fetchone()[0]
        self.assertEqual(visits, 5)  # non raddoppia


if __name__ == "__main__":
    unittest.main()


class ImportPageTest(unittest.TestCase):
    def setUp(self):
        from devtox.config import Config
        folder = tempfile.mkdtemp()
        self.config = Config(os.path.join(folder, "config.json"))
        self.storage = Storage(os.path.join(folder, "db.sqlite"))
        self.addCleanup(self.storage.close)
        self.home = tempfile.mkdtemp()
        self.source = importer.Source("Chrome", "chromium", make_chromium(self.home, ".config/google-chrome"))

    def render(self, **params):
        from devtox import importpage
        return importpage.render(params, self.config, self.storage, discover=lambda: [self.source])

    def test_lists_sources_with_counts(self):
        page = self.render()
        self.assertIn("Chrome", page)
        self.assertIn("3 preferiti", page)
        self.assertEqual(self.storage.bookmarks(), [])

    def test_imports_with_token(self):
        from devtox import importpage
        page = self.render(token=importpage.TOKEN, source=self.source.id, bookmarks="on")
        self.assertIn("Import completato", page)
        self.assertEqual(len(self.storage.bookmarks()), 3)

    def test_wrong_token_or_unknown_path_imports_nothing(self):
        from devtox import importpage
        self.render(token="sbagliato", source=self.source.id, bookmarks="on")
        self.render(token=importpage.TOKEN, source="/etc", bookmarks="on")
        self.assertEqual(self.storage.bookmarks(), [])
