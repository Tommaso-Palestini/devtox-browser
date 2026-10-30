import unittest

from shellrunner import navigation


class ResolveInputTest(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(navigation.resolve_input("   "))

    def test_full_urls_kept(self):
        for url in ("https://example.com/a?b=1", "http://localhost:3000", "sr://start", "about:blank"):
            self.assertEqual(navigation.resolve_input(url), url)

    def test_domains_get_https(self):
        self.assertEqual(navigation.resolve_input("example.com"), "https://example.com")
        self.assertEqual(navigation.resolve_input("docs.python.org/3/"), "https://docs.python.org/3/")

    def test_local_hosts_get_http(self):
        self.assertEqual(navigation.resolve_input("localhost:5173"), "http://localhost:5173")
        self.assertEqual(navigation.resolve_input("192.168.1.10:8000"), "http://192.168.1.10:8000")
        self.assertEqual(navigation.resolve_input("app.localhost"), "http://app.localhost")

    def test_public_ip_gets_https(self):
        self.assertEqual(navigation.resolve_input("1.1.1.1"), "https://1.1.1.1")

    def test_searches(self):
        for text in ("come si usa git rebase", "python", "localhost:notaport", "a..b"):
            self.assertTrue(navigation.resolve_input(text).startswith("https://duckduckgo.com/?q="), text)


class HostsTest(unittest.TestCase):
    def test_is_local_host(self):
        for host in ("localhost", "LOCALHOST", "x.localhost", "printer.local", "127.0.0.1", "10.0.0.2", "[::1]"):
            self.assertTrue(navigation.is_local_host(host), host)
        for host in ("example.com", "8.8.8.8", "localhost.example.com"):
            self.assertFalse(navigation.is_local_host(host), host)

    def test_http_host(self):
        self.assertEqual(navigation.http_host("https://Example.com:8443/x"), "example.com")
        self.assertIsNone(navigation.http_host("sr://start"))
        self.assertIsNone(navigation.http_host(None))

    def test_display_uri(self):
        self.assertEqual(navigation.display_uri(navigation.START_URL), "")
        self.assertEqual(navigation.display_uri("https://a.it/"), "https://a.it/")


class GoPageTest(unittest.TestCase):
    def test_javascript_becomes_search(self):
        page = navigation._render_go({"q": "javascript:alert(1)"})
        self.assertIn("duckduckgo.com", page)
        self.assertNotIn('"javascript:', page)

    def test_script_cannot_break_out(self):
        page = navigation._render_go({"q": "</script><script>alert(1)</script>"})
        self.assertEqual(page.count("</script>"), 1)


if __name__ == "__main__":
    unittest.main()
