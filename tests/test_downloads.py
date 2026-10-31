"""Nomi dei file scaricati: decisi dal sito, quindi dati non fidati."""

import os
import tempfile
import unittest

from devtox.downloads import safe_filename, unique_path


class SafeFilenameTest(unittest.TestCase):
    def test_paths_and_hidden_files(self):
        self.assertEqual(safe_filename("../../.bashrc"), "bashrc")
        self.assertEqual(safe_filename("C:\\Windows\\evil.exe"), "evil.exe")
        self.assertEqual(safe_filename("..."), "download")
        self.assertEqual(safe_filename(""), "download")

    def test_control_characters_removed(self):
        self.assertEqual(safe_filename("fattura\n2024\r.pdf"), "fattura2024.pdf")
        self.assertEqual(safe_filename("a\x00b\x1b.txt"), "ab.txt")

    def test_long_names_fit_the_filesystem_and_keep_extension(self):
        name = safe_filename("è" * 300 + ".tar.gz")
        self.assertLessEqual(len(name.encode()), 255)
        self.assertTrue(name.endswith(".gz"))

    def test_unique_path_never_overwrites(self):
        folder = tempfile.mkdtemp()
        open(os.path.join(folder, "a.txt"), "w").close()
        self.assertEqual(os.path.basename(unique_path(folder, "a.txt")), "a (1).txt")


if __name__ == "__main__":
    unittest.main()
