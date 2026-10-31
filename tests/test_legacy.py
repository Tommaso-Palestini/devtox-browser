"""Dal nome vecchio (Shellrunner) a Devtox: il profilo si sposta, niente va perso."""

import os
import tempfile
import unittest

from devtox import legacy


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.env = {name: os.path.join(self.root, name.lower()) for name in legacy.XDG_DEFAULTS}

    def make(self, var, name, files):
        folder = os.path.join(self.env[var], name)
        for path, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(folder, path)), exist_ok=True)
            with open(os.path.join(folder, path), "w") as f:
                f.write(text)
        return folder

    def test_moves_every_old_folder(self):
        self.make("XDG_CONFIG_HOME", "shellrunner", {"config.json": "{}"})
        self.make("XDG_DATA_HOME", "shellrunner", {"shellrunner.sqlite": "db"})
        self.make("XDG_CACHE_HOME", "shellrunner", {"webext/libsrprivacy.so": "x", "filters/a": "f"})
        moved = legacy.migrate(self.env)
        self.assertEqual(len(moved), 3)
        config = os.path.join(self.env["XDG_CONFIG_HOME"], "devtox")
        data = os.path.join(self.env["XDG_DATA_HOME"], "devtox")
        cache = os.path.join(self.env["XDG_CACHE_HOME"], "devtox")
        self.assertTrue(os.path.exists(os.path.join(config, "config.json")))
        # Il database prende il nome nuovo, il resto resta com'è
        self.assertTrue(os.path.exists(os.path.join(data, "devtox.sqlite")))
        self.assertFalse(os.path.exists(os.path.join(self.env["XDG_DATA_HOME"], "shellrunner")))
        # La vecchia estensione C non deve restare: WebKit carica ogni .so della cartella
        self.assertFalse(os.path.exists(os.path.join(cache, "webext", "libsrprivacy.so")))
        self.assertTrue(os.path.exists(os.path.join(cache, "filters", "a")))

    def test_never_overwrites_a_new_profile(self):
        self.make("XDG_CONFIG_HOME", "shellrunner", {"config.json": "vecchio"})
        new = self.make("XDG_CONFIG_HOME", "devtox", {"config.json": "nuovo"})
        self.assertEqual(legacy.migrate(self.env), [])
        with open(os.path.join(new, "config.json")) as f:
            self.assertEqual(f.read(), "nuovo")

    def test_nothing_to_do(self):
        self.assertEqual(legacy.migrate(self.env), [])

    def test_session_urls(self):
        self.assertEqual(legacy.session_uri("sr://start"), "devtox://start")
        self.assertEqual(legacy.session_uri("https://sr.example/"), "https://sr.example/")


if __name__ == "__main__":
    unittest.main()
