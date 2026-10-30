"""
Tests for installing and updating specloop: the package, the thin files a
project keeps (shims, hook scripts, skill stubs, the CLAUDE.md block), the
minimum version, and `specloop update`.

    python3 -m unittest discover tests
"""

import json
import re
import shutil
import os
import subprocess
import sys
import unittest
from pathlib import Path

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


OLD = "7da7cea"  # the specloop KTCatPokemon copied in last


def run_cli(repo, *args):
    """This checkout's specloop, not the project's tools/specloop, which an
    old copied install replaces."""
    out = subprocess.run(["specloop", *args], cwd=repo.path, env=repo.env, capture_output=True, text=True)
    out.output = out.stdout + out.stderr
    return out


def old_file(path):
    return subprocess.run(["git", "-C", str(HERE), "show", f"{OLD}:{path}"], capture_output=True, text=True, check=True).stdout


class UpdateTests(SpecloopTestCase):
    def copied_install(self, repo):
        """The project as install.sh left it: full copies, no markers, no minVersion."""
        repo.write("tools/specloop", old_file("bin/specloop"))
        for hook in ("specloop-trigger", *project.HOOKS):
            repo.write(f"tools/githooks/{hook}", old_file(f"hooks/{hook}"))
        for name in project.SKILLS:
            repo.write(f".claude/skills/{name}/SKILL.md", old_file(f"skills/{name}/SKILL.md"))
        repo.write("CLAUDE.md", "# Project\n\n" + old_file("templates/CLAUDE.md"))
        repo.commit("copied install", SPEC_SYNC="off")

    def snapshot(self, repo, paths):
        return {p: (repo.path / p).read_bytes() for p in paths}

    def test_moves_copied_install_over(self):
        repo = self.repo()
        self.copied_install(repo)
        out = run_cli(repo, "update")
        self.assertEqual(out.returncode, 0, out.output)
        self.assertIn(project.SHIM_MARKER, (repo.path / "tools/specloop").read_text())
        self.assertFalse((repo.path / "tools/githooks/specloop-trigger").exists())
        for name in project.SKILLS:
            self.assertIn(project.STUB_MARKER, (repo.path / f".claude/skills/{name}/SKILL.md").read_text())
        claude = (repo.path / "CLAUDE.md").read_text()
        self.assertTrue(claude.startswith("# Project\n\n" + project.BEGIN))
        self.assertIn(project.RULES_HEADING, claude)
        self.assertEqual(json.loads((repo.path / "specloop.json").read_text())["minVersion"], "0.1.0")
        self.assertIn("Review and commit", out.stdout)

    def test_edited_skill_is_kept_as_fork(self):
        repo = self.repo()
        self.copied_install(repo)
        skill = repo.path / ".claude/skills/spec-sync/SKILL.md"
        skill.write_text(skill.read_text() + "\nLocal rule.\n")
        out = run_cli(repo, "update")
        self.assertIn("Local rule.", skill.read_text())
        self.assertIn("+Local rule.", out.stdout)  # diff from the packaged text to the local file
        self.assertIn("fork: .claude/skills/spec-sync/SKILL.md", run_cli(repo, "status").stdout)

    def test_unrecognized_cli_is_kept(self):
        repo = self.repo()
        repo.write("tools/specloop", "#!/bin/sh\necho mine\n")
        out = run_cli(repo, "update")
        self.assertEqual((repo.path / "tools/specloop").read_text(), "#!/bin/sh\necho mine\n")
        self.assertEqual(out.returncode, 1)
        self.assertIn("tools/specloop is edited here", out.stderr)

    def test_older_cli_refuses_to_update(self):
        repo = self.repo()
        self.copied_install(repo)
        config = json.loads((repo.path / "specloop.json").read_text())
        config["minVersion"] = "9.0.0"
        repo.write("specloop.json", json.dumps(config))
        paths = ["specloop.json", "tools/specloop", "CLAUDE.md", ".claude/skills/spec-sync/SKILL.md"]
        before = self.snapshot(repo, paths)
        out = run_cli(repo, "update")
        self.assertEqual(out.returncode, 1)
        self.assertIn("upgrade before updating", out.output)
        self.assertEqual(self.snapshot(repo, paths), before)

    def test_update_is_idempotent(self):
        repo = self.repo()
        run_cli(repo, "update")
        repo.commit("update", SPEC_SYNC="off")
        run_cli(repo, "update")
        self.assertEqual(repo.git("status", "--porcelain").stdout, "")

    def test_never_touches_project_state(self):
        repo = self.repo()
        repo.write("docs/signals/sig-1.json", '{"id": "sig-1"}\n')
        repo.write(".git/specloop/syncs/abc.json", '{"rev": "abc"}\n')
        claude = repo.path / "CLAUDE.md"
        claude.write_text("# Mine\n\n" + claude.read_text() + "\n## After\n\nkeep\n")
        paths = ["docs/SPEC.md", "docs/.spec-implemented", "docs/signals/sig-1.json", ".git/specloop/syncs/abc.json"]
        before = self.snapshot(repo, paths)
        outside = project.outside_block(claude.read_text())
        run_cli(repo, "update")
        self.assertEqual(self.snapshot(repo, paths), before)
        self.assertEqual(project.outside_block(claude.read_text()), outside)

    def test_keeps_unknown_config_keys(self):
        repo = self.repo()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["futureKey"] = {"a": 1}
        repo.write("specloop.json", json.dumps(config))
        run_cli(repo, "update")
        self.assertEqual(json.loads((repo.path / "specloop.json").read_text())["futureKey"], {"a": 1})

    def test_release_notes_since_old_min(self):
        self.assertIn("## 0.1.0", project.release_notes("0.0.0", "0.1.0"))
        self.assertEqual(project.release_notes("0.1.0", "0.1.0"), "")


class ConfigEditTests(SpecloopTestCase):
    def test_adds_min_version_without_reformatting(self):
        repo = self.repo()
        text = '{\n  "spec": "docs/SPEC.md",\n  "tests": {"paths": ["tests"], "tagStyles": ["pytest"]},\n  "sync": {"require": ["XP"]}\n}\n'
        repo.write("specloop.json", text)
        run_cli(repo, "update")
        self.assertEqual((repo.path / "specloop.json").read_text(), text.replace('{\n', '{\n  "minVersion": "0.1.0",\n', 1))

    def test_raises_min_version_in_place(self):
        repo = self.repo()
        repo.write("specloop.json", '{"minVersion": "0.0.9", "tests": {"paths": ["tests"]}}\n')
        run_cli(repo, "update")
        self.assertEqual((repo.path / "specloop.json").read_text(), '{"minVersion": "0.1.0", "tests": {"paths": ["tests"]}}\n')

    def test_one_line_config(self):
        repo = self.repo()
        repo.write("specloop.json", '{"tests": {"paths": ["tests"]}}\n')
        run_cli(repo, "update")
        config = json.loads((repo.path / "specloop.json").read_text())
        self.assertEqual(config, {"minVersion": "0.1.0", "tests": {"paths": ["tests"]}})


def harness_rev(repo):
    out = repo.run("trailers", "--none", "deps", "--model", "claude-opus-5-5").stdout
    return re.search(r"^Harness-Rev: (.*)$", out, re.M).group(1)


class HarnessRevTests(SpecloopTestCase):
    def test_names_version_and_not_the_stub(self):
        rev = harness_rev(self.repo())
        self.assertTrue(rev.startswith("specloop@0.1.0 "), rev)
        self.assertNotIn("spec-sync@", rev)
        self.assertRegex(rev, r"claude-md@[0-9a-f]{6}$")

    def test_claude_md_hash_covers_only_the_project_part(self):
        repo = self.repo()
        claude = repo.path / "CLAUDE.md"
        before = harness_rev(repo)
        claude.write_text(claude.read_text().replace(project.END, "- edited inside\n" + project.END))
        self.assertEqual(harness_rev(repo), before)
        claude.write_text(claude.read_text() + "\n- Project rule.\n")
        self.assertNotEqual(harness_rev(repo), before)

    def test_fork_is_named(self):
        repo = self.repo()
        repo.write(".claude/skills/spec-sync/SKILL.md", project.skill_text("spec-sync"))
        self.assertRegex(harness_rev(repo), r"^specloop@0\.1\.0 spec-sync@[0-9a-f]{6} ")


class ToleranceTests(SpecloopTestCase):
    """A teammate on an older specloop still writes records a newer one made."""

    def test_unknown_sync_field_survives(self):
        repo = self.repo()
        repo.spec_change()
        repo.run("sync", "running")
        [record_path] = (repo.path / ".git/specloop/syncs").glob("*.json")
        record = json.loads(record_path.read_text())
        record["fromTheFuture"] = 1
        record_path.write_text(json.dumps(record))
        repo.run("sync", "done")
        self.assertEqual(json.loads(record_path.read_text())["fromTheFuture"], 1)

    def test_unknown_signal_field_survives(self):
        repo = self.repo()
        repo.run("signal", "add", "--source", "qa", "--summary", "slow", "--rule", "XP-1")
        [path] = (repo.path / "docs/signals").glob("*.json")
        record = json.loads(path.read_text())
        record["fromTheFuture"] = 1
        path.write_text(json.dumps(record))
        repo.run("signal", "triage", record["id"], "--layer", "spec", "--kind", "ambiguous",
                 "--confidence", "low", "--reasoning", "r", "--confirm")
        record = json.loads(path.read_text())
        self.assertEqual(record["fromTheFuture"], 1)
        self.assertEqual(record["triage"]["layer"], "spec")

    def test_unknown_trailer_is_ignored(self):
        repo = self.repo()
        repo.write("app.py", "XP = 10\n")
        repo.commit("code\n\nSpec-Rules: XP-1\nSpec-Future: x\nHarness: human", SPEC_SYNC="off")
        out = repo.run("blame", "--commit", "HEAD")
        self.assertEqual(out.returncode, 0, out.output)
        self.assertIn("XP-1", out.stdout)


class CompatTests(SpecloopTestCase):
    """Every release reads every earlier release's projects. Each fixture is a
    project made by one release (scripts/make-fixture)."""

    def test_fixtures_still_read(self):
        fixtures = sorted((HERE / "tests" / "fixtures").glob("v*"))
        self.assertTrue(fixtures, "no fixtures; run scripts/make-fixture")
        env = {**os.environ, "PATH": f"{HERE / 'bin'}:{os.environ['PATH']}"}
        for fixture in fixtures:
            with self.subTest(fixture.name):
                path = self.tmp / fixture.name
                subprocess.run(["git", "clone", "-q", str(fixture / "repo.bundle"), str(path)], check=True)
                shutil.copytree(fixture / "state", path / ".git" / "specloop")
                for command in (["status"], ["check"], ["coverage"], ["pending"], ["signals", "--all"]):
                    out = subprocess.run(["specloop", *command], cwd=path, env=env, capture_output=True, text=True)
                    self.assertEqual(out.returncode, 0, f"{command}: {out.stdout}{out.stderr}")
                    self.assertNotIn("Traceback", out.stderr)


class UpgradeCommandTests(unittest.TestCase):
    def test_by_install_location(self):
        from specloop import cli
        cases = {
            "/opt/homebrew/Cellar/specloop/0.1.0/libexec/lib/python3.12/site-packages/specloop/cli.py": "brew upgrade specloop",
            "/Users/me/.local/pipx/venvs/specloop/lib/python3.12/site-packages/specloop/cli.py": "pipx upgrade specloop",
            "/Users/me/venv/lib/python3.9/site-packages/specloop/cli.py": "pip install --upgrade specloop",
        }
        for path, expected in cases.items():
            self.assertEqual(cli.upgrade_command(Path(path)), expected, path)
        self.assertEqual(cli.upgrade_command(HERE / "src/specloop/cli.py"), f"git pull in {HERE}")


class InstallScriptTests(SpecloopTestCase):
    def install(self, home, target):
        env = {**os.environ, "HOME": str(home), "PATH": "/usr/bin:/bin"}
        return subprocess.run(["sh", str(HERE / "install.sh"), str(target)], env=env, capture_output=True, text=True)

    def test_links_and_inits(self):
        home = self.tmp / "home"
        home.mkdir()
        target = fresh_git_repo(self.tmp / "app")
        out = self.install(home, target)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((home / ".local/bin/specloop").resolve(), (HERE / "bin/specloop").resolve())
        self.assertIn(project.SHIM_MARKER, (target / "tools/specloop").read_text())
        self.assertIn("isn't on your PATH", out.stdout + out.stderr)

    def test_replaces_an_old_link(self):
        home = self.tmp / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/specloop").symlink_to("/nonexistent/specloop")
        out = self.install(home, fresh_git_repo(self.tmp / "app"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((home / ".local/bin/specloop").resolve(), (HERE / "bin/specloop").resolve())

    def test_refuses_to_replace_a_real_file(self):
        home = self.tmp / "home"
        (home / ".local/bin").mkdir(parents=True)
        (home / ".local/bin/specloop").write_text("#!/bin/sh\n")
        out = self.install(home, fresh_git_repo(self.tmp / "app"))
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual((home / ".local/bin/specloop").read_text(), "#!/bin/sh\n")


class ReviewFixTests(SpecloopTestCase):
    copied_install = UpdateTests.copied_install

    def test_edited_copied_cli_changes_nothing_and_commits_still_work(self):
        repo = self.repo()
        self.copied_install(repo)
        cli = repo.path / "tools/specloop"
        cli.write_text(cli.read_text() + "# local tweak\n")
        repo.commit("tweak", SPEC_SYNC="off")
        out = run_cli(repo, "update")
        self.assertEqual(out.returncode, 1)
        self.assertIn("tools/specloop is edited here", out.output)
        self.assertEqual(repo.git("status", "--porcelain").stdout, "", "update changed nothing")
        repo.enable_hooks()
        repo.write("app.py", "x = 1\n")
        self.assertEqual(repo.commit("code\n\nSpec-Rules: none (deps)").returncode, 0)

    def test_commit_succeeds_when_tools_specloop_is_missing(self):
        repo = self.repo()
        repo.enable_hooks()
        (repo.path / "tools/specloop").unlink()
        repo.write("app.py", "x = 1\n")
        out = repo.commit("code", SPEC_SYNC="off")
        self.assertEqual(out.returncode, 0, out.output)


class OlderInitTests(SpecloopTestCase):
    def test_older_init_refuses_and_leaves_the_block(self):
        repo = self.repo()
        config = json.loads((repo.path / "specloop.json").read_text())
        config["minVersion"] = "9.0.0"
        repo.write("specloop.json", json.dumps(config))
        claude = repo.path / "CLAUDE.md"
        claude.write_text(claude.read_text().replace(project.END, "- from a newer specloop\n" + project.END))
        before = claude.read_text()
        out = run_cli(repo, "init")
        self.assertEqual(out.returncode, 1)
        self.assertIn("older than this project's minimum 9.0.0", out.stderr)
        self.assertEqual(claude.read_text(), before)


class NestedFieldTests(SpecloopTestCase):
    def test_nested_signal_fields_survive_triage_and_resolve(self):
        repo = self.repo()
        repo.run("signal", "add", "--source", "qa", "--summary", "slow", "--rule", "XP-1")
        [path] = (repo.path / "docs/signals").glob("*.json")
        record = json.loads(path.read_text())
        record["triage"] = {"future": 1}
        record["resolution"]["by"] = "someone"
        path.write_text(json.dumps(record))
        repo.run("signal", "triage", record["id"], "--layer", "spec", "--kind", "ambiguous",
                 "--confidence", "low", "--reasoning", "r")
        repo.run("signal", "resolve", record["id"], "--status", "wontfix")
        record = json.loads(path.read_text())
        self.assertEqual(record["triage"]["future"], 1)
        self.assertEqual(record["triage"]["layer"], "spec")
        self.assertEqual(record["resolution"]["by"], "someone")
        self.assertEqual(record["resolution"]["status"], "wontfix")


class PackageDataTests(unittest.TestCase):
    def test_globs_cover_every_data_file_without_recursive_globbing(self):
        # setuptools before 62.3 doesn't expand "**" in package-data, so each
        # pattern has to match a file one path segment at a time.
        import fnmatch
        text = (HERE / "pyproject.toml").read_text()
        patterns = re.findall(r'"(data/[^"]*)"', text.split("[tool.setuptools.package-data]")[1])
        self.assertTrue(patterns)
        root = HERE / "src" / "specloop"
        for path in (root / "data").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                rel = path.relative_to(root).parts
                matched = any(
                    len(p.split("/")) == len(rel) and all(fnmatch.fnmatch(a, b) for a, b in zip(rel, p.split("/")))
                    for p in patterns
                )
                self.assertTrue(matched, "/".join(rel))


class KeptDiffTests(SpecloopTestCase):
    copied_install = UpdateTests.copied_install

    def test_kept_skill_diff_shows_only_the_local_edit(self):
        repo = self.repo()
        self.copied_install(repo)
        skill = repo.path / ".claude/skills/spec-triage/SKILL.md"
        skill.write_text(skill.read_text() + "\nLocal rule.\n")
        out = run_cli(repo, "update").stdout
        diff = out.split("kept .claude/skills/spec-triage/SKILL.md", 1)[1].split("\nreplaced ", 1)[0]
        changed = [l for l in diff.splitlines() if l and l[0] in "+-" and not l.startswith(("+++", "---"))]
        self.assertEqual(changed, ["+", "+Local rule."])
        self.assertIn("as copied", diff)
