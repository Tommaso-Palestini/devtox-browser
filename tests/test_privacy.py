import os
import tempfile
import unittest

from devtox import privacy


class BlocklistTest(unittest.TestCase):
    def test_created_with_defaults_when_missing(self):
        path = os.path.join(tempfile.mkdtemp(), "nuova", "blocklist.txt")
        domains = privacy.load_blocklist(path)
        self.assertIn("doubleclick.net", domains)
        self.assertTrue(os.path.exists(path))

    def test_parsing(self):
        path = os.path.join(tempfile.mkdtemp(), "blocklist.txt")
        with open(path, "w") as f:
            f.write("# commento\nTracker.COM\n*.ads.example.org  # nota\n\nnon valido!\ntracker.com\n")
        with self.assertLogs("devtox", "WARNING"):
            domains = privacy.load_blocklist(path)
        self.assertEqual(domains, ["ads.example.org", "tracker.com"])


class RulesTest(unittest.TestCase):
    def test_https_rules_come_before_blocks(self):
        rules = privacy.build_rules(["tracker.com"], True, ["legacy.it"])
        kinds = [r["action"]["type"] for r in rules]
        self.assertEqual(kinds[0], "make-https")
        last_ignore = max(i for i, k in enumerate(kinds) if k == "ignore-previous-rules")
        first_block = kinds.index("block")
        self.assertLess(last_ignore, first_block)
        self.assertTrue(any("legacy" in r["trigger"]["url-filter"] for r in rules))

    def test_no_https_rules_when_disabled(self):
        rules = privacy.build_rules(["tracker.com"], False, [])
        self.assertNotIn("make-https", [r["action"]["type"] for r in rules])

    def test_shields_down_and_bad_hosts(self):
        rules = privacy.build_rules(["tracker.com"], True, ["bad host/"], ["news.it", "x\\y"])
        blocks = [r for r in rules if r["action"]["type"] == "block"]
        self.assertTrue(all(r["trigger"]["unless-domain"] == ["*news.it"] for r in blocks))
        self.assertFalse(any("bad host" in r["trigger"]["url-filter"] for r in rules))

    def test_ping_always_blocked(self):
        rules = privacy.build_rules([], False, [])
        self.assertEqual(rules[-1]["trigger"]["resource-type"], ["ping"])


if __name__ == "__main__":
    unittest.main()


class _Config(dict):
    def set(self, key, value):
        self[key] = value


class _Filter:
    def __init__(self):
        self.session_https_exceptions = set()

    def reload(self, on_done=None):
        if on_done:
            on_done()


class _View:
    def __init__(self):
        self.loaded = []

    def load_alternate_html(self, page, uri, base):
        self.loaded.append(uri)

    def load_uri(self, uri):
        self.loaded.append(uri)


class _Decision:
    def __init__(self, uri, gesture):
        self.uri, self.gesture, self.ignored = uri, gesture, False

    def get_navigation_action(self):
        return self

    def get_request(self):
        return self

    def get_uri(self):
        return self.uri

    def is_user_gesture(self):
        return self.gesture

    def ignore(self):
        self.ignored = True


class HttpsGuardTest(unittest.TestCase):
    """L'HTTP si accetta solo con un clic sulla pagina d'errore, nella stessa tab."""

    NAV = privacy.WebKit2.PolicyDecisionType.NAVIGATION_ACTION

    def setUp(self):
        self.config = _Config(https_only=True, https_exceptions=[])
        self.guard = privacy.HttpsGuard(self.config, _Filter(), lambda view: False)
        self.view = _View()
        # Richiesta in http, portata in https, che poi fallisce
        self.guard.on_decide_policy(self.view, _Decision("http://bank.example/", True), self.NAV)
        self.assertTrue(self.guard._offer_http(self.view, "https://bank.example/", "timeout"))

    def test_click_on_error_page_adds_exception(self):
        decision = _Decision("http://bank.example/", True)
        self.assertTrue(self.guard.on_decide_policy(self.view, decision, self.NAV))
        self.assertEqual(self.config["https_exceptions"], ["bank.example"])

    def test_script_navigation_is_not_consent(self):
        self.guard.on_decide_policy(self.view, _Decision("http://bank.example/", False), self.NAV)
        self.assertEqual(self.config["https_exceptions"], [])

    def test_other_tab_is_not_consent(self):
        self.guard.on_decide_policy(_View(), _Decision("http://bank.example/", True), self.NAV)
        self.assertEqual(self.config["https_exceptions"], [])


class SettingsTest(unittest.TestCase):
    def test_no_leaky_features(self):
        settings = privacy.create_settings()
        self.assertFalse(settings.get_enable_webrtc())
        self.assertFalse(settings.get_enable_media_stream())
