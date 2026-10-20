"""Sync between two Macs, each a fake keychain, through one vault in a temp
folder standing in for iCloud Drive. Uses the real age from Homebrew; no real
keychain, no real iCloud. Run: python3 tests/test_sync.py"""
import importlib.machinery, importlib.util, io, json, os, shutil, sys, tempfile, unittest
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("envsecret", os.path.join(HERE, "..", "envsecret"))
spec = importlib.util.spec_from_loader("envsecret", loader)
E = importlib.util.module_from_spec(spec)
loader.exec_module(E)
E.SECURITY = os.path.join(HERE, "fake_security")
E.KEYCHAIN = "/fake/login.keychain-db"

SEED = {"BBB": {"label": "envsecret [flightr] BBB", "acct": "u", "value": "bbb-secret", "cdat": "20260902000000"},
        "CCC": {"label": "envsecret [flight] CCC", "acct": "u", "value": "ccc", "cdat": "20260903000000"}}


@unittest.skipUnless(any(os.access(os.path.join(d, "age"), os.X_OK) for d in E.AGE_DIRS),
                     "age is not installed")
class TwoMacs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="envsecret-sync-")
        self.vault = os.path.join(self.tmp, "icloud", "envsecret", "vault.age")
        E.VAULT = self.vault
        os.makedirs(os.path.join(self.tmp, "icloud"))
        os.environ["USER"] = E.ACCOUNT = "u"
        os.environ["FAKE_CLOCK"] = os.path.join(self.tmp, "clock")
        for mac, seed in (("a", SEED), ("b", {})):
            os.makedirs(os.path.join(self.tmp, mac))
            with open(os.path.join(self.tmp, mac, "store.json"), "w") as f:
                json.dump(seed, f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def on(self, mac):
        d = os.path.join(self.tmp, mac)
        os.environ["FAKE_STORE"] = os.path.join(d, "store.json")
        os.environ["FAKE_LOG"] = os.path.join(d, "calls.log")
        E.CONFIG = os.path.join(d, "envsecret", "config")

    def store(self, mac):
        with open(os.path.join(self.tmp, mac, "store.json")) as f:
            return {k: v for k, v in json.load(f).items() if k != E.KEY_SERVICE}

    def secrets(self, mac):
        return {k: (v["label"], v["value"]) for k, v in self.store(mac).items()}

    def writes(self, mac):
        try:
            with open(os.path.join(self.tmp, mac, "calls.log")) as f:
                return [l for l in f.read().splitlines() if l.startswith(("add", "delete"))]
        except OSError:
            return []

    def pair(self):
        """A sets up, B takes its key and pulls."""
        self.on("a")
        self.assertEqual(E.sync(setup=True), "sync set up, 2 out")
        key = E.vault_key()
        self.on("b")
        E.store_key(key)
        self.assertEqual(E.sync(), "2 in")
        return key

    def test_setup_and_first_pull(self):
        self.on("b")
        self.assertIsNone(E.sync(), "no key and no vault: sync is off")
        os.rmdir(os.path.join(self.tmp, "icloud"))
        self.on("a")
        with self.assertRaisesRegex(E.SyncError, "iCloud Drive"):
            E.sync(setup=True)
        os.makedirs(os.path.join(self.tmp, "icloud"))
        self.pair()
        self.assertEqual(self.secrets("a"), self.secrets("b"))
        with open(self.vault, "rb") as f:
            self.assertNotIn(b"bbb-secret", f.read())
        self.on("a")
        self.assertNotIn(E.KEY_SERVICE, [i.name for i in E.index()])

    def test_quiet_when_nothing_changed(self):
        self.pair()
        for mac in ("a", "b", "a", "b"):
            self.on(mac)
            open(os.environ["FAKE_LOG"], "w").close()
            self.assertEqual(E.sync(), "in sync")
            self.assertEqual(self.writes(mac), [], f"{mac} rewrote something")

    def test_edit_delete_regroup_travel(self):
        self.pair()
        self.on("b")
        self.assertIsNone(E.write_value("flightr", "BBB", "new-value", "n", replace=True))
        self.assertIsNone(E.write_value("ops", "DDD", "ddd", "n"))
        self.assertEqual(E.sync(), "2 out")
        self.on("a")
        self.assertEqual(E.sync(), "2 in")
        self.assertTrue(E.delete_value("CCC"))
        self.assertIsNone(E.write_value("ops2", "DDD", "ddd", "n", replace=True))
        self.assertEqual(E.sync(), "2 out")
        self.on("b")
        self.assertEqual(E.sync(), "2 in")
        self.assertEqual(self.secrets("a"), self.secrets("b"))
        self.assertEqual(self.secrets("b"), {"BBB": ("envsecret [flightr] BBB", "new-value"),
                                             "DDD": ("envsecret [ops2] DDD", "ddd")})

    def test_both_changed_newer_wins(self):
        self.pair()
        self.on("a")
        E.write_value("flightr", "BBB", "from-a", "n", replace=True)
        self.on("b")
        E.write_value("flightr", "BBB", "from-b", "n", replace=True)     # later
        self.on("a")
        self.assertEqual(E.sync(), "1 out")
        self.on("b")
        self.assertIn("kept the newer: BBB", E.sync())
        self.on("a")
        E.sync()
        self.assertEqual(self.store("a")["BBB"]["value"], "from-b")
        self.assertEqual(self.store("b")["BBB"]["value"], "from-b")

    def test_edit_beats_a_delete(self):
        self.pair()
        self.on("a")
        E.delete_value("BBB")
        self.on("b")
        E.write_value("flightr", "BBB", "edited", "n", replace=True)
        E.sync()
        self.on("a")
        E.sync()
        self.assertEqual(self.store("a")["BBB"]["value"], "edited")

    def test_lost_vault_costs_nothing(self):
        self.pair()
        os.remove(self.vault)
        self.on("b")
        self.assertEqual(E.sync(), "2 out")
        self.on("a")
        self.assertEqual(E.sync(), "in sync")
        self.assertEqual(self.secrets("a"), self.secrets("b"))
        self.assertEqual(len(self.secrets("a")), 2)

    def test_icloud_conflict_copy_is_merged_and_removed(self):
        self.pair()
        before = self.vault + ".before"
        shutil.copy(self.vault, before)
        self.on("b")
        E.write_value("ops", "EEE", "eee", "n")
        E.sync()
        # iCloud keeps the other Mac's write as a copy and the older one in place
        os.replace(self.vault, self.vault.replace("vault.age", "vault 2.age"))
        os.replace(before, self.vault)
        self.on("a")
        self.assertEqual(E.sync(), "1 in")
        self.assertEqual(self.store("a")["EEE"]["value"], "eee")
        self.assertEqual(E.vault_files(self.vault), [self.vault])

    def test_wrong_key_refused(self):
        self.pair()
        self.on("b")
        E.delete_value(E.KEY_SERVICE)
        E.store_key(E.new_key())
        with self.assertRaisesRegex(E.SyncError, "does not open"):
            E.sync()

    def test_no_key_but_a_vault_never_starts_a_new_one(self):
        self.pair()
        self.on("b")
        E.delete_value(E.KEY_SERVICE)
        with self.assertRaisesRegex(E.SyncError, "key-import"):
            E.sync(setup=True)
        # the same with the vault still only a stub in iCloud
        stub = os.path.join(os.path.dirname(self.vault), ".vault.age.icloud")
        os.replace(self.vault, stub)
        with self.assertRaisesRegex(E.SyncError, "key-import"):
            E.sync(setup=True)

    def test_bad_entries_never_reach_the_keychain(self):
        key = self.pair()
        entries = E.decrypt(self.vault, key)
        entries["bad name"] = dict(entries["BBB"], rev="x")
        entries["TABBY"] = dict(entries["BBB"], value="a\tb", rev="y")
        entries["GRP"] = dict(entries["BBB"], group="Bad Group", rev="z")
        E.encrypt(self.vault, entries, key)
        self.on("b")
        self.assertEqual(E.sync(), "in sync")
        self.assertEqual(set(self.secrets("b")), {"BBB", "CCC"})

    def test_key_import(self):
        self.on("a")
        E.sync(setup=True)
        key = E.vault_key()
        self.on("b")

        def feed(text):
            real, sys.stdin = sys.stdin, io.StringIO(text)
            try:
                return E.key_import()
            finally:
                sys.stdin = real

        self.assertIn("not an age key", feed("hello\n"))
        self.assertIn("does not open", feed(E.new_key() + "\n"))
        self.assertIsNone(E.vault_key(), "a key that fails is not kept")
        self.assertEqual(feed(key + "\n"), 0)
        self.assertEqual(E.vault_key(), key)
        self.assertEqual(feed(key + "\n"), 0)
        self.assertIn("different vault key", feed(E.new_key() + "\n"))
        self.assertEqual(E.vault_key(), key)


if __name__ == "__main__":
    unittest.main(verbosity=1)
