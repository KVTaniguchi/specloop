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
import unittest

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


class ClaudeBlockTests(unittest.TestCase):
    def test_appends_block_and_rules_section(self):
        new, _ = project.apply_block("# My app\n")
        self.assertTrue(new.startswith("# My app\n"))
        self.assertIn(project.BEGIN, new)
        self.assertLess(new.index(project.END), new.index(project.RULES_HEADING))

    def test_keeps_an_existing_rules_section(self):
        new, _ = project.apply_block(f"# My app\n\n{project.RULES_HEADING}\n\n- Mine.\n")
        self.assertEqual(new.count(project.RULES_HEADING), 1)
        self.assertIn("- Mine.", new)

    def test_replaces_only_inside_markers(self):
        text = f"top\n{project.BEGIN}\nold\n{project.END}\nbottom\n"
        new, diff = project.apply_block(text)
        self.assertTrue(new.startswith("top\n") and new.endswith("bottom\n"))
        self.assertNotIn("\nold\n", new)
        self.assertIn("-old", diff)

    def test_migrates_pasted_section_keeping_project_rules(self):
        rules = f"{project.RULES_HEADING}\n\n- Never bump the build number.\n\n## Other\n\nkeep me\n"
        text = f"# App\n\n{project.PASTED_HEADING}\n\n- old bullet\n\n{rules}"
        new, diff = project.apply_block(text)
        self.assertTrue(new.endswith(rules))
        self.assertTrue(new.startswith("# App\n\n" + project.BEGIN))
        self.assertIn("-- old bullet", diff)

    def test_pasted_section_without_rules_ends_at_next_heading(self):
        text = f"{project.PASTED_HEADING}\n\n- old\n\n## Build\n\nmake\n"
        new, _ = project.apply_block(text)
        self.assertTrue(new.endswith("## Build\n\nmake\n"))

    def test_unchanged_block_has_no_diff(self):
        new, _ = project.apply_block("x\n")
        self.assertEqual(project.apply_block(new), (new, ""))

    def test_outside_block(self):
        new, _ = project.apply_block("top\n")
        self.assertNotIn(project.BEGIN, project.outside_block(new))
        self.assertTrue(project.outside_block(new).startswith("top\n"))


class InitBlockTests(SpecloopTestCase):
    def test_init_creates_claude_md(self):
        path = fresh_git_repo(self.tmp / "new")
        subprocess.run([str(HERE / "bin/specloop"), "init", str(path)], capture_output=True, check=True)
        self.assertIn(project.BEGIN, (path / "CLAUDE.md").read_text())
        self.assertFalse((path / "AGENTS.md").exists())

    def test_init_for_cursor_creates_agents_md(self):
        path = fresh_git_repo(self.tmp / "new")
        subprocess.run(["git", "-C", str(path), "config", "specloop.harness", "cursor"], check=True)
        subprocess.run([str(HERE / "bin/specloop"), "init", str(path)], capture_output=True, check=True)
        self.assertIn(project.BEGIN, (path / "AGENTS.md").read_text())
        self.assertFalse((path / "CLAUDE.md").exists())

    def test_init_adds_block_to_both_when_both_exist(self):
        path = fresh_git_repo(self.tmp / "both")
        (path / "CLAUDE.md").write_text("# C\n")
        (path / "AGENTS.md").write_text("# A\n")
        subprocess.run([str(HERE / "bin/specloop"), "init", str(path)], capture_output=True, check=True)
        for name, title in (("CLAUDE.md", "# C\n"), ("AGENTS.md", "# A\n")):
            text = (path / name).read_text()
            self.assertTrue(text.startswith(title))
            self.assertIn(project.BEGIN, text)


class MinVersionTests(SpecloopTestCase):
    def set_min(self, repo, value="9.0.0"):
        config = json.loads((repo.path / "specloop.json").read_text())
        if value is None:
            config.pop("minVersion", None)
        else:
            config["minVersion"] = value
        repo.write("specloop.json", json.dumps(config))
        repo.commit("min", SPEC_SYNC="off")

    def test_commands_warn_and_run(self):
        repo = self.repo()
        self.set_min(repo)
        out = repo.run("coverage")
        self.assertEqual(out.returncode, 0)
        self.assertIn("specloop 0.1.0 is older than this project's minimum 9.0.0", out.stderr)

    def test_status_leads_with_gap(self):
        repo = self.repo()
        self.set_min(repo)
        self.assertTrue(repo.run("status").stdout.startswith("specloop 0.1.0 is older than this project's minimum 9.0.0"))

    def test_spec_sync_skill_stops(self):
        repo = self.repo()
        self.set_min(repo)
        out = repo.run("skill", "spec-sync")
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("# Spec sync", out.stdout)
        self.assertIn('tools/specloop sync blocked --note "specloop 0.1.0 < 9.0.0;', out.stdout)

    def test_other_skills_warn_and_run(self):
        repo = self.repo()
        self.set_min(repo)
        out = repo.run("skill", "spec-triage")
        self.assertEqual(out.returncode, 0)
        self.assertIn("# Spec triage", out.stdout)
        self.assertIn("older than", out.stderr)

    def test_hook_starts_nothing_and_commit_succeeds(self):
        repo = self.repo()
        self.set_min(repo)
        repo.enable_hooks()
        repo.change_spec()
        out = repo.commit("raise scan XP")
        self.assertEqual(out.returncode, 0)
        self.assertIn("older than this project's minimum", out.output)
        self.assertEqual(repo.claude_calls(), [])
        self.assertEqual(repo.syncs(), [])

    def test_blocked_status_names_versions(self):
        repo = self.repo()
        repo.spec_change()
        repo.run("sync", "blocked", "--note", "specloop 0.1.0 < 9.0.0; brew upgrade specloop")
        self.assertIn("blocked: specloop 0.1.0 < 9.0.0", repo.run("status").stdout)

    def test_equal_or_missing_min_no_warning(self):
        repo = self.repo()
        self.set_min(repo, "0.1.0")
        self.assertNotIn("older", repo.run("coverage").stderr)
        self.set_min(repo, None)
        self.assertNotIn("older", repo.run("coverage").stderr)

    def test_malformed_min_warns_once(self):
        repo = self.repo()
        self.set_min(repo, "soon")
        out = repo.run("coverage")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stderr.count('minVersion "soon" in specloop.json isn\'t a version like 0.3.0'), 1)

    def test_parse_version(self):
        from specloop import cli
        self.assertEqual(cli.parse_version("0.10.2"), (0, 10, 2))
        self.assertGreater(cli.parse_version("0.10.0"), cli.parse_version("0.9.9"))
        with self.assertRaises(ValueError):
            cli.parse_version("1.2")
