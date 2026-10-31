import os
import tempfile
import unittest

from devtox import navigation, onboarding
from devtox.config import Config


class SetupPageTest(unittest.TestCase):
    def setUp(self):
        self.config = Config(os.path.join(tempfile.mkdtemp(), "config.json"))
        self.applied = 0
        self.restarted = 0
        self.setup = onboarding.Setup(self.config, self._apply, self._restart)
        self.addCleanup(navigation.set_search_engine, navigation.DEFAULT_SEARCH_ENGINE)

    def _apply(self):
        self.applied += 1

    def _restart(self):
        self.restarted += 1

    def save(self, **fields):
        params = {"token": self.setup.token, "save": "1", "language": "it"}
        params.update(fields)
        return self.setup.render(params)

    def test_form_shows_current_values(self):
        page = self.setup.render({})
        self.assertIn(self.setup.token, page)
        self.assertIn('value="duckduckgo" checked', page)
        self.assertIn("5173, 3000, 8000, 4321", page)

    def test_tool_switches_need_restart(self):
        current = {field: "on" for field, keys, *_rest in onboarding.PRIVACY_SWITCHES
                   if all(self.config[k] for k in keys)}
        current.update({key: "on" for key, *_rest in onboarding.TOOL_SWITCHES if self.config[key]})
        current["server_alerts"] = "on"
        current.pop("docker_enabled")
        page = self.save(**current)
        self.assertTrue(self.config["server_alerts"])
        self.assertFalse(self.config["docker_enabled"])
        self.assertIn("restart=1", page)

    def test_wrong_token_changes_nothing(self):
        page = self.setup.render({"token": "falso", "save": "1", "search_engine": "google"})
        self.assertEqual(self.config["search_engine"], "duckduckgo")
        self.assertFalse(self.config["setup_done"])
        self.assertIn("<form", page)

    def test_save_without_restart_goes_to_welcome(self):
        current = {field: "on" for field, keys, *_rest in onboarding.PRIVACY_SWITCHES
                   if all(self.config[k] for k in keys)}
        current.update({key: "on" for key, *_rest in onboarding.TOOL_SWITCHES if self.config[key]})
        page = self.save(search_engine="startpage", dev_ports="9000; 9000, 3000", **current)
        self.assertIn("location.replace", page)
        self.assertIn(navigation.WELCOME_URL, page)
        self.assertEqual(self.config["search_engine"], "startpage")
        self.assertEqual(self.config["dev_ports"], [9000, 3000])
        self.assertTrue(self.config["setup_done"])
        self.assertEqual(self.applied, 1)
        self.assertTrue(navigation.search_url("x").startswith("https://www.startpage.com/"))

    def test_strict_privacy_needs_restart(self):
        page = self.save(https_only="on", fingerprint="on", ai_enabled="on")
        self.assertFalse(self.config["persistent_data"])
        self.assertFalse(self.config["history_enabled"])
        self.assertFalse(self.config["send_gpc"])
        self.assertIn("restart=1", page)
        self.setup.render({"token": self.setup.token, "restart": "1"})  # pianificato con idle_add

    def test_bad_values_are_ignored(self):
        self.save(search_engine="evil", language="klingon", dev_ports="80, 99999")
        self.assertEqual(self.config["search_engine"], "duckduckgo")
        self.assertEqual(self.config["language"], "")
        self.assertEqual(self.config["dev_ports"], [5173, 3000, 8000, 4321])

    def test_skip(self):
        page = self.setup.render({"token": self.setup.token, "skip": "1"})
        self.assertTrue(self.config["setup_done"])
        self.assertIn(navigation.WELCOME_URL, page)

    def test_parse_ports(self):
        self.assertEqual(onboarding.parse_ports(""), [])
        self.assertEqual(onboarding.parse_ports(" 1 ,2,,2"), [1, 2])
        self.assertIsNone(onboarding.parse_ports("0"))
        self.assertIsNone(onboarding.parse_ports("abc"))
        self.assertEqual(len(onboarding.parse_ports(",".join(str(p) for p in range(1, 100)))),
                         onboarding.MAX_DEV_PORTS)


class SearchEngineTest(unittest.TestCase):
    def tearDown(self):
        navigation.set_search_engine(navigation.DEFAULT_SEARCH_ENGINE)

    def test_engines(self):
        for name in navigation.SEARCH_ENGINES:
            navigation.set_search_engine(name)
            url = navigation.search_url("a b")
            self.assertTrue(navigation.is_search_url(url), name)
            self.assertIn("a+b", url)
        navigation.set_search_engine("non-esiste")
        self.assertIn("duckduckgo", navigation.search_url("x"))
        self.assertFalse(navigation.is_search_url("https://example.com/"))


if __name__ == "__main__":
    unittest.main()
