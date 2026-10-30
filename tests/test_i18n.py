import os
import subprocess
import sys
import tempfile
import unittest

from shellrunner import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import update_po  # noqa: E402


class CatalogTest(unittest.TestCase):
    def test_english_is_complete_and_placeholders_match(self):
        catalog = i18n.parse_po(os.path.join(i18n.LOCALE_DIR, "en.po"))
        self.assertEqual(update_po.problems(update_po.collect(), catalog), [])

    def test_parse_po_multiline_and_escapes(self):
        path = os.path.join(tempfile.mkdtemp(), "x.po")
        with open(path, "w", encoding="utf-8") as f:
            f.write('msgid ""\nmsgstr ""\n"Language: x\\n"\n\nmsgid ""\n"riga uno\\n"\n"riga \\"due\\""\n'
                    'msgstr "one\\ntwo"\n\nmsgid "vuota"\nmsgstr ""\n')
        self.assertEqual(i18n.parse_po(path), {'riga uno\nriga "due"': "one\ntwo"})


class LanguageTest(unittest.TestCase):
    def tearDown(self):
        i18n.setup("it")

    def test_switching(self):
        i18n.setup("en")
        self.assertEqual(i18n._("Nuova tab"), "New tab")
        self.assertEqual(i18n._("testo che non esiste"), "testo che non esiste")
        i18n.setup("it")
        self.assertEqual(i18n._("Nuova tab"), "Nuova tab")

    def test_unknown_language_falls_back_to_english(self):
        i18n.setup("xx")
        self.assertEqual(i18n.language, "en")

    def test_system_language(self):
        saved = {k: os.environ.pop(k, None) for k in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")}
        try:
            os.environ["LANG"] = "it_IT.UTF-8"
            self.assertEqual(i18n.system_language(), "it")
            os.environ["LANG"] = "de_DE.UTF-8"
            self.assertEqual(i18n.system_language(), "en")
            os.environ["LANG"] = "C.UTF-8"
            self.assertEqual(i18n.system_language(), "en")
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None)
                if value is not None:
                    os.environ[key] = value

    def test_resources_have_no_leftover_markers(self):
        from shellrunner import utils
        i18n.setup("en")
        for name in ("start.html", "https_error.html", "json_viewer.js", "info.html"):
            text = utils.read_resource(name)
            self.assertNotIn("{{", text.replace("`{${", ""), name)
        self.assertIn('lang="en"', utils.read_resource("start.html"))


class EnglishProcessTest(unittest.TestCase):
    """Un processo nuovo in inglese: le stringhe create all'import devono essere tradotte."""

    def test_module_constants_follow_language(self):
        env = dict(os.environ, LANGUAGE="en_US")
        code = ("from shellrunner import tabs, ui, about; "
                "print(tabs.DEFAULT_TITLE); print(ui.ShieldsPopover.SHIELDS[0][1]); "
                "print('Welcome to Shellrunner' in about.render_welcome_page())")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                             text=True, timeout=30)
        self.assertEqual(out.stdout.split(), ["New", "tab", "Block", "trackers", "True"], out.stderr)


if __name__ == "__main__":
    unittest.main()
