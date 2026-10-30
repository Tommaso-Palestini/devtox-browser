import json
import unittest

from shellrunner import about, deps, ui
from shellrunner.control import ControlServer


class FuzzyScoreTest(unittest.TestCase):
    def test_substring_beats_initials(self):
        self.assertGreater(ui.fuzzy_score("term", "Terminale"), ui.fuzzy_score("nt", "Nuova tab"))

    def test_initials(self):
        self.assertGreater(ui.fuzzy_score("nt", "Nuova tab"), 0)
        self.assertEqual(ui.fuzzy_score("xyz", "Nuova tab"), 0)

    def test_empty_query_matches_everything(self):
        self.assertEqual(ui.fuzzy_score("  ", "qualsiasi"), 1)


class DepsTest(unittest.TestCase):
    def test_nothing_missing_here(self):
        self.assertEqual(deps.missing(), [])

    def test_install_hint_lists_packages(self):
        hint = deps.install_hint([("WebKit2 4.1", ("gir1.2-webkit2-4.1", "webkit2gtk4.1", "webkit2gtk-4.1"))])
        self.assertTrue(any(name in hint for name in ("gir1.2-webkit2-4.1", "webkit2gtk4.1", "webkit2gtk-4.1")))


class FakeWindow:
    def __init__(self):
        self.opened = []

    def open_from_cli(self, text):
        self.opened.append(text)
        return ("https://" + text) if text else None

    def list_tabs(self):
        return [{"index": 1, "title": "T", "uri": "https://a.it/", "suspended": False, "current": True}]


class ControlTest(unittest.TestCase):
    def setUp(self):
        self.window = FakeWindow()
        self.server = ControlServer(self.window)

    def test_open(self):
        response = self.server._handle(json.dumps({"cmd": "open", "url": "a.it"}))
        self.assertEqual(response, {"ok": True, "url": "https://a.it"})
        self.assertEqual(self.window.opened, ["a.it"])

    def test_open_empty(self):
        self.assertFalse(self.server._handle(json.dumps({"cmd": "open"}))["ok"])

    def test_tabs(self):
        self.assertEqual(self.server._handle('{"cmd": "tabs"}')["tabs"][0]["uri"], "https://a.it/")

    def test_unusable_socket_path_is_not_fatal(self):
        self.server.path = "/" + "x" * 200 + ".sock"
        with self.assertLogs("shellrunner", "WARNING"):
            self.server.start()
        self.assertIsNone(self.server.service)
        self.server.stop()

    def test_bad_requests(self):
        for line in ("non json", "[]", '{"x": 1}', '{"cmd": "rm -rf"}'):
            self.assertFalse(self.server._handle(line)["ok"], line)


class PagesTest(unittest.TestCase):
    def test_about_lists_versions_and_escapes(self):
        page = about.render_about_page("/tmp/<config>.json")
        self.assertIn("WebKitGTK", page)
        self.assertIn("&lt;config&gt;", page)
        self.assertNotIn("$", page.replace("$$", ""))

    def test_welcome(self):
        self.assertIn("Ctrl+K", about.render_welcome_page())


if __name__ == "__main__":
    unittest.main()
