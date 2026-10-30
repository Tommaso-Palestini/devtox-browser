import os
import tempfile
import unittest

from shellrunner import privacy


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
        with self.assertLogs("shellrunner", "WARNING"):
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
