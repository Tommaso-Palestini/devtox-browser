"""Prova d'avvio reale: finestra, socket di sr, inoltro degli indirizzi, log pulito.

Apre una finestra vera, quindi è disattivata di default:
  SHELLRUNNER_GUI_TESTS=1 python -m unittest tests.test_gui
oppure scripts/check.sh, che la esegue dentro Xvfb.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = os.path.join(PROJECT, "bin", "sr")
STARTUP_SECONDS = 30


@unittest.skipUnless(os.environ.get("SHELLRUNNER_GUI_TESTS") == "1", "SHELLRUNNER_GUI_TESTS=1 per attivarla")
class StartupTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp(prefix="shellrunner-gui-")
        self.addCleanup(shutil.rmtree, root, True)
        self.env = dict(os.environ)
        self.env.pop("SHELLRUNNER_SOCKET", None)
        self.env.pop("WAYLAND_DISPLAY", None)  # sempre nello schermo X di Xvfb
        self.env["GDK_BACKEND"] = "x11"
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            path = os.path.join(root, name.lower())
            os.makedirs(path, mode=0o700)
            self.env[name] = path
        self.log = os.path.join(self.env["XDG_STATE_HOME"], "shellrunner", "shellrunner.log")

    def sr(self, *args):
        return subprocess.run([sys.executable, SR, *args], env=self.env, capture_output=True, text=True, timeout=10)

    def shellrunner(self, *args, **kwargs):
        return subprocess.Popen([sys.executable, "-m", "shellrunner", *args], cwd=PROJECT, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)

    def wait_for_socket(self, process):
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail("Shellrunner è uscito:\n" + process.stdout.read())
            result = self.sr("tabs")
            if result.returncode == 0:
                return result.stdout
            time.sleep(0.5)
        self.fail("il socket di sr non è comparso")

    @staticmethod
    def wait_for(condition, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(0.5)
        return False

    def test_first_start(self):
        browser = self.shellrunner()
        self.addCleanup(browser.wait, 10)
        self.addCleanup(browser.terminate)

        tabs = self.wait_for_socket(browser)
        self.assertIn("sr://setup", tabs)  # primo avvio: configurazione iniziale
        # Il titolo arriva quando la pagina è caricata: prova che sr://setup esiste davvero
        self.assertTrue(self.wait_for(lambda: "Personalizza Shellrunner" in self.sr("tabs").stdout))

        # Un secondo avvio con un indirizzo lo passa alla finestra già aperta ed esce
        second = self.shellrunner("sr://about")
        self.assertEqual(second.wait(15), 0)
        self.assertTrue(self.wait_for(lambda: "sr://about" in self.sr("tabs").stdout))

        mem = self.sr("mem")
        self.assertEqual(mem.returncode, 0, mem.stderr)

        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertIn("avviato", log)
        self.assertNotIn("Traceback", log)
        self.assertNotIn("ERROR", log)

        config = os.path.join(self.env["XDG_CONFIG_HOME"], "shellrunner", "config.json")
        with open(config, encoding="utf-8") as f:
            self.assertIn("https_only", json.load(f))


if __name__ == "__main__":
    unittest.main()
