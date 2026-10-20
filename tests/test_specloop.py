"""
End-to-end tests for the specloop CLI and git hooks. Each test builds a
throwaway git repo with specloop installed, and a fake `claude` on PATH that
records how it was called.

    python3 -m unittest discover tests
"""

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

SPEC = """\
# Spec

## Rules

- **XP-1:** A scan pays 10 XP.
- **XP-2:** A relabel pays the scanner's XP.
"""

TESTS = """\
# Spec: XP-1
def test_scan(): pass

# Spec: XP-2
def test_relabel(): pass
"""


class Repo:
    def __init__(self, path, claude_exit=0, logged_in=True):
        self.path = path
        self.calls = path.parent / "claude-calls"
        self.launch_env = path.parent / "launch-env"
        self.session_pid = path.parent / "session-pid"
        bin_dir = path.parent / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        launch = (
            "echo 'Starting background service…'\necho 'backgrounded · 9c694670 · Spec sync'\n"
            if claude_exit == 0
            else "echo 'Workspace not trusted. Run `claude` here once.'\n"
        )
        fake.write_text(
            "#!/bin/sh\n"
            f'if [ "$1" = auth ]; then echo \'{{"loggedIn": {str(logged_in).lower()}}}\'; exit 0; fi\n'
            f'echo "$@" >> "{self.calls}"\n'
            f'if [ "$1" = stop ]; then [ -f "{self.session_pid}" ] && kill "$(cat "{self.session_pid}")"; exit 0; fi\n'
            'if [ "$1" = rm ]; then exit 0; fi\n'
            f"env | grep '^GIT_' >> \"{self.launch_env}\"\n"
            f"{launch}exit {claude_exit}\n"
        )
        fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
        self.env.pop("SPEC_SYNC", None)

        path.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        (path / "tools" / "githooks").mkdir(parents=True)
        shutil.copy(HERE / "bin" / "specloop", path / "tools" / "specloop")
        for hook in ("specloop-trigger", "post-commit", "post-merge", "post-rewrite"):
            shutil.copy(HERE / "hooks" / hook, path / "tools" / "githooks" / hook)
        self.write("specloop.json", json.dumps({"tests": {"paths": ["tests"]}, "sync": {"require": ["XP"]}}))
        self.write("docs/SPEC.md", SPEC)
        self.write("tests/test_rules.py", TESTS)
        self.commit("baseline", SPEC_SYNC="off")
        self.run("mark")
        self.commit("ledger")

    def git(self, *args, check=True, **env):
        result = subprocess.run(
            ["git", *args], cwd=self.path, env={**self.env, **env}, capture_output=True, text=True, check=check
        )
        result.output = result.stdout + result.stderr  # git sends hook output to stderr
        return result

    def run(self, *args):
        result = subprocess.run(
            [str(self.path / "tools" / "specloop"), *args], cwd=self.path, env=self.env, capture_output=True, text=True
        )
        result.output = result.stdout + result.stderr
        return result

    def write(self, name, text):
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, message, **env):
        self.git("add", "-A")
        return self.git("commit", "-q", "-m", message, **env)

    def run_in(self, path, *args):
        result = subprocess.run(
            [str(path / "tools" / "specloop"), *args], cwd=path, env=self.env, capture_output=True, text=True
        )
        result.output = result.stdout + result.stderr
        return result

    def add_worktree(self, rev, branch, lock_pid=None, reason=None):
        """A worktree named the way `claude --bg --worktree spec-sync-<sha>` names it."""
        short = self.git("rev-parse", "--short", rev).stdout.strip()
        path = self.path / ".claude" / "worktrees" / f"spec-sync-{short}"
        self.git("worktree", "add", "-q", "-b", branch, str(path), rev)
        if lock_pid or reason:
            reason = reason or f"claude session spec-sync-{short} (pid {lock_pid} start Tue Oct 20 21:01:40 2026)"
            self.git("worktree", "lock", "--reason", reason, str(path))
        return path, short

    def spec_change(self):
        """Commit a spec change without launching anything; returns its sha."""
        self.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        self.commit("raise scan XP", SPEC_SYNC="off")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def finished_sync(self, rev, session_id="abc12345", lock_pid=None):
        """A sync that built `rev` on its own branch and reported done."""
        path, short = self.add_worktree(rev, f"worktree-spec-sync-{rev[:7]}")
        self.git("-C", str(path), "branch", "-m", f"spec-sync/{short}")
        self.run_in(path, "sync", "running")
        self.run_in(path, "sync", "--session-id", session_id)
        (path / "app.py").write_text("XP = 12\n")
        self.run_in(path, "mark", "HEAD")
        self.git("-C", str(path), "add", "-A")
        self.git("-C", str(path), "commit", "-q", "-m", "Spec sync: raise scan XP", SPEC_SYNC="off")
        self.run_in(path, "sync", "done")
        if lock_pid:
            self.git("worktree", "lock", "--reason", f"claude session spec-sync-{short} (pid {lock_pid} start x)", str(path))
        return path, short

    def branches(self):
        return self.git("branch", "--format=%(refname:short)").stdout.split()

    def enable_hooks(self):
        self.git("config", "core.hooksPath", "tools/githooks")

    def claude_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def syncs(self):
        directory = self.path / ".git" / "specloop" / "syncs"
        return [json.loads(p.read_text()) for p in directory.glob("*.json")] if directory.exists() else []


class SpecloopTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def repo(self, **kwargs):
        return Repo(self.tmp / "project", **kwargs)


class CheckTests(SpecloopTestCase):
    def test_clean_project_passes(self):
        result = self.repo().run("check")
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn("0 errors, 0 warnings", result.output)

    def test_duplicate_id_fails(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC + "- **XP-1:** Also something else.\n")
        result = repo.run("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/SPEC.md:7: XP-1 is defined more than once (first at line 5)", result.output)

    def test_reused_id_with_new_meaning_fails(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("- **XP-2:** A relabel pays the scanner's XP.\n", ""))
        repo.write("tests/test_rules.py", TESTS.split("# Spec: XP-2")[0])
        repo.commit("drop XP-2", SPEC_SYNC="off")
        repo.write("docs/SPEC.md", SPEC.replace("pays the scanner's XP", "costs 5 XP"))
        result = repo.run("check", "--allow-pending")
        self.assertEqual(result.returncode, 1, result.output)
        self.assertIn("XP-2 was removed in", result.output)
        self.assertIn("defined again in the working tree", result.output)

    def test_restored_id_with_same_text_passes(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("- **XP-2:** A relabel pays the scanner's XP.\n", ""))
        repo.commit("drop XP-2", SPEC_SYNC="off")
        repo.write("docs/SPEC.md", SPEC)
        repo.commit("revert", SPEC_SYNC="off")
        result = repo.run("check")
        self.assertEqual(result.returncode, 0, result.output)

    def test_allow_reused_config(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("- **XP-2:** A relabel pays the scanner's XP.\n", ""))
        repo.commit("drop XP-2", SPEC_SYNC="off")
        repo.write("docs/SPEC.md", SPEC.replace("pays the scanner's XP", "costs 5 XP"))
        repo.write(
            "specloop.json",
            json.dumps({"tests": {"paths": ["tests"]}, "check": {"allowReused": ["XP-2"]}}),
        )
        self.assertNotIn("XP-2 was removed", repo.run("check", "--allow-pending").output)

    def test_stale_tag_fails_with_github_annotation(self):
        repo = self.repo()
        repo.write("tests/test_rules.py", TESTS + "\n# Spec: XP-9\ndef test_gone(): pass\n")
        result = repo.run("check", "--format", "github")
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error file=tests/test_rules.py,line=7::Test names XP-9", result.output)

    def test_required_prefix_uncovered_fails(self):
        repo = self.repo()
        repo.write("tests/test_rules.py", TESTS.split("# Spec: XP-2")[0])
        result = repo.run("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("XP-2 has no test", result.output)

    def test_pending_spec_fails_unless_allowed(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP", SPEC_SYNC="off")
        result = repo.run("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("(XP-1) and the code hasn't caught up", result.output)
        self.assertEqual(repo.run("check", "--allow-pending").returncode, 0)

    def test_ledger_naming_missing_commit(self):
        repo = self.repo()
        repo.write("docs/.spec-implemented", "0123456789abcdef0123456789abcdef01234567\n")
        result = repo.run("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("isn't a commit in this clone", result.output)
        pending = repo.run("pending")
        self.assertIn("isn't a commit in this clone", pending.output)
        self.assertNotIn("git diff", pending.output)


class TriggerTests(SpecloopTestCase):
    def test_spec_commit_triggers_and_other_commits_dont(self):
        repo = self.repo()
        repo.write("README.md", "hi")
        repo.commit("docs")
        self.assertEqual(repo.run("trigger").returncode, 1)
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        self.assertEqual(repo.run("trigger").returncode, 0)

    def test_already_implemented_doesnt_trigger(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.run("mark")
        repo.commit("ledger")
        result = repo.run("trigger", "--since", "HEAD~2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already implemented", result.output)

    def test_running_sync_blocks_a_second_one(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.run("sync", "running")
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "14 XP"))
        repo.commit("raise it again")
        result = repo.run("trigger")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is already running; not starting another", result.output)


class StatusTests(SpecloopTestCase):
    def pending_repo(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        return repo

    def line(self, repo):
        sha = repo.git("rev-parse", "--short", "main").stdout.strip()
        rows = [l for l in repo.run("status").stdout.splitlines() if l.strip().startswith(sha)]
        self.assertEqual(len(rows), 1, repo.run("status").stdout)
        return rows[0]

    def test_lifecycle(self):
        repo = self.pending_repo()
        self.assertIn("not started", self.line(repo))

        repo.run("sync", "starting", "--session", "Spec sync x")
        self.assertIn("starting", self.line(repo))

        sha = repo.git("rev-parse", "--short", "HEAD").stdout.strip()
        repo.git("checkout", "-q", "-b", f"spec-sync/{sha}")
        repo.run("sync", "running")
        self.assertIn(f"running          on spec-sync/{sha}", self.line(repo))
        repo.write("app.py", "XP = 12\n")
        repo.run("mark", "HEAD")
        repo.commit("Spec sync: raise scan XP")

        repo.run("sync", "done")
        repo.git("checkout", "-q", "main")
        self.assertIn(f"awaiting review  on spec-sync/{sha}", self.line(repo))

        repo.git("merge", "-q", f"spec-sync/{sha}")
        self.assertIn("pending:     nothing", repo.run("status").stdout)

    def test_blocked_shows_note(self):
        repo = self.pending_repo()
        repo.run("sync", "running")
        repo.run("sync", "blocked", "--note", "XP-1 contradicts XP-2")
        self.assertIn("blocked          XP-1 contradicts XP-2", self.line(repo))

    def test_quiet_sessions_are_flagged(self):
        repo = self.pending_repo()
        repo.run("sync", "starting", "--session-id", "fc372a90-b504-4450-a0ca-2bf0de5b093b")
        record_path = next((repo.path / ".git" / "specloop" / "syncs").glob("*.json"))
        record = json.loads(record_path.read_text())
        record["updated"] = "2020-01-01T00:00:00+00:00"
        record_path.write_text(json.dumps(record))
        self.assertIn("failed to start?", self.line(repo))
        self.assertIn("run `claude logs fc372a90`", self.line(repo))
        self.assertEqual(repo.run("trigger").returncode, 0, "a dead launch shouldn't block a new one")

        record["status"] = "running"
        record_path.write_text(json.dumps(record))
        self.assertIn("stalled?", self.line(repo))

    def test_older_revision_is_included_in_newer_sync(self):
        repo = self.pending_repo()
        older = repo.git("rev-parse", "--short", "HEAD").stdout.strip()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "14 XP"))
        repo.commit("again")
        repo.run("sync", "running")
        status = repo.run("status").stdout
        self.assertRegex(status, rf"{older}\s+included\s+in the sync of")


class SyncFieldTests(SpecloopTestCase):
    def test_field_update_keeps_status_and_time(self):
        repo = self.repo()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.run("sync", "running")
        [before] = repo.syncs()
        self.assertEqual(repo.run("sync", "--session-id", "9c694670").returncode, 0)
        [after] = repo.syncs()
        self.assertEqual((after["status"], after["updated"], after["sessionId"]), ("running", before["updated"], "9c694670"))

    def test_field_update_needs_a_record(self):
        result = self.repo().run("sync", "--session-id", "9c694670")
        self.assertEqual(result.returncode, 1)
        self.assertIn("No sync recorded", result.output)


def background_pid(command):
    """PID of a process that isn't our child, so it is reaped when it exits."""
    out = subprocess.run(["sh", "-c", f"{command} >/dev/null 2>&1 & echo $!"], capture_output=True, text=True)
    return int(out.stdout.strip())


class CleanupTests(SpecloopTestCase):
    def live_session(self, repo):
        pid = background_pid("sleep 60")
        self.addCleanup(lambda: subprocess.run(["kill", str(pid)], capture_output=True))
        repo.session_pid.write_text(str(pid))
        return pid

    def dead_pid(self):
        pid = background_pid("true")
        time.sleep(0.3)
        return pid

    def test_merge_cleans_up_the_finished_sync(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev, lock_pid=self.live_session(repo))
        repo.enable_hooks()
        out = repo.git("merge", "-q", f"spec-sync/{short}").output
        self.assertIn(f"removed .claude/worktrees/spec-sync-{short} (implemented; deleted spec-sync/{short})", out)
        self.assertFalse(path.exists())
        self.assertNotIn(f"spec-sync/{short}", repo.branches())
        self.assertEqual(repo.syncs(), [])
        self.assertEqual(repo.claude_calls(), ["stop abc12345", "rm abc12345"])

    def test_next_commit_cleans_up_a_merged_sync(self):
        # post-commit runs with GIT_INDEX_FILE=.git/index, which broke removal.
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev, lock_pid=self.dead_pid())
        repo.git("merge", "-q", f"spec-sync/{short}")
        repo.enable_hooks()
        repo.write("README.md", "hi")
        out = repo.commit("docs").output
        self.assertIn(f"removed .claude/worktrees/spec-sync-{short} (implemented; deleted spec-sync/{short})", out)
        self.assertFalse(path.exists())

    def test_awaiting_review_is_kept(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev, lock_pid=self.live_session(repo))
        self.assertEqual(repo.run("cleanup").output, "")
        self.assertTrue(path.exists())
        self.assertNotIn("worktrees:", repo.run("status").stdout)

    def test_dead_launch_is_cleaned_up(self):
        repo = self.repo()
        rev = repo.spec_change()
        repo.run("sync", "starting", "--session-id", "deadbeef")
        path, short = repo.add_worktree(rev, f"worktree-spec-sync-{rev[:7]}", lock_pid=self.dead_pid())
        self.assertIn("worktrees:   1 left over", repo.run("status").stdout)

        out = repo.run("cleanup").output
        self.assertIn(f"removed .claude/worktrees/spec-sync-{short} (ended without finishing; deleted worktree-spec-sync-", out)
        self.assertFalse(path.exists())
        self.assertEqual(repo.branches(), ["main"])
        self.assertEqual(repo.claude_calls(), ["rm deadbeef"])
        self.assertIn("failed           the session ended without reporting", repo.run("status").stdout)

    def test_dead_session_with_commits_keeps_its_branch(self):
        repo = self.repo()
        rev = repo.spec_change()
        repo.run("sync", "starting")
        path, short = repo.add_worktree(rev, f"spec-sync/{rev[:7]}", lock_pid=self.dead_pid())
        (path / "app.py").write_text("XP = 12\n")
        repo.git("-C", str(path), "add", "-A")
        repo.git("-C", str(path), "commit", "-q", "-m", "partial", SPEC_SYNC="off")
        out = repo.run("cleanup").output
        self.assertIn(f"kept spec-sync/{rev[:7]}, which has unmerged commits", out)
        self.assertFalse(path.exists())
        self.assertIn(f"spec-sync/{rev[:7]}", repo.branches())

    def test_running_session_is_kept(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.add_worktree(rev, f"spec-sync/{rev[:7]}", lock_pid=self.live_session(repo))
        repo.run_in(path, "sync", "running")
        self.assertEqual(repo.run("cleanup").output, "")
        self.assertTrue(path.exists())
        self.assertEqual(repo.claude_calls(), [])

    def test_uncommitted_changes_are_kept(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev)
        repo.git("merge", "-q", f"spec-sync/{short}")
        (path / "notes.txt").write_text("wip\n")
        self.assertIn("it has uncommitted changes", repo.run("cleanup").output)
        self.assertTrue(path.exists())

    def test_foreign_lock_is_kept(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev)
        repo.git("worktree", "lock", "--reason", "reviewing on the train", str(path))
        repo.git("merge", "-q", f"spec-sync/{short}")
        self.assertIn("locked (reviewing on the train)", repo.run("cleanup").output)
        self.assertTrue(path.exists())

    def test_dry_run_changes_nothing(self):
        repo = self.repo()
        rev = repo.spec_change()
        path, short = repo.finished_sync(rev)
        repo.git("merge", "-q", f"spec-sync/{short}")
        self.assertIn(f"would remove .claude/worktrees/spec-sync-{short} (implemented)", repo.run("cleanup", "--dry-run").output)
        self.assertTrue(path.exists())
        self.assertEqual(len(repo.syncs()), 1)

    def test_other_worktrees_are_ignored(self):
        repo = self.repo()
        path = repo.path.parent / "my-feature"
        repo.git("worktree", "add", "-q", "-b", "feature", str(path))
        repo.spec_change()
        repo.run("mark")
        repo.commit("ledger")
        self.assertEqual(repo.run("cleanup").output, "")
        self.assertTrue(path.exists())


class HookTests(SpecloopTestCase):
    def test_post_commit_launches_once_and_records_state(self):
        repo = self.repo()
        repo.enable_hooks()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        out = repo.commit("raise scan XP").output
        self.assertIn("started background session", out)
        self.assertEqual(len(repo.claude_calls()), 1)
        self.assertIn("--worktree spec-sync-", repo.claude_calls()[0])
        [record] = repo.syncs()
        self.assertEqual(record["status"], "starting")
        self.assertEqual(record["sessionId"], "9c694670")
        self.assertIn("claude attach 9c694670", out)

        leaked = [v for v in repo.launch_env.read_text().split() if v.split("=")[0] in (
            "GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")]
        self.assertEqual(leaked, [], "the session must not inherit the commit's git variables")
        self.assertEqual(repo.git("check-ignore", ".claude/worktrees/spec-sync-abc").returncode, 0)

        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "13 XP"))
        repo.git("add", "-A")
        out = repo.git("commit", "-q", "--amend", "-m", "raise scan XP").output
        self.assertIn("not starting another", out)
        self.assertEqual(len(repo.claude_calls()), 1)

    def test_launch_failure_is_recorded(self):
        repo = self.repo(claude_exit=1)
        repo.enable_hooks()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        self.assertIn("failed to start session: Workspace not trusted", repo.commit("raise scan XP").output)
        self.assertEqual([s["status"] for s in repo.syncs()], ["failed"])
        self.assertIn("failed           claude --bg failed: Workspace not trusted", repo.run("status").stdout)

    def test_logged_out_cli_fails_fast(self):
        repo = self.repo(logged_in=False)
        repo.enable_hooks()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        self.assertIn("isn't logged in", repo.commit("raise scan XP").output)
        self.assertEqual(repo.claude_calls(), [])
        self.assertIn("claude auth login", repo.run("status").stdout)

    def test_merge_brings_in_spec_change(self):
        repo = self.repo()
        repo.git("checkout", "-q", "-b", "laptop")
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.git("checkout", "-q", "main")
        repo.write("README.md", "hi")
        repo.commit("unrelated")
        repo.enable_hooks()
        out = repo.git("merge", "-q", "--no-edit", "laptop").output
        self.assertIn("started background session", out)
        self.assertEqual(len(repo.claude_calls()), 1)

    def test_fast_forward_pull_brings_in_spec_change(self):
        repo = self.repo()
        repo.git("checkout", "-q", "-b", "laptop")
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.git("checkout", "-q", "main")
        repo.enable_hooks()
        repo.git("merge", "-q", "--ff-only", "laptop")
        self.assertEqual(len(repo.claude_calls()), 1)

    def test_squash_merge_waits_for_its_commit(self):
        repo = self.repo()
        repo.git("checkout", "-q", "-b", "laptop")
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        repo.git("checkout", "-q", "main")
        repo.enable_hooks()
        repo.git("merge", "-q", "--squash", "laptop")
        self.assertEqual(repo.claude_calls(), [])
        repo.commit("squashed")
        self.assertEqual(len(repo.claude_calls()), 1)

    def test_rebase_onto_spec_change(self):
        repo = self.repo()
        repo.git("checkout", "-q", "-b", "feature")
        repo.write("app.py", "x = 1\n")
        repo.commit("feature work")
        repo.git("checkout", "-q", "main")
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP", SPEC_SYNC="off")
        repo.git("checkout", "-q", "feature")
        repo.enable_hooks()
        repo.git("rebase", "-q", "main")
        self.assertEqual(len(repo.claude_calls()), 1)

    def test_no_launch_from_sync_branch(self):
        repo = self.repo()
        repo.git("checkout", "-q", "-b", "spec-sync/abc")
        repo.enable_hooks()
        repo.write("docs/SPEC.md", SPEC.replace("10 XP", "12 XP"))
        repo.commit("raise scan XP")
        self.assertEqual(repo.claude_calls(), [])


if __name__ == "__main__":
    unittest.main()
