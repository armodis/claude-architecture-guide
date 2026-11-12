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


if __name__ == "__main__":
    unittest.main()
