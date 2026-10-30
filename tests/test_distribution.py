"""
Tests for installing and updating specloop: the package, the thin files a
project keeps (shims, hook scripts, skill stubs, the CLAUDE.md block), the
minimum version, and `specloop update`.

    python3 -m unittest discover tests
"""

import json
import os
import subprocess
import sys

from test_specloop import HERE, Repo, SpecloopTestCase

sys.path.insert(0, str(HERE / "src"))

from specloop import project  # noqa: E402

DATA = HERE / "src" / "specloop" / "data"


class VersionTests(SpecloopTestCase):
    def test_version(self):
        out = subprocess.run([str(HERE / "bin" / "specloop"), "--version"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "specloop 0.1.0")

    def test_package_data_present(self):
        for rel in ("skills/spec-sync/SKILL.md", "specloop-trigger", "claude-block.md", "templates/specloop.json"):
            self.assertTrue((DATA / rel).is_file(), rel)


class SkillTests(SpecloopTestCase):
    def test_skill_prints_versioned_text(self):
        out = self.repo().run("skill", "spec-sync")
        self.assertEqual(out.returncode, 0)
        self.assertTrue(out.stdout.startswith("<!-- specloop 0.1.0 -->\n"))
        self.assertIn("# Spec sync", out.stdout)

    def test_unknown_skill(self):
        self.assertEqual(self.repo().run("skill", "nope").returncode, 2)

    def test_stub_keeps_frontmatter_and_defers(self):
        stub = project.render_stub("spec-sync")
        full = (DATA / "skills" / "spec-sync" / "SKILL.md").read_text()
        self.assertTrue(stub.startswith(project.frontmatter(full)))
        self.assertIn("tools/specloop skill spec-sync", stub)
        self.assertIn(project.STUB_MARKER, stub)


def fresh_git_repo(path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    return path


def minimal_env(repo, home):
    """What a git GUI gives a hook: no Homebrew or pipx directories on PATH."""
    return {"PATH": "/usr/bin:/bin", "HOME": str(home)}


class ShimTests(SpecloopTestCase):
    def test_init_writes_thin_files(self):
        repo = self.repo()  # Repo runs init
        self.assertIn(project.SHIM_MARKER, (repo.path / "tools/specloop").read_text())
        for hook in project.HOOKS:
            self.assertIn(" hook ", (repo.path / "tools/githooks" / hook).read_text())
        for name in project.SKILLS:
            self.assertIn(project.STUB_MARKER, (repo.path / f".claude/skills/{name}/SKILL.md").read_text())

    def test_init_on_a_new_project_writes_config_and_spec(self):
        path = fresh_git_repo(self.tmp / "new")
        out = subprocess.run([str(HERE / "bin/specloop"), "init", str(path)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads((path / "specloop.json").read_text())["minVersion"], "0.1.0")
        self.assertTrue((path / "docs/spec/README.md").is_file())
        self.assertIn("core.hooksPath tools/githooks", out.stdout)

    def test_init_never_overwrites_config_or_spec(self):
        path = fresh_git_repo(self.tmp / "own")
        (path / "specloop.json").write_text('{"spec": "docs/SPEC.md", "tests": {"paths": ["t"]}}\n')
        (path / "docs").mkdir()
        (path / "docs/SPEC.md").write_text("# Mine\n")
        subprocess.run([str(HERE / "bin/specloop"), "init", str(path)], capture_output=True, check=True)
        self.assertEqual((path / "specloop.json").read_text(), '{"spec": "docs/SPEC.md", "tests": {"paths": ["t"]}}\n')
        self.assertEqual((path / "docs/SPEC.md").read_text(), "# Mine\n")
        self.assertFalse((path / "docs/spec").exists())

    def test_init_refuses_a_non_repo(self):
        (self.tmp / "plain").mkdir()
        out = subprocess.run([str(HERE / "bin/specloop"), "init", str(self.tmp / "plain")], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("is not a git repository", out.stderr)

    def test_hook_finds_cli_outside_path(self):
        repo = self.repo()
        repo.enable_hooks()
        home = self.tmp / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/specloop").symlink_to(HERE / "bin/specloop")
        repo.change_spec()
        repo.git("add", "-A")
        out = repo.git("commit", "-q", "-m", "raise scan XP", **minimal_env(repo, home)).output
        # The trigger ran: it got as far as looking for claude, which isn't on this PATH.
        self.assertIn("claude CLI not found", out)

    def test_commit_succeeds_without_cli(self):
        repo = self.repo()
        repo.enable_hooks()
        repo.change_spec()
        repo.git("add", "-A")
        out = repo.git("commit", "-q", "-m", "raise scan XP", check=False, **minimal_env(repo, self.tmp / "empty"))
        self.assertEqual(out.returncode, 0)
        self.assertIn("not installed", out.output)
        self.assertIn("skipping", out.output)

    def test_direct_shim_call_without_cli_fails(self):
        repo = self.repo()
        out = subprocess.run(
            [str(repo.path / "tools/specloop"), "status"], cwd=repo.path,
            env=minimal_env(repo, self.tmp / "empty"), capture_output=True, text=True,
        )
        self.assertEqual(out.returncode, 127)
        self.assertIn("brew install KVTaniguchi/tap/specloop", out.stderr)
