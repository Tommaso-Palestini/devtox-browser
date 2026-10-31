"""Indirizzi nel terminale: quelli che stampano i server di sviluppo diventano cliccabili."""

import re
import unittest

from devtox.terminal import URL_PATTERN

URL = re.compile(URL_PATTERN)


class UrlPatternTest(unittest.TestCase):
    def test_dev_server_banners(self):
        cases = {
            "  ➜  Local:   http://localhost:5173/": "http://localhost:5173/",
            "Starting development server at http://127.0.0.1:8000/": "http://127.0.0.1:8000/",
            "Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ...": "http://0.0.0.0:8000/",
            "- Local:        http://localhost:3000": "http://localhost:3000",
            "see https://vitejs.dev/config/.": "https://vitejs.dev/config/",
            "docs: <https://example.com/a?b=1&c=2>, ok": "https://example.com/a?b=1&c=2",
            "[http://[::1]:8080/path]": "http://[::1]:8080/path",
        }
        for line, url in cases.items():
            with self.subTest(line=line):
                self.assertEqual(URL.search(line).group(0), url)

    def test_no_false_positives(self):
        for line in ("http:// incomplete", "nothttp://x", "ftp://files.example"):
            with self.subTest(line=line):
                self.assertIsNone(URL.search(line))


if __name__ == "__main__":
    unittest.main()
