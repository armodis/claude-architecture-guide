"""Offline tests for preflight: its two-sided controls over throwaway repos, and its command line."""
import importlib.machinery
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "template", "claude-user", ".claude", "skills", "preflight", "scripts", "preflight.py")
loader = importlib.machinery.SourceFileLoader("preflight_under_test", SRC)
spec = importlib.util.spec_from_loader("preflight_under_test", loader)
pf = importlib.util.module_from_spec(spec)
loader.exec_module(pf)


class Controls(unittest.TestCase):
    def test_every_control_passes(self):
        lines = []
        self.assertEqual(pf.controls(out=lines.append), pf.CLEAR, "\n".join(lines))
        self.assertTrue(lines[-1].endswith("controls passed"))
        self.assertFalse([l for l in lines if l.startswith("FAIL")], "\n".join(lines))


class CommandLine(unittest.TestCase):
    def run_main(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pf.main(list(argv))
        return code, buf.getvalue()

    def test_an_unknown_flag_exits_2_with_the_usage(self):
        code, out = self.run_main("--bogus")
        self.assertEqual(code, pf.CANT)
        self.assertIn("preflight.py [PATH ...]", out)

    def test_help_exits_0(self):
        self.assertEqual(self.run_main("--help")[0], pf.CLEAR)

    def test_an_unreadable_config_exits_2(self):
        d = os.path.join(HERE, "..", "..")
        bad = os.path.join(self.tmp(), "boards.json")
        with open(bad, "w") as f:
            f.write("{not json")
        saved = pf.CONFIG_PATH
        pf.CONFIG_PATH = bad
        try:
            code, out = self.run_main(os.path.abspath(d))
        finally:
            pf.CONFIG_PATH = saved
        self.assertEqual(code, pf.CANT, out)

    def tmp(self):
        import tempfile, shutil
        t = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, t)
        return t


class ConfigShape(unittest.TestCase):
    def load(self, text, env=None):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "boards.json")
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
        return pf.load_section(path)

    def test_a_good_section_loads(self):
        sec = self.load('{"boards": {}, "preflight": {"repos": ["~/x"], "probes": [{"run": "true"}]}}')
        self.assertEqual(sec["repos"], ["~/x"])

    def test_no_section_is_empty(self):
        self.assertEqual(self.load('{"boards": {}}'), {})

    def test_malformed_sections_are_refused(self):
        for text in ('[]', '{"preflight": []}', '{"preflight": {"repos": "~/x"}}',
                     '{"preflight": {"probes": ["gh api user"]}}', '{"preflight": {"probes": [{"name": "x"}]}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_a_board_config_variable_naming_a_missing_file_is_refused(self):
        saved = os.environ.get("BOARD_CONFIG")
        os.environ["BOARD_CONFIG"] = "/nowhere/boards.json"
        try:
            with self.assertRaises(ValueError):
                pf.load_section("/nowhere/boards.json")
        finally:
            if saved is None:
                os.environ.pop("BOARD_CONFIG")
            else:
                os.environ["BOARD_CONFIG"] = saved


class Wording(unittest.TestCase):
    def test_describe(self):
        self.assertEqual(pf.describe(0, 0), "up to date with")
        self.assertEqual(pf.describe(2, 0), "2 ahead of")
        self.assertEqual(pf.describe(0, 1), "1 behind")
        self.assertEqual(pf.describe(2, 1), "2 ahead and 1 behind")


if __name__ == "__main__":
    unittest.main()
