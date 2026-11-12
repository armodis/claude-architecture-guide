"""Offline tests for the design loop's cost report on open, closed and reopened runs, against a
made-up transcript."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
COST = os.path.join(HERE, "..", "..", "template", "claude-user", ".claude", "skills", "design-loop", "scripts", "cost.py")
TEMPLATE = os.path.join(HERE, "..", "..", "template", "claude-user", ".claude", "skills", "design-loop", "templates", "cost.md")
SID = "11111111-2222-3333-4444-555555555555"


def msg(ts, mid, out):
    return {"type": "assistant", "timestamp": ts, "sessionId": SID,
            "message": {"id": mid, "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                                  "output_tokens": out}}}


class CostReport(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        proj = os.path.join(self.home, ".claude", "projects", "-repo")
        os.makedirs(proj)
        with open(os.path.join(proj, SID + ".jsonl"), "w") as f:
            for m in (msg("2026-01-01T00:10:00Z", "a", 10), msg("2026-01-01T01:10:00Z", "b", 20),
                      msg("2026-01-01T02:10:00Z", "c", 40)):
                f.write(json.dumps(m) + "\n")
        self.run_dir = os.path.join(self.home, "run")
        os.makedirs(self.run_dir)
        shutil.copy(TEMPLATE, os.path.join(self.run_dir, "cost.md"))

    def cost(self, *args):
        env = dict(os.environ, HOME=self.home)
        return subprocess.run([sys.executable, COST, *args], capture_output=True, text=True, env=env)

    def mark(self, step, at):
        with open(os.path.join(self.run_dir, "cost-log.tsv"), "a") as f:
            f.write(f"{at}\t{step}\t{SID}\n")

    def report(self):
        r = self.cost("report", self.run_dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.run_dir, "cost.md")) as f:
            return f.read()

    def test_closed_run_reports_and_says_closed(self):
        self.mark("0-frame", "2026-01-01T00:00:00+00:00")
        self.mark("5-build", "2026-01-01T01:00:00+00:00")
        self.mark("closed", "2026-01-01T02:00:00+00:00")
        text = self.report()
        self.assertIn("Run closed 2026-01-01T02:00:00+00:00", text)
        self.assertIn("| 0-frame | claude-opus-5-5 | 1 | 0 | 0 | 10 |", text)
        self.assertIn("| 5-build | claude-opus-5-5 | 1 | 0 | 0 | 20 |", text, "usage after closed is not counted")

    def test_open_run_counts_the_last_step_to_now(self):
        self.mark("0-frame", "2026-01-01T00:00:00+00:00")
        text = self.report()
        self.assertIn("Run still open", text)
        self.assertIn("| 0-frame | claude-opus-5-5 | 3 | 0 | 0 | 70 |", text)

    def test_reopening_in_the_same_second_as_closed_reopens(self):
        self.mark("0-frame", "2026-01-01T00:00:00+00:00")
        self.mark("closed", "2026-01-01T02:00:00+00:00")
        self.mark("6-verify", "2026-01-01T02:00:00+00:00")
        text = self.report()
        self.assertIn("Run still open", text)
        self.assertIn("| 6-verify | claude-opus-5-5 | 1 | 0 | 0 | 40 |", text)

    def test_reopened_run_counts_the_new_step(self):
        self.mark("0-frame", "2026-01-01T00:00:00+00:00")
        self.mark("closed", "2026-01-01T01:00:00+00:00")
        self.mark("6-verify", "2026-01-01T02:00:00+00:00")
        text = self.report()
        self.assertIn("Run still open", text)
        self.assertIn("| 6-verify | claude-opus-5-5 | 1 | 0 | 0 | 40 |", text)


if __name__ == "__main__":
    unittest.main()
