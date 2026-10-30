import json
import os
import tempfile
import unittest

from shellrunner.config import DEFAULTS, Config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "sub", "config.json")

    def write(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def test_first_run_writes_defaults(self):
        config = Config(self.path)
        self.assertTrue(config.first_run)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), DEFAULTS)
        self.assertFalse(Config(self.path).first_run)

    def test_user_values_override(self):
        self.write({"history_days": 7, "dev_ports": [9000]})
        config = Config(self.path)
        self.assertEqual(config["history_days"], 7)
        self.assertEqual(config["dev_ports"], [9000])
        self.assertEqual(config["https_only"], DEFAULTS["https_only"])

    def test_wrong_types_are_ignored(self):
        self.write({"history_days": "tanti", "https_only": 1})
        with self.assertLogs("shellrunner", "WARNING"):
            config = Config(self.path)
        self.assertEqual(config["history_days"], DEFAULTS["history_days"])
        self.assertIs(config["https_only"], DEFAULTS["https_only"])

    def test_broken_json_uses_defaults(self):
        self.write("{ non è json")
        with self.assertLogs("shellrunner", "WARNING"):
            config = Config(self.path)
        self.assertEqual(config["dev_ports"], DEFAULTS["dev_ports"])
        self.assertFalse(config.first_run)

    def test_set_persists(self):
        Config(self.path).set("shields_down_hosts", ["example.com"])
        self.assertEqual(Config(self.path)["shields_down_hosts"], ["example.com"])

    def test_defaults_not_shared(self):
        Config(self.path)["dev_ports"].append(1)
        self.assertNotIn(1, DEFAULTS["dev_ports"])


if __name__ == "__main__":
    unittest.main()
