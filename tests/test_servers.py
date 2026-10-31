"""Server locali letti da /proc: porte in ascolto, processo, progetto, strumento."""

import os
import tempfile
import unittest

from shellrunner import servers

UID = os.getuid()

# Due socket in ascolto dell'utente (5173 su 127.0.0.1, 8000 su 0.0.0.0),
# una connessione stabilita (stato 01) e un ascolto di un altro utente.
TCP = f"""  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1435 00000000:0000 0A 00000000:00000000 00:00000000 00000000  {UID}        0 1111 1
   1: 00000000:1F40 00000000:0000 0A 00000000:00000000 00:00000000 00000000  {UID}        0 2222 1
   2: 0100007F:1F41 0100007F:9C40 01 00000000:00000000 00:00000000 00000000  {UID}        0 3333 1
   3: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 4444 1
"""
# ::1 porta 3000 (0x0BB8)
TCP6 = f"""  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000001000000:0BB8 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000  {UID}        0 5555 1
"""


def make_proc(root):
    os.makedirs(os.path.join(root, "net"))
    with open(os.path.join(root, "net", "tcp"), "w") as f:
        f.write(TCP)
    with open(os.path.join(root, "net", "tcp6"), "w") as f:
        f.write(TCP6)
    with open(os.path.join(root, "stat"), "w") as f:
        f.write("cpu  1 2 3\nbtime 1000\n")
    home = os.path.expanduser("~")
    procs = {
        "101": ("node", ["node", "/srv/app/node_modules/.bin/vite", "--port", "5173"],
                os.path.join(home, "progetti", "sito"), "socket:[1111]"),
        "202": ("python3", ["python3", "-m", "http.server", "8000"], "/tmp/www", "socket:[2222]"),
        "303": ("next-server", ["next-server (v14.2.3)"], "/opt/shop", "socket:[5555]"),
    }
    for pid, (comm, argv, cwd, link) in procs.items():
        base = os.path.join(root, pid)
        os.makedirs(os.path.join(base, "fd"))
        with open(os.path.join(base, "comm"), "w") as f:
            f.write(comm + "\n")
        with open(os.path.join(base, "cmdline"), "wb") as f:
            f.write(b"\0".join(a.encode() for a in argv) + b"\0")
        # campo 22 (starttime) = 100 secondi dopo il boot, in tick
        with open(os.path.join(base, "stat"), "w") as f:
            f.write(f"{pid} ({comm}) S " + " ".join(["0"] * 18) + f" {100 * servers.CLOCK_TICKS} 0\n")
        os.symlink(cwd, os.path.join(base, "cwd"))
        os.symlink(link, os.path.join(base, "fd", "3"))
        os.symlink("/dev/null", os.path.join(base, "fd", "0"))
    os.makedirs(os.path.join(root, "self"))


class ParseTest(unittest.TestCase):
    def test_ipv4_and_ipv6_addresses(self):
        self.assertEqual(servers.parse_address("0100007F:1435"), ("127.0.0.1", 5173))
        self.assertEqual(servers.parse_address("00000000:1F40"), ("0.0.0.0", 8000))
        self.assertEqual(
            servers.parse_address("00000000000000000000000001000000:0BB8"), ("::1", 3000))

    def test_tool_from_command_line(self):
        cases = {
            ("node", "node /x/node_modules/.bin/vite --port 5173"): "vite",
            ("node", "node /x/node_modules/next/dist/bin/next dev"): "next",
            ("next-server", "next-server (v14.2.3)"): "next",
            ("python3", "python3 -m http.server 8000"): "http.server",
            ("python3", "python3 manage.py runserver"): "django",
            ("uvicorn", "/venv/bin/python /venv/bin/uvicorn main:app"): "uvicorn",
            ("ruby", "ruby bin/rails server"): "rails",
            ("php", "php -S localhost:8080"): "php",
            ("hugo", "hugo server"): "hugo",
            ("myserver", "./myserver --flag"): "myserver",
        }
        for (comm, cmdline), tool in cases.items():
            with self.subTest(cmdline=cmdline):
                self.assertEqual(servers.guess_tool(comm, cmdline.split()), tool)


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        make_proc(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_own_listeners_with_their_process(self):
        found = servers.scan(proc=self.tmp.name, now=1000 + 100 + 3600)
        self.assertEqual([s.port for s in found], [3000, 5173, 8000])
        vite = found[1]
        self.assertEqual(vite.tool, "vite")
        self.assertEqual(vite.pid, 101)
        self.assertEqual(vite.project, os.path.join("~", "progetti", "sito"))
        self.assertEqual(vite.uptime, 3600)
        self.assertEqual(vite.url, "http://localhost:5173/")
        self.assertEqual(found[0].tool, "next")
        self.assertEqual(found[2].tool, "http.server")

    def test_ignores_other_users_and_connections(self):
        ports = [s.port for s in servers.scan(proc=self.tmp.name)]
        self.assertNotIn(22, ports)      # di root
        self.assertNotIn(8001, ports)    # connessione, non ascolto

    def test_missing_proc_gives_nothing(self):
        self.assertEqual(servers.scan(proc=os.path.join(self.tmp.name, "nope")), [])


class FormatTest(unittest.TestCase):
    def test_uptime(self):
        self.assertEqual(servers.format_uptime(42), "42 s")
        self.assertEqual(servers.format_uptime(5 * 60 + 3), "5 min")
        self.assertEqual(servers.format_uptime(2 * 3600 + 14 * 60), "2 h 14 min")
        self.assertEqual(servers.format_uptime(3 * 86400 + 3600), "3 g 1 h")
        self.assertEqual(servers.format_uptime(None), "—")


if __name__ == "__main__":
    unittest.main()
