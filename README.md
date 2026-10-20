# specloop

**Keep a spec, the code, and the tests in lockstep — with Claude Code doing the implementation.**

You edit a Markdown spec and commit. A background Claude Code session builds the change on a review branch, writes tests tagged with the rules they check, and records which spec revision the code now matches. The spec stays a *stateful* source of truth: it always describes what the project actually does.

> Status: early. Extracted from one real iOS project in October 2026. See [docs/lessons.md](docs/lessons.md) for what's been learned so far, including what hasn't been proven yet.

## Why another spec-driven tool?

Tools like GitHub Spec Kit and Kiro focus on the step from spec to plan to code. specloop focuses on what happens **after** that, when the spec has to stay true:

- **Ledger.** `docs/.spec-implemented` records the exact spec revision the code matches, so "what's left to build" is always just a `git diff`.
- **Traceability.** Every rule has a stable ID. Every test names the IDs it checks. `specloop coverage` maps the two and fails when a test names an ID the spec no longer defines.
- **Two-way discipline.** Spec edits drive code changes. When the code changes first, the spec is updated in the same commit.
- **Sensors.** The hooks notice a spec change however it arrives (commit, merge, pull, rebase). `specloop status` shows where each pending revision stands, and `specloop check` fails CI when the spec and the code drift apart.

## The loop

```
edit docs/SPEC.md ──► git commit / merge / pull
                         │  hook (only if the spec changed and isn't built yet)
                         ▼
          background Claude Code session, own worktree
                         │  /spec-sync
                         ├─ specloop pending        what changed since the ledger
                         ├─ build it, tag tests     @Test("XP-6: …")
                         ├─ run tests + coverage    specloop coverage --ids …
                         └─ specloop mark + commit  on spec-sync/<sha>
                         ▼
               you review the branch and merge
```

## Install

Requirements: git, Python 3.8+ (standard library only), [Claude Code](https://claude.com/claude-code) for the skills and trigger.

```bash
git clone https://github.com/KVTaniguchi/specloop.git ~/specloop
~/specloop/install.sh /path/to/your/project
```

This copies the following into your project, without overwriting anything you already have:

| File | Purpose |
|---|---|
| `tools/specloop` | CLI: `status`, `pending`, `coverage`, `check`, `mark`, `sync`, `trigger`, `config` |
| `tools/githooks/` | Trigger: `post-commit`, `post-merge` and `post-rewrite` start `/spec-sync` when the spec changes |
| `.claude/skills/spec-sync/` | Builds a pending spec diff |
| `.claude/skills/spec-init/` | Drafts the first spec from existing code |
| `specloop.json` | Spec path, test dirs and tag styles, test command |
| `docs/SPEC.md` | Template, only if you don't have one |

Then:
1. Fill in `specloop.json`, especially `commands.test` and `tests.paths`.
2. Paste [templates/CLAUDE.md](templates/CLAUDE.md) into your project's `CLAUDE.md`.
3. In Claude Code, run `/spec-init`. It drafts the spec from the code as it is today, tags existing tests, and records the baseline.
4. **Enable the trigger (optional).** The hook starts background Claude Code agents that edit code on their own, so this step is a deliberate opt-in. Claude Code's safety checks may ask you to confirm. Without it, run `/spec-sync` yourself after committing a spec change.
   ```bash
   git config core.hooksPath tools/githooks
   ```
   Background sessions need two things the desktop app doesn't give the command-line `claude`: the project folder must be trusted (run `claude` in it once and accept the prompt), and the CLI must be logged in (`claude auth status`, then `claude auth login` if needed). Test the hook without launching anything with `SPEC_SYNC=dry-run git commit …`.

## Day to day

| You want to… | Do this |
|---|---|
| Change behavior | Edit the spec, commit, review the `spec-sync/…` branch, merge |
| Skip the trigger once | `SPEC_SYNC=off git commit …` |
| See what's pending | `tools/specloop status` (each pending revision: not started, running, awaiting review, blocked, failed) / `tools/specloop pending` |
| Hotfix code directly | Change code **and** spec in one commit (`SPEC_SYNC=off`), then `tools/specloop mark` |
| Check test coverage | `tools/specloop coverage` (`--uncovered`, `--require XP,LVL`) |
| Watch a running sync | `tools/specloop status`, `claude agents`, `claude attach "Spec sync <sha>"` |
| Review a sync locally | `cd .claude/worktrees/spec-sync-<sha>` (its branch is checked out there) |
| Clean up sync worktrees | Automatic after a merge; `tools/specloop cleanup` ([details](docs/ci.md#cleaning-up-worktrees)) |
| Gate CI on the spec | `tools/specloop check` ([CI setup](docs/ci.md)) |

## Docs

- [Writing a spec](docs/spec-format.md): IDs, good rules, tagging tests in each framework
- [Sensors and CI](docs/ci.md): how syncs are tracked and cleaned up, and `specloop check` in GitHub Actions
- [Lessons](docs/lessons.md): what happened on a real project
- [Example: iOS / Swift](examples/ios-swift/)

## Development

```bash
python3 -m unittest discover tests
```

## License

MIT
