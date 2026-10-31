"""
Tests for `specloop doctor`: it checks a project's setup and says how to fix
what's wrong, and exits 1 only for problems that stop syncs from working.

    python3 -m unittest discover tests
"""

import json
import unittest

from test_specloop import Repo, SpecloopTestCase


class DoctorTests(SpecloopTestCase):
    def healthy(self, repo=None):
        """A project with everything set up: test command, trigger on, folder trusted."""
        repo = repo or self.repo()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["commands"] = {"test": "python3 -m unittest"}
        repo.write("specloop.json", json.dumps(config))
        repo.commit("test command", SPEC_SYNC="off")
        repo.enable_hooks()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.trust(repo.path)
        repo.env["HOME"] = str(self.home)
        return repo

    def trust(self, *paths):
        projects = {str(p.resolve()): {"hasTrustDialogAccepted": True} for p in paths}
        (self.home / ".claude.json").write_text(json.dumps({"projects": projects}))

    def line(self, out, name):
        """The doctor's line for one check."""
        return next((l for l in out.stdout.splitlines() if l[2:].startswith(name)), "")

    def test_healthy_project_passes(self):
        out = self.healthy().run("doctor")
        self.assertEqual(out.returncode, 0, out.output)
        for name in ("version", "config", "tests", "spec", "ledger", "files", "trigger", "claude", "trust"):
            self.assertTrue(self.line(out, name).startswith("✓"), f"{name}: {out.stdout}")

    def test_missing_test_command_fails(self):
        repo = self.healthy()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["commands"] = {"test": "<the exact command that runs your tests>"}
        repo.write("specloop.json", json.dumps(config))
        out = repo.run("doctor")
        self.assertEqual(out.returncode, 1)
        self.assertTrue(self.line(out, "config").startswith("✗"))
        self.assertIn("commands.test", out.stdout)

    def test_wrong_test_path_fails(self):
        repo = self.healthy()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["tests"] = {"paths": ["NoSuchTests"]}
        repo.write("specloop.json", json.dumps(config))
        out = repo.run("doctor")
        self.assertEqual(out.returncode, 1)
        self.assertTrue(self.line(out, "tests").startswith("✗"))
        self.assertIn("tests.paths", out.stdout)

    def test_logged_out_claude_fails_when_trigger_is_on(self):
        repo = Repo(self.tmp / "project", logged_in=False)
        out = self.healthy(repo).run("doctor")
        self.assertEqual(out.returncode, 1)
        self.assertTrue(self.line(out, "claude").startswith("✗"))
        self.assertIn("claude auth login", out.stdout)

    def test_absolute_hooks_path_counts_as_on(self):
        repo = self.healthy()
        repo.git("config", "core.hooksPath", str(repo.path / "tools" / "githooks"))
        self.assertTrue(self.line(repo.run("doctor"), "trigger").startswith("✓"))

    def test_trigger_off_is_reported_but_not_a_failure(self):
        repo = Repo(self.tmp / "project", logged_in=False)
        repo = self.healthy(repo)
        repo.git("config", "--unset", "core.hooksPath")
        out = repo.run("doctor")
        self.assertEqual(out.returncode, 0, out.output)
        self.assertIn("git config core.hooksPath tools/githooks", out.stdout)
        # Agent problems only matter once the trigger is on.
        self.assertTrue(self.line(out, "claude").startswith("!"))

    def test_untrusted_folder_warns(self):
        repo = self.healthy()
        self.trust(self.tmp / "elsewhere")
        out = repo.run("doctor")
        self.assertEqual(out.returncode, 0, out.output)
        self.assertTrue(self.line(out, "trust").startswith("!"))
        self.assertIn("accept", self.line(out, "trust") + out.stdout)

    def test_trusted_parent_folder_counts(self):
        repo = self.healthy()
        self.trust(self.tmp)
        self.assertTrue(self.line(repo.run("doctor"), "trust").startswith("✓"))

    def test_below_min_version_fails(self):
        repo = self.healthy()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["minVersion"] = "9.0.0"
        repo.write("specloop.json", json.dumps(config))
        out = repo.run("doctor")
        self.assertEqual(out.returncode, 1)
        self.assertTrue(self.line(out, "version").startswith("✗"))
        self.assertIn("older than this project's minimum 9.0.0", out.stdout)

    def test_outdated_project_files_warn(self):
        repo = self.healthy()
        shim = repo.path / "tools" / "specloop"
        shim.write_text(shim.read_text() + "# from an older specloop\n")
        out = repo.run("doctor")
        self.assertTrue(self.line(out, "files").startswith("!"))
        self.assertIn("specloop update", out.stdout)

    def test_missing_ledger_warns(self):
        repo = self.healthy()
        (repo.path / "docs" / ".spec-implemented").unlink()
        out = repo.run("doctor")
        self.assertTrue(self.line(out, "ledger").startswith("!"))
        self.assertIn("specloop mark", out.stdout)


if __name__ == "__main__":
    unittest.main()
