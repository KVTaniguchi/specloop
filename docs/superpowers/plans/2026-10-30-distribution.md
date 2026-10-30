# Distribution and Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** specloop installs once per machine (Homebrew, pipx), a project commits only thin shims, stubs and a managed `CLAUDE.md` block that defer to the installed version, and `specloop update` moves a project forward in one reviewed commit.

**Architecture:** The CLI moves from `bin/specloop` into a Python package (`src/specloop/`) that carries the skill texts, the trigger script, the shim and stub templates and the `CLAUDE.md` block as package data. New commands `init`, `update`, `hook`, `skill` and `--version` write and serve those files. The existing trigger stays a shell script, shipped as package data and run by `specloop hook`; only its location changes.

**Tech Stack:** Python 3.8+ standard library only, POSIX `sh`, git, `unittest`, setuptools (`pyproject.toml`), Homebrew formula, GitHub composite action.

**Spec:** `docs/distribution.md`

## Global Constraints

- Python 3.8+, standard library only, as today. No `importlib.resources.files` (3.9+): find package data with `Path(__file__).resolve().parent / "data"`.
- Semantic versioning, first release `0.1.0`. Tags are `v0.1.0`.
- Package and command name: `specloop` (free on PyPI, checked 2026-10-30).
- Hooks never fail a git command because specloop is missing or old. They print one line and exit 0. The one exception is `commit-msg` refusing a commit with bad trailers, as today, when the CLI is present.
- Only `specloop init` and `specloop update` write project files.
- Every release reads every earlier project's files, and keeps unknown config keys, record fields and trailer keys when it rewrites a file.
- Below `minVersion`: commands warn on stderr and run; `specloop skill spec-sync` stops the sync; the hook starts nothing.
- Nothing outside specloop's markers in `CLAUDE.md` / `AGENTS.md` is ever changed.
- No network access from the CLI.
- `tools/specloop` keeps working as the command agents and docs use; skills keep saying `tools/specloop`.

## Review Focus

1. **A git GUI runs the hook with `PATH=/usr/bin:/bin`.** The shim must still find a pipx install in `~/.local/bin`, and a commit must succeed when nothing is found. Test: `ShimTests.test_hook_finds_cli_outside_path` and `test_commit_succeeds_without_cli` (Task 3).
2. **`specloop update` run by a version older than the project's `minVersion`.** It must refuse instead of downgrading shims, stubs and the block, and leave `minVersion` alone. Test: `UpdateTests.test_older_cli_refuses_to_update` (Task 6).
3. **A `CLAUDE.md` with the old pasted section plus the project's own rules under it.** Migration must keep "Spec sync rules for this project" and everything after it byte for byte. Test: `ClaudeBlockTests.test_migrates_pasted_section_keeping_project_rules` (Task 4).
4. **A locally edited skill file in a copied install.** `update` keeps it, prints a diff, and `status` keeps saying it's a fork. Test: `UpdateTests.test_edited_skill_is_kept_as_fork` (Task 6).
5. **A record written by a newer version** (an unknown field in a sync record, signal or `specloop.json`). Older code rewriting it must keep the field. Test: `ToleranceTests.test_unknown_fields_survive_rewrite` (Task 7).

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/specloop/__init__.py` | `__version__ = "0.1.0"` |
| `src/specloop/__main__.py` | `python -m specloop` → `cli.run()` |
| `src/specloop/cli.py` | Today's `bin/specloop`, plus the new commands' argument parsing and the version check |
| `src/specloop/project.py` | Writing project files: shims, stubs, the managed block, `minVersion`; recognizing old copies. Used by `init` and `update` |
| `src/specloop/data/skills/<name>/SKILL.md` | Full skill texts (moved from `skills/`) |
| `src/specloop/data/specloop-trigger` | The trigger script (moved from `hooks/`) |
| `src/specloop/data/shim.sh` | Template for `tools/specloop` |
| `src/specloop/data/hook.sh` | Template for each `tools/githooks/<hook>` |
| `src/specloop/data/stub.md` | Template for a skill stub |
| `src/specloop/data/claude-block.md` | The managed `CLAUDE.md` / `AGENTS.md` block (from `templates/CLAUDE.md`) |
| `src/specloop/data/templates/` | `specloop.json` and `spec/` templates (moved from `templates/`) |
| `src/specloop/data/known-copies.json` | Git blob hashes of every past version of each file `install.sh` copied, by kind |
| `src/specloop/data/CHANGELOG.md` | Copied from the root `CHANGELOG.md` at build; read by `update` |
| `bin/specloop` | Dev launcher: puts `src/` on `sys.path` and calls `cli.run()`. Resolves symlinks |
| `pyproject.toml` | Package metadata, entry point, package data |
| `CHANGELOG.md` | Release notes, `## 0.1.0` sections |
| `scripts/known-copies` | Regenerates `known-copies.json` from git history |
| `scripts/make-fixture` | Builds `tests/fixtures/v<version>/` from the current version |
| `scripts/release` | The release checklist as a script, run by the owner |
| `packaging/homebrew/specloop.rb` | Formula template for the `KVTaniguchi/homebrew-tap` repo |
| `action.yml` | GitHub composite action: install `specloop==<minVersion>` |
| `tests/test_specloop.py` | Existing suite; its `Repo` helper switches to `specloop init` |
| `tests/test_distribution.py` | New suite for this plan's commands |
| `tests/fixtures/v0.1.0/` | `repo.bundle` and `state/` (a `.git/specloop` tree) made by 0.1.0 |
| `install.sh` | Links this checkout's `bin/specloop` into `~/.local/bin`, then runs `specloop init` |

Delete after their content moves: `skills/`, `hooks/`, `templates/`.

---

### Task 1: Package layout and `--version`

**Files:**
- Create: `src/specloop/__init__.py`, `src/specloop/__main__.py`, `pyproject.toml`, `CHANGELOG.md`
- Move: `bin/specloop` → `src/specloop/cli.py`; `skills/*` → `src/specloop/data/skills/`; `hooks/specloop-trigger` → `src/specloop/data/specloop-trigger`; `templates/specloop.json`, `templates/spec/` → `src/specloop/data/templates/`; `templates/CLAUDE.md` → `src/specloop/data/claude-block.md`
- Create: `bin/specloop` (launcher)
- Modify: `tests/test_specloop.py` (`Repo.__init__`: copy paths)
- Test: `tests/test_distribution.py`

**Interfaces:**
- Produces: `specloop.__version__: str`; `specloop.cli.run() -> int` (today's `main()`, renamed); `specloop.cli.main_entry() -> None` (`sys.exit(run())`, the console-script entry point and what `bin/specloop` calls); `specloop.cli.DATA: Path` (the `data/` directory); `specloop --version` prints `specloop 0.1.0`.

- [ ] **Step 1: Write the failing test**

```python
class VersionTests(SpecloopTestCase):
    def test_version(self):
        out = subprocess.run([str(HERE / "bin" / "specloop"), "--version"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "specloop 0.1.0")

    def test_package_data_present(self):
        for rel in ("skills/spec-sync/SKILL.md", "specloop-trigger", "claude-block.md", "templates/specloop.json"):
            self.assertTrue((HERE / "src" / "specloop" / "data" / rel).is_file(), rel)
```

`tests/test_distribution.py` imports `SpecloopTestCase`, `Repo` and `HERE` from `test_specloop`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m unittest tests.test_distribution -v`
Expected: FAIL (`--version` unrecognized, data missing)

- [ ] **Step 3: Move the files with `git mv`, add `__version__`, `run()`, `--version` (argparse `action="version"`), and the launcher**

The launcher is `#!/usr/bin/env python3`, inserts `Path(__file__).resolve().parent.parent / "src"` into `sys.path[0]`, then `sys.exit(cli.run())`. `pyproject.toml`: setuptools, `src` layout, `requires-python = ">=3.8"`, `[project.scripts] specloop = "specloop.cli:main_entry"` where `main_entry()` is `sys.exit(run())`, and package data `data/**/*` (include the trigger as executable; `cli` runs it with `sh`, so the mode bit doesn't matter). In the `Repo` test helper, make `tools/specloop` a symlink to `HERE / "bin" / "specloop"` and copy the trigger from `src/specloop/data/`. `CHANGELOG.md` gets a `## 0.1.0` section listing this plan's user-facing changes.

- [ ] **Step 4: Run both suites**

Run: `python3 -m unittest discover tests`
Expected: all pass (the existing 90 plus 2)

- [ ] **Step 5: Commit**

Message `Package the CLI with its skills and templates as data`, trailers `Spec-Rules: none (specloop itself has no spec)` and `Harness: claude-code <model>`. Every later commit uses the same trailers.

---

### Task 2: `specloop skill` and stubs

**Files:**
- Modify: `src/specloop/cli.py`
- Create: `src/specloop/data/stub.md`, `src/specloop/project.py`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Produces: `specloop skill <name>` prints `<!-- specloop <version> -->` then the skill's full text, exit 0; unknown name exits 2. `project.SKILLS = ("spec-sync", "spec-init", "spec-triage")`. `project.render_stub(name: str) -> str`. `project.frontmatter(text: str) -> str` (the `---` block, verbatim). `project.STUB_MARKER = "<!-- specloop stub -->"`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

Import `project` and `DATA` by putting `HERE / "src"` on `sys.path` at the top of the test module.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.SkillTests -v`
Expected: FAIL

- [ ] **Step 3: Implement `cmd_skill` in `cli.py`, and `render_stub` / `frontmatter` in `project.py`**

`stub.md` is the body after the frontmatter: the marker line, then "Run `tools/specloop skill <name>` and follow what it prints, step by step. It holds this skill's instructions for the specloop version installed on this machine. If the command fails, follow what it printed instead." `render_stub` is `frontmatter(full) + "\n" + stub body` with `<name>` filled in.

- [ ] **Step 4: Run them to make sure they pass**

Run: `python3 -m unittest tests.test_distribution.SkillTests -v`
Expected: PASS

- [ ] **Step 5: Commit** (`Serve skill instructions from the installed specloop`)

---

### Task 3: Shims, `specloop hook` and `specloop init`

**Files:**
- Create: `src/specloop/data/shim.sh`, `src/specloop/data/hook.sh`
- Modify: `src/specloop/project.py`, `src/specloop/cli.py`, `src/specloop/data/specloop-trigger` (header comment only)
- Modify: `tests/test_specloop.py` (`Repo.__init__` uses `init`)
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `project.render_stub`, `project.SKILLS` (Task 2).
- Produces:
  - `project.HOOKS = {"post-commit": "commit", "post-merge": "merge", "post-rewrite": "rebase", "commit-msg": "commit-msg"}`.
  - `project.SHIM_MARKER = "# specloop shim"`; `project.render_shim() -> str`; `project.render_hook(git_hook: str) -> str`.
  - `project.Change = namedtuple("Change", "path action note")`, `action` one of `"create"`, `"replace"`, `"keep"`, `"delete"`. `note` is a message or a diff to print, or `""`.
  - `project.write_files(root: Path, config: dict, changes: list) -> None`.
  - `project.plan_init(root: Path, config: dict) -> list[Change]`: shims, hooks, stubs, `specloop.json` (if missing, with `minVersion`), spec templates (if no spec). Task 4 adds the block.
  - `specloop init [path]` prints one line per change and the next steps (fill in `specloop.json`; enable hooks with `git config core.hooksPath tools/githooks`).
  - `specloop hook <commit|merge|rebase|commit-msg> [args...]` runs `sh <DATA>/specloop-trigger <mode>` from the project root, or for `commit-msg` runs `trailers --verify <file>` in-process. `merge` with first arg `1` (squash) and `rebase` with first arg other than `rebase` exit 0 at once, as the hook scripts do today.

The shim (`shim.sh`) looks for an executable `specloop` in `$PATH`, then `/opt/homebrew/bin`, `/usr/local/bin`, `$HOME/.local/bin`, skipping any whose resolved path is the shim itself, and `exec`s it with `"$@"`. If none: when `$1` is `hook`, print `specloop: not installed (brew install KVTaniguchi/tap/specloop, or pipx install specloop); skipping` to stderr and exit 0; otherwise print the same install line and exit 127. Each git hook (`hook.sh`) is `exec "$(git rev-parse --show-toplevel)/tools/specloop" hook <mode> "$@"`. The trigger keeps calling `$root/tools/specloop`, so it needs no logic change.

- [ ] **Step 1: Write the failing tests**

```python
class ShimTests(SpecloopTestCase):
    def test_init_writes_thin_files(self):
        repo = self.repo()  # Repo now runs init
        self.assertIn(project.SHIM_MARKER, (repo.path / "tools/specloop").read_text())
        for hook in project.HOOKS:
            self.assertIn(" hook ", (repo.path / "tools/githooks" / hook).read_text())
        for name in project.SKILLS:
            self.assertIn(project.STUB_MARKER, (repo.path / f".claude/skills/{name}/SKILL.md").read_text())
        self.assertEqual(json.loads((repo.path / "specloop.json").read_text())["minVersion"], "0.1.0")

    def test_init_never_overwrites_config_or_spec(self):
        # write specloop.json with {"tests": {"paths": ["t"]}} and docs/SPEC.md first; after init both are unchanged
        ...

    def test_hook_finds_cli_outside_path(self):
        # HOME=<tmp>/home with home/.local/bin/specloop -> symlink to bin/specloop; PATH=/usr/bin:/bin
        # a spec commit with SPEC_SYNC=dry-run prints "would start background"
        ...

    def test_commit_succeeds_without_cli(self):
        # PATH=/usr/bin:/bin, HOME empty; commit returns 0 and stderr has "not installed"
        ...

    def test_direct_shim_call_without_cli_fails(self):
        # same env; tools/specloop status exits 127 with the install line
        ...
```

Write the `...` bodies with the `Repo` helper (`git`, `commit`, `run`, env overrides), asserting exactly what the comments say. `Repo.__init__` stops copying files: it puts a `specloop` symlink to `HERE/bin/specloop` in its fake `bin_dir` (already first on `PATH`) and runs `specloop init` before writing its own `specloop.json`. Because the test's `specloop.json` is written after `init`, keep `minVersion` by merging it in.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.ShimTests -v`
Expected: FAIL

- [ ] **Step 3: Implement the templates, `plan_init`, `write_files`, `cmd_init` and `cmd_hook`**

`write_files` sets mode 0o755 on `tools/specloop` and `tools/githooks/*`. `init` refuses a path that isn't a git repo, with the same message as `install.sh` today.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass. The existing `HookTests`, `CursorTests` and `SyncStartTests` now go through the shims, which is the regression check for the trigger.

- [ ] **Step 5: Commit** (`Projects keep thin shims; specloop init writes them`)

---

### Task 4: The managed block in `CLAUDE.md` / `AGENTS.md`

**Files:**
- Modify: `src/specloop/data/claude-block.md` (drop the "paste this" comment and the trailing rules section), `src/specloop/project.py`, `src/specloop/cli.py`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `Change`, `plan_init`, `write_files` (Task 3).
- Produces:
  - `project.BEGIN = "<!-- specloop:begin (managed by specloop update; edits here are replaced) -->"`, `project.END = "<!-- specloop:end -->"`.
  - `project.RULES_HEADING = "### Spec sync rules for this project"`.
  - `project.PASTED_HEADING = "## Spec-driven development (specloop)"`.
  - `project.render_block() -> str`: `BEGIN`, the block text, `END`, each on its own line.
  - `project.apply_block(text: str) -> tuple[str, str]`: returns `(new_text, diff)`. With markers: replace what's between them. Without markers but with `PASTED_HEADING`: replace from that heading up to (not including) `RULES_HEADING`, or the next `## ` heading, or the end. With neither: append the block, then `RULES_HEADING` and its placeholder comment if the file has no `RULES_HEADING`. `diff` is a unified diff of the replaced region against the new block (empty when unchanged).
  - `project.block_targets(root: Path, harness: str) -> list[Path]`: every existing `CLAUDE.md` and `AGENTS.md` at the root, or, if neither exists, `CLAUDE.md` for `claude` and `AGENTS.md` for `cursor`.
  - `project.outside_block(text: str) -> str`: the text with the marked block removed (used in Task 7).
  - `plan_init` adds a `Change` per block target.

- [ ] **Step 1: Write the failing tests**

```python
class ClaudeBlockTests(unittest.TestCase):
    def test_appends_block_and_rules_section(self):
        new, _ = project.apply_block("# My app\n")
        self.assertIn(project.BEGIN, new)
        self.assertLess(new.index(project.END), new.index(project.RULES_HEADING))

    def test_replaces_only_inside_markers(self):
        text = f"top\n{project.BEGIN}\nold\n{project.END}\nbottom\n"
        new, diff = project.apply_block(text)
        self.assertTrue(new.startswith("top\n") and new.endswith("bottom\n"))
        self.assertIn("-old", diff)

    def test_migrates_pasted_section_keeping_project_rules(self):
        rules = f"{project.RULES_HEADING}\n\n- Never bump the build number.\n\n## Other\n\nkeep me\n"
        text = f"# App\n\n{project.PASTED_HEADING}\n\n- old bullet\n\n{rules}"
        new, diff = project.apply_block(text)
        self.assertTrue(new.endswith(rules))
        self.assertTrue(new.startswith("# App\n\n" + project.BEGIN))
        self.assertIn("-- old bullet", diff)

    def test_unchanged_block_has_no_diff(self):
        new, _ = project.apply_block("x\n")
        self.assertEqual(project.apply_block(new), (new, ""))
```

Plus, in `ShimTests`: `init` on a repo with no `CLAUDE.md` creates one with the block; with `git config specloop.harness cursor` creates `AGENTS.md` instead.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.ClaudeBlockTests -v`
Expected: FAIL

- [ ] **Step 3: Implement the functions; `cmd_init` prints each block diff it applies**

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 5: Commit** (`Manage specloop's block in CLAUDE.md and AGENTS.md`)

---

### Task 5: `minVersion` enforcement

**Files:**
- Modify: `src/specloop/cli.py`, `src/specloop/data/specloop-trigger`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Produces:
  - `cli.parse_version(text: str) -> tuple[int, int, int]`; a malformed value raises `ValueError`.
  - `cli.version_gap(config: dict) -> str | None`: `None` when `minVersion` is absent, malformed, or ≤ `__version__`; otherwise `"specloop 0.1.0 is older than this project's minimum 0.3.0; upgrade with <cmd>"`, where `<cmd>` is `brew upgrade specloop` if the resolved CLI path contains `/Cellar/`, `pipx upgrade specloop` if it contains `/pipx/`, else `git pull in <checkout>` for a dev or `install.sh` link.
  - `specloop version-ok`: exit 0 if no gap, else print the gap and exit 1. Used by the trigger.
  - A malformed `minVersion` prints `specloop: minVersion "<value>" in specloop.json isn't a version like 0.3.0; ignoring it` once per command.

Behavior:
- `run()` prints the gap to stderr before every command except `--version`, `version-ok`, `init`, `update` and `skill` (which handle it themselves).
- `status` prints the gap as its first stdout line too.
- `skill spec-sync` with a gap prints, instead of the skill: the gap line, then "Don't build anything. Record this sync as blocked and stop:" and the command `tools/specloop sync blocked --note "specloop <installed> < <minVersion>; <cmd>"`. It exits 1. Other skills print the gap to stderr and then the text, exit 0.
- `describe_sync` shows a blocked sync whose note starts with `specloop ` and contains ` < ` as `blocked: <note up to ;>`.
- The trigger runs `"$specloop" version-ok || exit 0` right after the linked-worktree and branch checks, before cleanup, so nothing starts and git continues.

- [ ] **Step 1: Write the failing tests**

```python
class MinVersionTests(SpecloopTestCase):
    def ahead(self, repo, v="9.0.0"):
        cfg = json.loads((repo.path / "specloop.json").read_text()); cfg["minVersion"] = v
        repo.write("specloop.json", json.dumps(cfg)); repo.commit("min", SPEC_SYNC="off")

    def test_commands_warn_and_run(self):
        repo = self.repo(); self.ahead(repo)
        out = repo.run("coverage")
        self.assertEqual(out.returncode, 0)
        self.assertIn("older than this project's minimum 9.0.0", out.stderr)

    def test_status_leads_with_gap(self):
        repo = self.repo(); self.ahead(repo)
        self.assertTrue(repo.run("status").stdout.startswith("specloop 0.1.0 is older"))

    def test_spec_sync_skill_stops(self):
        repo = self.repo(); self.ahead(repo)
        out = repo.run("skill", "spec-sync")
        self.assertEqual(out.returncode, 1)
        self.assertNotIn("# Spec sync", out.stdout)
        self.assertIn("sync blocked --note", out.stdout)

    def test_other_skills_run(self):
        repo = self.repo(); self.ahead(repo)
        self.assertEqual(repo.run("skill", "spec-triage").returncode, 0)

    def test_hook_starts_nothing_and_commit_succeeds(self):
        repo = self.repo(); self.ahead(repo); repo.enable_hooks()
        repo.change_spec()  # commits a spec change through the hook
        self.assertEqual(repo.claude_calls(), [])
        self.assertEqual(repo.syncs(), [])

    def test_blocked_status_names_versions(self):
        # after `sync blocked --note "specloop 0.1.0 < 9.0.0; brew upgrade specloop"`, status shows "blocked: specloop 0.1.0 < 9.0.0"
        ...

    def test_no_min_no_warning(self):
        # Repo's minVersion equals the installed version; also check with the key removed
        self.assertNotIn("older", self.repo().run("coverage").stderr)

    def test_malformed_min_warns_once(self):
        # minVersion "soon": coverage exits 0, stderr has the "isn't a version" line exactly once
        ...
```

Check `change_spec`'s exact behavior in `tests/test_specloop.py` before relying on it.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.MinVersionTests -v`
Expected: FAIL

- [ ] **Step 3: Implement as described under Behavior**

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 5: Commit** (`Warn below minVersion, and block syncs`)

---

### Task 6: `specloop update`, including moving copied installs over

**Files:**
- Create: `scripts/known-copies`, `src/specloop/data/known-copies.json`
- Modify: `src/specloop/project.py`, `src/specloop/cli.py`, `src/specloop/data/CHANGELOG.md` (a committed copy of the root `CHANGELOG.md`, refreshed by `scripts/release` in Task 8)
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: everything in `project` from Tasks 2–4; `cli.parse_version` (Task 5).
- Produces:
  - `known-copies.json`: `{"cli": [blob...], "trigger": [...], "post-commit": [...], "post-merge": [...], "post-rewrite": [...], "commit-msg": [...], "spec-sync": [...], "spec-init": [...], "spec-triage": [...]}`, git blob SHA-1s of every version of each file in this repo's history (old paths `bin/specloop`, `hooks/*`, `skills/*/SKILL.md`; new paths after Task 1). `scripts/known-copies` regenerates it with `git log --all --format=%H -- <path>` and `git rev-parse <commit>:<path>`.
  - `project.classify(path: Path, kind: str) -> str`: `"current"` (same as what `init` would write), `"thin"` (a shim, hook or stub from any version, by marker), `"copy"` (blob hash in `known-copies.json`), or `"edited"` (anything else).
  - `project.plan_update(root: Path, config: dict) -> list[Change]`: `"current"` → nothing; `"thin"` or `"copy"` → replace; `"edited"` → `keep`, with a note holding a unified diff against the current packaged full text for skills, or the new thin file otherwise; block targets via `apply_block`; `minVersion` raised to `__version__`; a removed `tools/githooks/specloop-trigger` (a `Change` with action `"delete"`).
  - `project.forks(root: Path) -> list[Path]`: skill files under `.claude/skills/<SKILLS>/SKILL.md` without `STUB_MARKER`.
  - `project.release_notes(since: str, until: str) -> str`: the `## X.Y.Z` sections of `data/CHANGELOG.md` with `since < X.Y.Z <= until`.
  - `specloop update`: refuses with exit 1 and `specloop <installed> is older than this project's minimum <min>; upgrade before updating` when there's a gap; otherwise writes the plan, prints each change, each kept fork's diff, the release notes since the old `minVersion` (all notes if none), and `Review and commit these changes.` It never commits.
  - `status` prints `fork: .claude/skills/<name>/SKILL.md is a local copy and doesn't get updates` for each fork.

- [ ] **Step 1: Write the failing tests**

```python
class UpdateTests(SpecloopTestCase):
    def copied_install(self, repo, rev="7da7cea"):
        # overwrite tools/specloop, tools/githooks/*, .claude/skills/*/SKILL.md with their contents at `rev`
        # (git -C HERE show <rev>:bin/specloop etc.), drop minVersion, remove the block markers
        ...

    def test_moves_copied_install_over(self):
        repo = self.repo(); self.copied_install(repo)
        out = repo.run("update")
        self.assertEqual(out.returncode, 0)
        self.assertIn(project.SHIM_MARKER, (repo.path / "tools/specloop").read_text())
        self.assertFalse((repo.path / "tools/githooks/specloop-trigger").exists())
        self.assertEqual(json.loads((repo.path / "specloop.json").read_text())["minVersion"], "0.1.0")
        self.assertIn("Review and commit", out.stdout)

    def test_edited_skill_is_kept_as_fork(self):
        repo = self.repo(); self.copied_install(repo)
        skill = repo.path / ".claude/skills/spec-sync/SKILL.md"
        skill.write_text(skill.read_text() + "\nLocal rule.\n")
        out = repo.run("update")
        self.assertIn("Local rule.", skill.read_text())
        self.assertIn("+Local rule.", out.stdout)  # diff from the packaged text to the local file
        self.assertIn("fork: .claude/skills/spec-sync/SKILL.md", repo.run("status").stdout)

    def test_unrecognized_cli_is_kept(self):
        # tools/specloop replaced by "#!/bin/sh\necho mine\n": update keeps it and prints a diff
        ...

    def test_older_cli_refuses_to_update(self):
        # minVersion 9.0.0: update exits 1, files and specloop.json unchanged (compare bytes before/after)
        ...

    def test_update_is_idempotent(self):
        repo = self.repo(); repo.run("update"); repo.commit("u", SPEC_SYNC="off")
        repo.run("update")
        self.assertEqual(repo.git("status", "--porcelain").stdout, "")

    def test_never_touches_project_state(self):
        # spec, ledger, docs/signals/*, .git/specloop/syncs/* and CLAUDE.md outside markers byte-identical after update
        ...

    def test_release_notes_since_old_min(self):
        notes = project.release_notes("0.0.0", "0.1.0")
        self.assertIn("## 0.1.0", notes)
```

After `copied_install`, `tools/specloop` is the old copied CLI, which has no `update`. Run `update` and `status` in these tests through the `specloop` on the test `PATH` (`subprocess.run(["specloop", ...], cwd=repo.path, env=repo.env)`), which is this checkout's.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.UpdateTests -v`
Expected: FAIL

- [ ] **Step 3: Generate `known-copies.json` with `scripts/known-copies`, then implement `classify`, `plan_update`, `forks`, `release_notes`, `cmd_update`**

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 5: Try it on a copy of KTCatPokemon**

Run: `git clone -q ~/Development/KTCatPokemon <scratchpad>/ktcp && (cd <scratchpad>/ktcp && <repo>/bin/specloop update && git status --short && git diff --stat)`
Expected: `tools/specloop`, `tools/githooks/*`, the three skills, `CLAUDE.md` and `specloop.json` changed; `tools/githooks/specloop-trigger` deleted; no file under `docs/` or `KTCatPokemon/` changed; the `CLAUDE.md` diff keeps "Spec sync rules for this project" intact. Don't touch the real KTCatPokemon checkout.

- [ ] **Step 6: Commit** (`specloop update moves a project to the installed version`)

---

### Task 7: `Harness-Rev` and tolerance of newer files

**Files:**
- Modify: `src/specloop/cli.py` (`HARNESS_FILES`, `harness_revs`, `signals --by harness`), `src/specloop/data/skills/spec-triage/SKILL.md`, `docs/attribution.md`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `project.outside_block` (Task 4), `__version__`.
- Produces: `harness_revs(root)` returns `specloop@<version>` followed by `claude-md@<hash>` and `agents-md@<hash>` for each file present, each hash `git hash-object --stdin` of `outside_block(text)`, first 6 hex chars. The `spec-sync@` entry is gone unless `.claude/skills/spec-sync/SKILL.md` is a fork, in which case `spec-sync@<hash>` of the file is added after `specloop@…`.

- [ ] **Step 1: Write the failing tests**

```python
class HarnessRevTests(SpecloopTestCase):
    def test_names_version_and_hashes_outside_block(self):
        repo = self.repo()
        rev = re.search(r"^Harness-Rev: (.*)$", repo.run("trailers", "--none", "deps", "--human").stdout, re.M).group(1)
        self.assertTrue(rev.startswith("specloop@0.1.0 "))
        self.assertNotIn("spec-sync@", rev)
        before = rev
        # edit only inside the markers of CLAUDE.md: claude-md@ hash unchanged; edit outside: it changes
        ...

    def test_fork_is_named(self):
        # replace the spec-sync stub with full text: Harness-Rev contains spec-sync@
        ...

class ToleranceTests(SpecloopTestCase):
    def test_unknown_fields_survive_rewrite(self):
        # 1. add "fromTheFuture": 1 to a sync record; run `sync done`; field still there
        # 2. add it to a signal; run `signal triage ... --confirm`; field still there
        # 3. add "futureKey": {"a": 1} to specloop.json; run `update`; key still there
        # 4. a commit with trailer "Spec-Future: x" plus normal trailers: `blame --commit` succeeds
        ...
```

`signals --by harness` needs no new test if it already groups by the raw `Harness-Rev` string; read it first and add one only if it parses entries.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.HarnessRevTests tests.test_distribution.ToleranceTests -v`
Expected: `HarnessRevTests` FAIL; `ToleranceTests` may already pass for 1, 2 and 4 (records are saved whole today). Keep those cases as regression tests.

- [ ] **Step 3: Implement the `harness_revs` change; fix whatever `ToleranceTests` finds**

In `spec-triage`'s harness row and `attribution.md`'s feedback section, say a confirmed `harness/skill` pattern becomes an issue or PR against specloop, and project-specific fixes go in "Spec sync rules for this project". Update the `Harness-Rev` row and example in `attribution.md` and close its open question about the specloop version.

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 5: Commit** (`Harness-Rev names the specloop version`)

---

### Task 8: Release tooling: fixtures, formula, action, release script

**Files:**
- Create: `scripts/make-fixture`, `tests/fixtures/v0.1.0/` (generated), `packaging/homebrew/specloop.rb`, `action.yml`, `scripts/release`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `specloop init` (Task 3).
- Produces:
  - `scripts/make-fixture <version>`: builds a project in a temp dir with `bin/specloop init`, a tree spec with two rules, tagged tests, a ledger, one signal, one finished sync archived through `cleanup`, and commits with trailers; writes `tests/fixtures/v<version>/repo.bundle` (`git bundle create … --all`) and `tests/fixtures/v<version>/state/` (a copy of `.git/specloop/`).
  - `CompatTests` runs, for each `tests/fixtures/v*/`: clone the bundle, copy `state/` to `.git/specloop/`, then `status`, `check`, `coverage` and `pending`, each with exit code 0 and no traceback in the output.
  - `action.yml`: composite action, one step: read `minVersion` from `specloop.json` with `python3 -c`, then `pipx install "specloop==$v"` (or `pipx install specloop` with no `minVersion`).
  - `packaging/homebrew/specloop.rb`: formula installing the sdist with `virtualenv_install_with_resources`, `depends_on "python@3.12"`, `test do` running `specloop --version`. `url` and `sha256` are placeholders the release script fills.
  - `scripts/release <version>`: checks the tree is clean and `CHANGELOG.md` has `## <version>`; sets `__version__`; copies `CHANGELOG.md` into `data/`; runs `scripts/known-copies` and `scripts/make-fixture <version>`; runs the tests; commits; tags `v<version>`; builds with `python3 -m build`; then **prints** the remaining commands (`git push --follow-tags`, `twine upload dist/*`, and the formula `url`/`sha256` to paste into the tap) rather than running them, since they publish under the owner's accounts.

- [ ] **Step 1: Write the failing test**

```python
class CompatTests(SpecloopTestCase):
    def test_fixtures_still_read(self):
        fixtures = sorted((HERE / "tests" / "fixtures").glob("v*"))
        self.assertTrue(fixtures)
        for fixture in fixtures:
            with self.subTest(fixture.name):
                ...  # clone, copy state, run the four commands, assert as above
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m unittest tests.test_distribution.CompatTests -v`
Expected: FAIL (no fixtures)

- [ ] **Step 3: Write `scripts/make-fixture`, run it for 0.1.0, implement the test body; write the action, formula and release script**

- [ ] **Step 4: Check the package builds and installs**

Run: `python3 -m venv <scratchpad>/venv && <scratchpad>/venv/bin/pip install -q . && <scratchpad>/venv/bin/specloop --version && <scratchpad>/venv/bin/specloop skill spec-sync | head -1`
Expected: `specloop 0.1.0`, then `<!-- specloop 0.1.0 -->`

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 6: Commit** (`Release tooling, compatibility fixtures, Homebrew formula and CI action`)

---

### Task 9: `install.sh` and the docs

**Files:**
- Modify: `install.sh`, `README.md`, `docs/ci.md`, `docs/distribution.md` (status line, open question), `docs/lessons.md` (nothing yet; add an entry after the first real migration, not in this task)
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `specloop init` (Task 3).
- Produces: `install.sh <project>` makes `~/.local/bin/specloop` a symlink to this checkout's `bin/specloop` (replacing an existing symlink, refusing to replace a regular file), warns if `~/.local/bin` isn't on `PATH`, then runs `~/.local/bin/specloop init <project>`.

- [ ] **Step 1: Write the failing test**

```python
class InstallScriptTests(SpecloopTestCase):
    def test_links_and_inits(self):
        # HOME=<tmp>/home; run install.sh on a fresh git repo; home/.local/bin/specloop resolves to HERE/bin/specloop; repo has the shim
        ...

    def test_refuses_to_replace_a_real_file(self):
        # home/.local/bin/specloop is a regular file: install.sh exits non-zero and leaves it
        ...
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m unittest tests.test_distribution.InstallScriptTests -v`
Expected: FAIL

- [ ] **Step 3: Rewrite `install.sh`; update the docs**

- README "Install": `brew install KVTaniguchi/tap/specloop` or `pipx install specloop`, then `specloop init` in the project; `install.sh` as the no-package-manager route. A new "Updating" section: `brew upgrade specloop` / `pipx upgrade specloop`, then `specloop update` in each project and commit. The file table lists the thin files. Remove the "paste `templates/CLAUDE.md`" step.
- `docs/ci.md`: the GitHub Actions example uses `uses: KVTaniguchi/specloop@v0.1.0` before `tools/specloop check`, and explains that CI installs exactly `minVersion`.
- `docs/distribution.md`: status "built (date), not yet released"; replace the PyPI open question with "checked 2026-10-30: free".

- [ ] **Step 4: Run the whole suite**

Run: `python3 -m unittest discover tests`
Expected: all pass

- [ ] **Step 5: Commit** (`install.sh links the CLI; docs describe installing and updating`)

---

## After the plan

Done by the owner, not in any task: create the `KVTaniguchi/homebrew-tap` repo, a PyPI account and token, run `scripts/release 0.1.0`, push, upload, and update the tap. Then `brew upgrade` and `specloop update` in KTCatPokemon, and record what happened in `docs/lessons.md`.
