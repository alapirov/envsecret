"""Pure functions and the label contract. No keychain, no clipboard.
Run: python3 tests/test_units.py"""
import importlib.machinery, importlib.util, os, shlex, subprocess, sys, tempfile, unittest
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "envsecret")
loader = importlib.machinery.SourceFileLoader("envsecret", SCRIPT)
spec = importlib.util.spec_from_loader("envsecret", loader)
E = importlib.util.module_from_spec(spec)
loader.exec_module(E)

DUMP = '''keychain: "/k"
class: "genp"
attributes:
    0x00000007 <blob>="envsecret [cloudflare] CF_TOKEN"
    "cdat"<timedate>=0x3230  "20260902000000Z\\000"
keychain: "/k"
class: "genp"
attributes:
    0x00000007 <blob>="envsecret [ai] OPENAI_KEY"
    "cdat"<timedate>=0x3230  "20260901000000Z\\000"
keychain: "/k"
class: "genp"
attributes:
    0x00000007 <blob>="not envsecret"
    "cdat"<timedate>=0x3230  "20250101000000Z\\000"
keychain: "/k"
class: "genp"
attributes:
    0x00000007 <blob>="envsecret [ai] NO_STAMP"
keychain: "/k"
class: "genp"
attributes:
    0x00000007 <blob>="other app"
    "cdat"<timedate>=0x3230  "20240101000000Z\\000"
'''


def fake_run(stdout="", stderr="", returncode=0):
    return lambda *a, **k: type("R", (), {"stdout": stdout, "stderr": stderr,
                                          "returncode": returncode})


class Index(unittest.TestCase):
    def setUp(self):
        self.real = E.subprocess.run

    def tearDown(self):
        E.subprocess.run = self.real

    def test_pairs_label_with_its_own_cdat(self):
        E.subprocess.run = fake_run(DUMP)
        self.assertEqual([(i.group, i.name, i.added) for i in E.index("name")],
                         [("ai", "NO_STAMP", ""), ("ai", "OPENAI_KEY", "20260901000000"),
                          ("cloudflare", "CF_TOKEN", "20260902000000")])

    def test_sort_new_old(self):
        E.subprocess.run = fake_run(DUMP)
        self.assertEqual([i.name for i in E.index("new")], ["CF_TOKEN", "OPENAI_KEY", "NO_STAMP"])
        self.assertEqual([i.name for i in E.index("old")], ["NO_STAMP", "OPENAI_KEY", "CF_TOKEN"])

    def test_unreadable_keychain_is_none_not_empty(self):
        E.subprocess.run = fake_run("")          # what dump-keychain gives, with rc 0
        self.assertIsNone(E.index())


class ReadValue(unittest.TestCase):
    def setUp(self):
        self.real = E.subprocess.run

    def tearDown(self):
        E.subprocess.run = self.real

    def test_quoted_and_hex_forms(self):
        E.subprocess.run = fake_run(stderr='password: "plain value"\n')
        self.assertEqual(E.read_value("X"), "plain value")
        E.subprocess.run = fake_run(stderr='password: 0x7122625C73  "q"b\\134s"\n')
        self.assertEqual(E.read_value("X"), 'q"b\\s')
        E.subprocess.run = fake_run(stderr='password: 0x70C3A47373  "p\\303\\244ss"\n')
        self.assertEqual(E.read_value("X"), "päss")

    def test_missing(self):
        E.subprocess.run = fake_run(returncode=44)
        self.assertIsNone(E.read_value("X"))


class Rules(unittest.TestCase):
    def test_quote_round_trips_every_printable(self):
        text = "".join(map(chr, range(32, 127)))
        self.assertEqual(shlex.split(E.quote(text)), [text])

    def test_check(self):
        self.assertIsNone(E.check("cloudflare", "CF_TOKEN", "v", set()))
        for group in ("", "a]b", "a b", "Cloud", 'a"b'):
            self.assertEqual(E.check(group, "N", "v", set())[0], 0, group)
        self.assertEqual(E.check("g", "1A", "v", set())[0], 1)
        self.assertEqual(E.check("g", "N", "v", {"N"})[0], 1)
        self.assertEqual(E.check("g", "N", "", set())[0], 2)
        self.assertIsNone(E.check("g", "N", "", set(), keep_allowed=True))
        self.assertEqual(E.check("g", "N", "a\tb", set())[0], 2)
        self.assertEqual(E.check("g", "N", "päss", set())[0], 2)

    def test_write_refuses_before_running_anything(self):
        real = E.subprocess.run
        E.subprocess.run = lambda *a, **k: self.fail("security must not run")
        try:
            self.assertIn("plain ASCII", E.write_value("g", "N", "a\nb", "n"))
            self.assertIn("too long", E.write_value("g", "N", "x" * 4000, "n"))
        finally:
            E.subprocess.run = real

    def test_names(self):
        self.assertEqual(E.normalise_name(" my-key name "), "MY_KEY_NAME")
        self.assertEqual(E.normalise_group(" Cloudflare "), "cloudflare")
        self.assertEqual(E.day(""), "")

    def test_unknown_option(self):
        self.assertIsNone(E.unknown_option(["--list"]))
        self.assertIsNone(E.unknown_option(["--theme", "nord"]))
        self.assertIsNone(E.unknown_option(["--theme=nord"]))
        self.assertEqual(E.unknown_option(["--lsit"]), "--lsit")

    def test_tools_by_full_path(self):
        for tool in (E.SECURITY, E.OSASCRIPT, E.PBCOPY):
            self.assertTrue(tool.startswith("/usr/bin/"), tool)


class Config(unittest.TestCase):
    def test_roundtrip_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            E.CONFIG = os.path.join(d, "envsecret", "config")
            self.assertEqual(E.load_config(), {})
            self.assertTrue(E.save_setting("sort", "new"))
            with open(E.CONFIG, "a") as f:
                f.write("theme = nord  # trailing\n")
            self.assertEqual(E.load_config(), {"sort": "new", "theme": "nord"})


class ShellAgreement(unittest.TestCase):
    """The zsh helpers' parser and index() must list the same secrets."""
    def test_same_rows(self):
        zsh = subprocess.run(
            ["zsh", "-f", "-c",
             "grep -oE '0x00000007 <blob>=\"envsecret \\[[^]]+\\] [^\"]+\"'"
             " | sed -E 's/.*\"envsecret \\[([^]]+)\\] (.+)\"$/\\1 \\2/' | sort"],
            input=DUMP, capture_output=True, text=True).stdout.split()
        real = E.subprocess.run
        E.subprocess.run = fake_run(DUMP)
        try:
            py = [x for it in E.index() for x in (it.group, it.name)]
        finally:
            E.subprocess.run = real
        self.assertEqual(sorted(zip(zsh[::2], zsh[1::2])), sorted(zip(py[::2], py[1::2])))


if __name__ == "__main__":
    unittest.main(verbosity=1)
