"""Anti-phishing: indice locale dei domini segnalati, aggiornamento, controllo delle navigazioni."""

import gzip
import io
import os
import tempfile
import unittest
from unittest import mock

from devtox import phishing

LIST = """# Phishing.Database
paypa1-login.example
secure-bank.example.com
Bad Line!
xn--pypal-4ve.example
"""


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.index = phishing.Index.build(phishing.parse_domains(LIST))

    def test_exact_and_subdomains(self):
        self.assertTrue(self.index.contains("paypa1-login.example"))
        self.assertTrue(self.index.contains("www.paypa1-login.example"))   # sottodominio
        self.assertTrue(self.index.contains("SECURE-BANK.example.com"))
        self.assertFalse(self.index.contains("example.com"))              # il genitore no
        self.assertFalse(self.index.contains("paypal.com"))
        self.assertEqual(len(self.index), 3)                              # la riga non valida è scartata

    def test_save_and_load(self):
        path = os.path.join(tempfile.mkdtemp(), "index.bin")
        self.index.save(path)
        loaded = phishing.Index.load(path)
        self.assertTrue(loaded.contains("paypa1-login.example"))
        self.assertEqual(len(loaded), 3)
        self.assertEqual(len(phishing.Index.load(path + ".manca")), 0)

    def test_merge(self):
        merged = self.index.merge(["new-scam.example"])
        self.assertTrue(merged.contains("new-scam.example"))
        self.assertTrue(merged.contains("paypa1-login.example"))


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.updater = phishing.Updater(self.folder)

    def fake_urlopen(self, calls):
        def urlopen(request, timeout):
            calls.append(request.full_url)
            if request.full_url == phishing.FULL_URL:
                if request.get_header("If-none-match") == '"v1"':
                    raise phishing.urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)
                return FakeResponse(gzip.compress(LIST.encode()), headers={"Content-Encoding": "gzip", "ETag": '"v1"'})
            return FakeResponse(b"new-today.example\n")
        return urlopen

    def test_first_update_downloads_both(self):
        calls = []
        with mock.patch.object(phishing.urllib.request, "urlopen", self.fake_urlopen(calls)):
            index = self.updater.update(now=1_000_000)
        self.assertEqual(calls, [phishing.FULL_URL, phishing.NEW_URL])
        self.assertTrue(index.contains("paypa1-login.example"))
        self.assertTrue(index.contains("new-today.example"))

    def test_daily_update_downloads_only_new_domains(self):
        calls = []
        with mock.patch.object(phishing.urllib.request, "urlopen", self.fake_urlopen(calls)):
            self.updater.update(now=1_000_000)
            calls.clear()
            self.assertIsNone(self.updater.update(now=1_000_000 + 3600))      # meno di un giorno: niente
            self.updater.update(now=1_000_000 + 2 * 86400)                    # il giorno dopo: solo i nuovi
            self.assertEqual(calls, [phishing.NEW_URL])
            calls.clear()
            self.updater.update(now=1_000_000 + 8 * 86400)                    # dopo una settimana: anche la lista
        self.assertEqual(calls, [phishing.FULL_URL, phishing.NEW_URL])         # completa, ma con ETag (304)

    def test_network_error_keeps_the_old_index(self):
        with mock.patch.object(phishing.urllib.request, "urlopen", self.fake_urlopen([])):
            self.updater.update(now=1_000_000)

        def broken(request, timeout):
            raise OSError("niente rete")
        with mock.patch.object(phishing.urllib.request, "urlopen", broken):
            self.assertIsNone(self.updater.update(now=1_000_000 + 8 * 86400))
        self.assertTrue(phishing.Index.load(self.updater.index_path).contains("paypa1-login.example"))


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.guard = phishing.Guard(lambda: True)
        self.guard.index = phishing.Index.build(["paypa1-login.example"])

    def test_blocks_listed_sites_only(self):
        self.assertIsNotNone(self.guard.blocked_page("https://www.paypa1-login.example/login"))
        self.assertIsNone(self.guard.blocked_page("https://paypal.com/"))
        self.assertIsNone(self.guard.blocked_page("devtox://start"))
        self.assertIsNone(self.guard.blocked_page("http://localhost:5173/"))

    def test_continue_anyway_needs_the_token_and_lasts_the_session(self):
        url = "https://paypa1-login.example/"
        self.assertIsNone(self.guard.allow({"token": "falso", "url": url}))
        self.assertIsNotNone(self.guard.blocked_page(url))
        self.assertEqual(self.guard.allow({"token": phishing.TOKEN, "url": url}), url)
        self.assertIsNone(self.guard.blocked_page(url))

    def test_disabled(self):
        guard = phishing.Guard(lambda: False)
        guard.index = phishing.Index.build(["paypa1-login.example"])
        self.assertIsNone(guard.blocked_page("https://paypa1-login.example/"))


if __name__ == "__main__":
    unittest.main()


class BlockedPageTest(unittest.TestCase):
    def test_warning_and_continue(self):
        guard = phishing.Guard(lambda: True)
        guard.index = phishing.Index.build(["paypa1-login.example"])
        url = "https://paypa1-login.example/<script>"
        page = phishing.render_blocked({"url": url}, guard)
        self.assertIn("paypa1-login.example", page)
        self.assertNotIn("<script>", page.split("<body>")[1])
        self.assertIn(f"token={phishing.TOKEN}", page)
        self.assertIsNotNone(guard.blocked_page(url))
        redirect = phishing.render_blocked({"continue": "1", "token": phishing.TOKEN, "url": url}, guard)
        self.assertIn("location.replace", redirect)
        self.assertNotIn("<script>\"", redirect)
        self.assertIsNone(guard.blocked_page(url))


class SharedHostsTest(unittest.TestCase):
    def test_platforms_are_never_blocked_whole(self):
        index = phishing.Index.build(phishing.parse_domains("sites.google.com\ndweb.link\nscam.vercel.app\n"))
        self.assertFalse(index.contains("sites.google.com"))
        self.assertFalse(index.contains("dweb.link"))
        self.assertFalse(index.contains("my-project.vercel.app"))
        self.assertTrue(index.contains("scam.vercel.app"))  # il singolo sottodominio segnalato sì
