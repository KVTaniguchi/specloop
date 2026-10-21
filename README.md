# specloop

**Keep a spec, the code, and the tests in lockstep — with your coding agent (Claude Code or Cursor) doing the implementation.**

The product is described by a tree of Markdown docs in git: an overview at the top that links to one doc per feature. To change the product you open a pull request against the spec, not the code. Once it's merged and you pull, a background agent on your machine builds the change on a review branch, writes tests tagged with the rules they check, and records which spec revision the code now matches. The spec stays a *stateful* source of truth: it always describes what the project actually does.

> Status: early. Extracted from one real iOS project in October 2026. See [docs/lessons.md](docs/lessons.md) for what's been learned so far, including what hasn't been proven yet.

## Why another spec-driven tool?

Tools like GitHub Spec Kit and Kiro focus on the step from spec to plan to code. specloop focuses on what happens **after** that, when the spec has to stay true:

- **Ledger.** `docs/.spec-implemented` records the exact spec revision the code matches, so "what's left to build" is always just a `git diff`.
- **Traceability.** Every rule has a stable ID. Every test names the IDs it checks. `specloop coverage` maps the two and fails when a test names an ID the spec no longer defines.
- **Two-way discipline.** Spec edits drive code changes. When the code changes first, the spec is updated in the same commit.
- **No collisions.** The trigger runs locally, on the machine of whoever wrote the spec change. Everyone else who pulls the same merge sees it in `status` but doesn't build it too.
- **Attribution.** Every code commit names its rules, their versions and the harness that built it in trailers. `specloop blame` follows a crash or a failing test back to them, and `/spec-triage` decides whether the spec, the code, the tests or the harness needs the fix.
- **Sensors.** The hooks notice a spec change however it arrives (commit, merge, pull, rebase). `specloop status` shows where each pending revision stands, and `specloop check` fails CI when the spec and the code drift apart.

## The spec tree

```
docs/spec/
├── README.md          overview: product, non-goals, links to every feature doc
├── scanning.md        SCAN-1, SCAN-2, …
├── leveling.md        LVL-1, …
└── billing/
    ├── README.md      a big feature can be a folder with its own overview
    └── refunds.md
```

Every `.md` under `docs/spec/` is part of the spec. Rule IDs are unique across the whole tree, and `specloop check` fails on broken links or on a doc that nothing links to, so the overview always leads to every rule. A small project can keep one file instead (`"spec": "docs/SPEC.md"`).

## The loop

```
spec PR ──► review ──► merge ──► git pull (or commit locally)
                         │  hook (only if the spec changed, isn't built yet,
                         │        and you wrote the change)
                         ▼
     background Claude Code or Cursor agent, own worktree
                         │  /spec-sync
                         ├─ specloop pending        what changed since the ledger
                         ├─ build it, tag tests     @Test("XP-6: …")
                         ├─ run tests + coverage    specloop coverage --ids …
                         └─ specloop mark + commit  on spec-sync/<sha>
                         ▼
               you review the branch and merge
```

## Install

Requirements: git, Python 3.8+ (standard library only), and a coding agent for the skills and trigger: [Claude Code](https://claude.com/claude-code), or [Cursor](https://cursor.com) with its `agent` CLI.

```bash
git clone https://github.com/KVTaniguchi/specloop.git ~/specloop
~/specloop/install.sh /path/to/your/project
```

This copies the following into your project, without overwriting anything you already have:

| File | Purpose |
|---|---|
| `tools/specloop` | CLI: `status`, `pending`, `coverage`, `check`, `mark`, `sync`, `trigger`, `config`, and for feedback `trailers`, `blame`, `signal`, `signals` |
| `tools/githooks/` | Trigger: `post-commit`, `post-merge` and `post-rewrite` start `/spec-sync` when the spec changes. `commit-msg` checks trailers, if you turn it on |
| `.claude/skills/spec-sync/` | Builds a pending spec diff. Cursor reads `.claude/skills/` too, so `/spec-sync` works in both. |
| `.claude/skills/spec-init/` | Drafts the first spec from existing code |
| `.claude/skills/spec-triage/` | Traces a crash, failing test, QA report or review comment to its rules and harness, and proposes which layer to fix |
| `specloop.json` | Spec path, test dirs and tag styles, test command |
| `docs/spec/` | Overview and feature templates, only if you don't have a spec |

Then:
1. Fill in `specloop.json`, especially `commands.test` and `tests.paths`.
2. Paste [templates/CLAUDE.md](templates/CLAUDE.md) into your project's `CLAUDE.md` (Claude Code) or `AGENTS.md` (Cursor).
3. In Claude Code or Cursor, run `/spec-init`. It drafts the spec from the code as it is today, tags existing tests, and records the baseline.
4. **Enable the trigger (optional).** The hook starts background Claude Code agents that edit code on their own, so this step is a deliberate opt-in. Claude Code's safety checks may ask you to confirm. Without it, run `/spec-sync` yourself after committing a spec change.
   ```bash
   git config core.hooksPath tools/githooks
   ```
   Each person picks their own agent for their clone. Claude Code is the default:
   ```bash
   git config specloop.harness cursor
   ```
   **Claude Code:** background sessions need two things the desktop app doesn't give the command-line `claude`: the project folder must be trusted (run `claude` in it once and accept the prompt), and the CLI must be logged in (`claude auth status`, then `claude auth login` if needed). **Cursor:** install the `agent` CLI and log in (`agent login`). The hook runs `agent -p --force --trust` in a worktree at `.specloop/worktrees/spec-sync-<sha>`, with its output in `.git/specloop/logs/<sha>.log`.
   Test the hook without launching anything with `SPEC_SYNC=dry-run git commit …`.
5. **If GitHub squash-merges your PRs under a noreply address**, tell specloop it's you, so the trigger knows the change is yours to build:
   ```bash
   git config --add specloop.email 12345+you@users.noreply.github.com
   ```

## Day to day

| You want to… | Do this |
|---|---|
| Change behavior | Open a PR against `docs/spec/`, merge it, pull. Then review the `spec-sync/…` branch your agent made, and push it as a code PR |
| Build someone else's spec change | `/spec-sync` (the hook leaves it to its author; `status` says whose it is) |
| Build every spec change you pull | `"trigger": "all"` under `sync` in `specloop.json` |
| Skip the trigger once | `SPEC_SYNC=off git commit …` |
| See what's pending | `tools/specloop status` (each pending revision: not started, running, awaiting review, blocked, failed) / `tools/specloop pending` |
| Hotfix code directly | Change code **and** spec in one commit (`SPEC_SYNC=off`), then `tools/specloop mark` |
| Check test coverage | `tools/specloop coverage` (`--uncovered`, `--require XP,LVL`) |
| Watch a running sync | `tools/specloop status`; Claude Code: `claude agents`, `claude attach "Spec sync <sha>"`; Cursor: `tail -f .git/specloop/logs/<sha>.log` |
| Review a sync locally | `cd .claude/worktrees/spec-sync-<sha>` (Claude Code) or `.specloop/worktrees/spec-sync-<sha>` (Cursor); its branch is checked out there |
| Clean up sync worktrees | Automatic after a merge; `tools/specloop cleanup` ([details](docs/ci.md#cleaning-up-worktrees)) |
| Gate CI on the spec | `tools/specloop check` ([CI setup](docs/ci.md)) |
| Commit code by hand | End the message with `tools/specloop trailers --rules XP-6 --human`, or `--none deps` |
| Find what built a line | `tools/specloop blame src/xp.swift:42` (also `--test`, `--rule`, `--commit`) |
| Report a crash, bug or review comment | `/spec-triage` with the evidence; `tools/specloop signals` lists open ones |
| See whether a harness change helped | `tools/specloop signals --by harness` |

## Docs

- [Writing a spec](docs/spec-format.md): the tree, IDs, good rules, tagging tests in each framework
- [Sensors and CI](docs/ci.md): how syncs are tracked and cleaned up, and `specloop check` in GitHub Actions
- [Attribution and feedback](docs/attribution.md): commit trailers, blame, signals and triage
- [Lessons](docs/lessons.md): what happened on a real project
- [Example: iOS / Swift](examples/ios-swift/)

## Development

```bash
python3 -m unittest discover tests
```

## License

MIT
