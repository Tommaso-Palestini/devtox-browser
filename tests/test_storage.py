import os
import tempfile
import time
import unittest

from devtox.storage import Storage


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.storage = Storage(os.path.join(tempfile.mkdtemp(), "db.sqlite"))
        self.addCleanup(self.storage.close)

    def test_visits_are_counted_and_ranked(self):
        self.storage.record_visit("https://a.it/", "Alfa")
        self.storage.record_visit("https://b.it/", "Beta")
        self.storage.record_visit("https://b.it/", "")
        results = self.storage.search_history(".it")
        self.assertEqual(results[0], ("https://b.it/", "Beta"))  # il titolo vuoto non cancella quello vecchio
        self.assertEqual(len(results), 2)

    def test_search_matches_title(self):
        self.storage.record_visit("https://x.it/", "Documentazione Python")
        self.assertEqual(self.storage.search_history("python"), [("https://x.it/", "Documentazione Python")])

    def test_wildcards_are_literal(self):
        self.storage.record_visit("https://a.it/100%", "")
        self.storage.record_visit("https://a.it/x_y", "")
        self.storage.record_visit("https://a.it/xzy", "")
        self.assertEqual([r[0] for r in self.storage.search_history("%")], ["https://a.it/100%"])
        self.assertEqual([r[0] for r in self.storage.search_history("x_y")], ["https://a.it/x_y"])

    def test_expire_and_clear(self):
        self.storage.record_visit("https://old.it/", "")
        with self.storage.db:
            self.storage.db.execute("UPDATE history SET last_visit = ?", (time.time() - 10 * 86400,))
        self.storage.record_visit("https://new.it/", "")
        self.storage.expire_history(5)
        self.assertEqual([r[0] for r in self.storage.search_history("it")], ["https://new.it/"])
        self.storage.clear_history()
        self.assertEqual(self.storage.search_history("it"), [])

    def test_bookmarks_toggle(self):
        self.assertTrue(self.storage.toggle_bookmark("https://a.it/", "A"))
        self.assertTrue(self.storage.is_bookmarked("https://a.it/"))
        self.assertEqual(self.storage.bookmarks(), [("https://a.it/", "A")])
        self.assertFalse(self.storage.toggle_bookmark("https://a.it/", "A"))
        self.assertEqual(self.storage.bookmarks(), [])

    def test_session_roundtrip(self):
        tabs = [{"uri": "https://a.it/", "title": "A", "current": True}]
        self.storage.save_session(tabs)
        self.assertEqual(self.storage.load_session(), tabs)

    def test_broken_session_is_ignored(self):
        with open(self.storage.session_path, "w") as f:
            f.write('[{"uri": 3}, "x", {"uri": "https://ok.it/"}]')
        self.assertEqual(self.storage.load_session(), [{"uri": "https://ok.it/"}])
        with open(self.storage.session_path, "w") as f:
            f.write("non json")
        self.assertEqual(self.storage.load_session(), [])


if __name__ == "__main__":
    unittest.main()
