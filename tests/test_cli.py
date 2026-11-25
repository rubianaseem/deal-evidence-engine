import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import agent
from dee.util import read_json


class CliTests(unittest.TestCase):
    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = agent.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_end_to_end_with_refusals(self):
        with tempfile.TemporaryDirectory() as t:
            o = str(Path(t) / "run")
            code, out, _ = self.call("run", "--out", o, "--as-of", "2026-11-25")
            self.assertEqual(code, 0)
            sha = read_json(Path(o) / "manifest.json")["plan_sha256"]
            code, _, err = self.call("execute", "--out", o, "--now", "2026-11-25T10:00:00Z", "--no-sleep")
            self.assertEqual(code, 2)
            self.assertIn("not approved", err)
            code, _, err = self.call("approve", "--out", o, "--sha256", sha, "--approver", "claude", "--now", "2026-11-25T10:00:00Z")
            self.assertEqual(code, 2)
            code, out, _ = self.call("approve", "--out", o, "--sha256", sha, "--approver", "revops-lead", "--now", "2026-11-25T10:00:00Z")
            self.assertEqual(code, 0)
            code, out, _ = self.call("execute", "--out", o, "--now", "2026-11-25T11:00:00Z", "--no-sleep")
            self.assertEqual(code, 0)
            self.assertIn("'held_not_approved': 6", out)
            code, out, _ = self.call("verify", "--out", o)
            self.assertIn("ok", out)

    def test_claude_flag_without_key_falls_back(self):
        import os
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as t:
                code, out, err = self.call("run", "--out", str(Path(t) / "r"), "--as-of", "2026-11-25", "--claude")
                self.assertEqual(code, 0)
                self.assertIn("extractor=rules", out)
                self.assertIn("ANTHROPIC_API_KEY", err)
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
