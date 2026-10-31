"""Gestore password: origini, archivio (finto in memoria), import CSV dagli altri browser."""

import os
import tempfile
import unittest

from devtox import passwords


class OriginTest(unittest.TestCase):
    def test_only_secure_or_local_origins(self):
        self.assertEqual(passwords.origin_of("https://github.com/login?x=1"), "https://github.com")
        self.assertEqual(passwords.origin_of("https://Example.com:8443/a"), "https://example.com:8443")
        self.assertEqual(passwords.origin_of("http://localhost:5173/admin"), "http://localhost:5173")
        self.assertEqual(passwords.origin_of("http://127.0.0.1:8000/"), "http://127.0.0.1:8000")
        # Una password in chiaro su Internet non si compila né si salva
        self.assertIsNone(passwords.origin_of("http://example.com/login"))
        self.assertIsNone(passwords.origin_of("devtox://start"))
        self.assertIsNone(passwords.origin_of("file:///etc/passwd"))


class VaultTest(unittest.TestCase):
    def setUp(self):
        self.vault = passwords.Vault(passwords.MemoryBackend())

    def test_save_lookup_and_exact_origin(self):
        self.vault.save("https://github.com", "tommaso", "s3greta")
        self.vault.save("https://github.com", "lavoro", "altra")
        self.assertEqual(self.vault.usernames("https://github.com"), ["lavoro", "tommaso"])
        self.assertEqual(self.vault.password("https://github.com", "tommaso"), "s3greta")
        # Mai su un'origine diversa, nemmeno un sottodominio o lo schema http
        self.assertEqual(self.vault.usernames("https://gist.github.com"), [])
        self.assertEqual(self.vault.usernames("http://github.com"), [])

    def test_save_replaces_and_reports(self):
        self.assertEqual(self.vault.save("https://a.example", "u", "1"), "new")
        self.assertEqual(self.vault.save("https://a.example", "u", "1"), "same")
        self.assertEqual(self.vault.save("https://a.example", "u", "2"), "updated")
        self.assertEqual(self.vault.password("https://a.example", "u"), "2")

    def test_delete_and_list(self):
        self.vault.save("https://a.example", "u", "1")
        self.vault.save("http://localhost:3000", "admin", "admin")
        self.assertEqual(self.vault.entries(), [("http://localhost:3000", "admin"), ("https://a.example", "u")])
        self.vault.delete("https://a.example", "u")
        self.assertEqual(self.vault.entries(), [("http://localhost:3000", "admin")])


CHROME_CSV = """name,url,username,password,note
github.com,https://github.com/session,tommaso,"pa,ss""word",
localhost,http://localhost:5173/login,admin,admin,
insicuro,http://example.com/,u,p,
app,android://abc@com.app/,u,p,
"""
FIREFOX_CSV = """"url","username","password","httpRealm","formActionOrigin","guid","timeCreated","timeLastUsed","timePasswordChanged"
"https://accounts.example.com","me@example.com","fx-pass",,"https://accounts.example.com","{1}","1","1","1"
"""
BITWARDEN_CSV = """folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,login_password,login_totp
,,login,Mail,,,0,https://mail.example.org/,me,bw-pass,
,,note,Nota,,,0,,,,
"""


class CsvTest(unittest.TestCase):
    def write(self, text):
        path = os.path.join(tempfile.mkdtemp(), "passwords.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_chrome_opera_brave_edge(self):
        rows, skipped = passwords.read_csv(self.write(CHROME_CSV))
        self.assertEqual(rows, [("https://github.com", "tommaso", 'pa,ss"word'),
                                ("http://localhost:5173", "admin", "admin")])
        self.assertEqual(skipped, 2)  # http su Internet e app Android

    def test_firefox(self):
        rows, _skipped = passwords.read_csv(self.write(FIREFOX_CSV))
        self.assertEqual(rows, [("https://accounts.example.com", "me@example.com", "fx-pass")])

    def test_bitwarden(self):
        rows, _skipped = passwords.read_csv(self.write(BITWARDEN_CSV))
        self.assertEqual(rows, [("https://mail.example.org", "me", "bw-pass")])

    def test_not_a_password_file(self):
        with self.assertRaises(ValueError):
            passwords.read_csv(self.write("a,b,c\n1,2,3\n"))


if __name__ == "__main__":
    unittest.main()
