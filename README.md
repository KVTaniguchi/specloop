# specloop

[![test](https://github.com/KVTaniguchi/specloop/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/KVTaniguchi/specloop/actions/workflows/test.yml)
[![release](https://img.shields.io/github/v/release/KVTaniguchi/specloop)](https://github.com/KVTaniguchi/specloop/releases)
[![license](https://img.shields.io/github/license/KVTaniguchi/specloop)](LICENSE)

**Keep an iOS app's spec, its code and its tests in lockstep, with Claude Code or Cursor doing the implementation.**

![A spec change to the iOS example: the commit hook queues a sync, and status shows XP-1 pending](docs/demo.gif)

*The [iOS example](examples/ios-swift/), with the trigger in dry-run mode. A real commit starts a background Claude Code session that builds XP-1 on a review branch.*

**Spec drift** is what happens once a coding agent writes most of your app: the code moves fast, the spec stops describing it, and soon nobody can say which rules the code actually follows. specloop stops the drift.

In plain terms: you write down how your app should behave, in ordinary Markdown. When you change that description, an AI coding agent updates the code and tests to match, and hands you the result to review. specloop keeps track of which version of the description the code matches, so the two can't quietly fall apart.

| Building a house | specloop |
|---|---|
| The blueprint | The spec: Markdown docs in `docs/spec/`, one bold ID per rule |
| A change order | A pull request against the spec |
| The contractor | A background Claude Code or Cursor agent |
| The work, waiting for your walkthrough | The `spec-sync/<sha>` review branch |
| The inspection checklist | Tests tagged with rule IDs, and `specloop coverage` |
| The signed-off inspection | The ledger, `docs/.spec-implemented`: the spec revision the code matches |

## Highlights

- **Built for iOS.** Swift Testing and XCTest tags, your `xcodebuild` test command, and a worked [iOS example](examples/ios-swift/).
- **Your spec, your shape.** Plain Markdown in git, organized however you like. specloop only needs bold rule IDs.
- **Starts from the app you have.** `/spec-init` drafts the spec from your existing code and tags the tests you already have.
- **Builds in the background.** A spec change starts an agent in its own worktree, on a branch for you to review. Your checkout isn't touched.
- **Every rule has a test, or you know it doesn't.** `specloop coverage` maps rules to tests, and `specloop check` fails CI when the spec and the code drift apart.
- **Traceable.** Every commit names the rules it built, so `specloop blame` and `/spec-triage` take a crash or failing test back to its rule.
- **Safe for teams.** By default only the author of a spec change builds it, so nobody's agent duplicates anyone else's work.
- **No telemetry.** specloop makes no network calls. One `brew install`, and `specloop update` keeps projects current.

## A rule and its test

Your app's behavior is described by a tree of Markdown docs in git: an overview at the top that links to one doc per feature. To change the app you open a pull request against the spec, not the code. Once it's merged and you pull, a background agent on your Mac builds the change on a review branch, writes Swift tests tagged with the rules they check, and records which spec revision the code now matches. The spec stays a *stateful* source of truth: it always describes what the app actually does.

A rule in the spec:

```markdown
- **XP-2:** When the player relabels a catch, they earn the XP of the scanner's result, not of the breed they picked.
```

The test the agent writes for it names the rule:

```swift
@Test("XP-2, XP-3: relabeling keeps the scanner's XP")
func relabelKeepsScannerXP() { … }
```

`specloop coverage` maps every rule to its tests, and `specloop blame` follows a failing test or a crash back to the rule and the commit that built it.

> Status: early. Built for iOS projects (Swift Testing or XCTest, run with `xcodebuild`) and extracted from one shipped SwiftUI app in October 2026. See [docs/lessons.md](docs/lessons.md) for what's been learned so far, including what hasn't been proven yet. See [examples/ios-swift](examples/ios-swift/) for a trimmed-down setup.

## Why another spec-driven tool?

Tools like GitHub Spec Kit, Kiro, [GSD](https://github.com/open-gsd/gsd-core) and, for Apple apps, [SwiftShip](https://github.com/rshankras/SwiftShip) take you from a spec or an idea to a plan to code. specloop doesn't replace them. It handles what happens **after** the code exists, when the spec has to stay true. Use them to build a feature, and specloop to keep it from drifting:

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

## What runs on your machine

specloop starts coding agents from a git hook, so here is exactly what it does:

- **Nothing runs until you turn it on.** The trigger is off until you set `core.hooksPath` in your clone. `SPEC_SYNC=off` skips it for one commit, and `SPEC_SYNC=dry-run` shows what it would start.
- **It only builds your own changes.** By default the hook builds spec changes you wrote, not every change you pull.
- **Your checkout isn't touched.** The agent works in its own worktree, on a `spec-sync/<sha>` branch. You review that branch and merge it.
- **Nothing is pushed for you.** The agent is instructed not to push or merge. That is an instruction to the agent, not a hard block, so it runs with your harness's permission settings: Claude Code's `auto` mode by default (`sync.permissionMode` in `specloop.json`), or Cursor's `agent --force`.
- **specloop never phones home.** The CLI makes no network calls: no telemetry, no update checks. The only network traffic is your coding agent's own.
- **A missing specloop never fails a commit.** If it isn't installed, the hooks print a note and step aside.

## Install

Requirements: a Mac with Xcode and git, and a coding agent for the skills and trigger: [Claude Code](https://claude.com/claude-code), or [Cursor](https://cursor.com) with its `agent` CLI.

Install specloop once per machine:

```bash
brew install KVTaniguchi/tap/specloop
```

Without Homebrew, clone this repository and run `install.sh`, which links `~/.local/bin/specloop` to the checkout and sets up the project in one go.

Then set it up in each project:

```bash
cd /path/to/your/project
specloop init
```

This writes small files that run whatever specloop is installed on the machine, so upgrading specloop never leaves stale copies behind. It never overwrites a spec or config you already have:

| File | Purpose |
|---|---|
| `tools/specloop` | Runs the installed CLI: `status`, `pending`, `coverage`, `check`, `mark`, `sync`, `trigger`, `config`, and for feedback `trailers`, `blame`, `signal`, `signals`. It looks in `PATH`, then Homebrew's and pipx's directories, because git GUIs run hooks with a short `PATH` |
| `tools/githooks/` | `post-commit`, `post-merge` and `post-rewrite` start `/spec-sync` when the spec changes. `commit-msg` checks trailers, if you turn it on. A missing specloop never fails a commit |
| `.claude/skills/spec-sync/` | Builds a pending spec diff. Cursor reads `.claude/skills/` too, so `/spec-sync` works in both. Like the other skills, it's a stub that runs `tools/specloop skill spec-sync` for the installed version's instructions |
| `.claude/skills/spec-init/` | Drafts the first spec from existing code |
| `.claude/skills/spec-triage/` | Traces a crash, failing test, QA report or review comment to its rules and harness, and proposes which layer to fix |
| `CLAUDE.md` / `AGENTS.md` | specloop's instructions for agents, between `<!-- specloop:begin -->` and `<!-- specloop:end -->` markers, followed by a "Spec sync rules for this project" section that's yours |
| `specloop.json` | Spec path, test dirs and tag styles, test command, and `minVersion`, the oldest specloop the project relies on |
| `docs/spec/` | Overview and feature templates, only if you don't have a spec |

Then follow [Your first sync](docs/first-sync.md) for a walkthrough, or in short:
1. Fill in `specloop.json`, especially `commands.test` and `tests.paths`.
2. In Claude Code or Cursor, run `/spec-init`. It drafts the spec from the code as it is today, tags existing tests, and records the baseline.
3. **Enable the trigger (optional).** The hook starts background Claude Code agents that edit code on their own, so this step is a deliberate opt-in. Claude Code's safety checks may ask you to confirm. Without it, run `/spec-sync` yourself after committing a spec change.
   ```bash
   git config core.hooksPath tools/githooks
   ```
   Each person picks their own agent for their clone. Claude Code is the default:
   ```bash
   git config specloop.harness cursor
   ```
   **Claude Code:** background sessions need two things the desktop app doesn't give the command-line `claude`: the project folder must be trusted (run `claude` in it once and accept the prompt), and the CLI must be logged in (`claude auth status`, then `claude auth login` if needed). **Cursor:** install the `agent` CLI and log in (`agent login`). The hook runs `agent -p --force --trust` in a worktree at `.specloop/worktrees/spec-sync-<sha>`, with its output in `.git/specloop/logs/<sha>.log`.
   Test the hook without launching anything with `SPEC_SYNC=dry-run git commit …`.
4. **If GitHub squash-merges your PRs under a noreply address**, tell specloop it's you, so the trigger knows the change is yours to build:
   ```bash
   git config --add specloop.email 12345+you@users.noreply.github.com
   ```

## Updating

```bash
brew upgrade specloop        # or: git pull, for an install.sh checkout
specloop update              # in each project, then review and commit
```

Upgrading changes what runs on your machine at once: the shims find the new version, and the skills print its instructions. `specloop update` brings the project's own files along: the shims and stubs, specloop's block in `CLAUDE.md`, and `minVersion`, which it raises to the installed version so teammates know the project relies on it. It prints the release notes since the old minimum, and never commits.

If your specloop is older than a project's `minVersion`, commands warn and still run, but `/spec-sync` stops and the hook doesn't start a sync, so no agent builds from older instructions than the project expects.

**Moving over from a copied install:** projects set up by the old `install.sh` have full copies of the CLI, hooks and skills. `specloop update` recognizes unedited copies and replaces them with the small files. A file you edited is kept, with a diff, and `status` keeps pointing it out. The old trigger is removed, and the section pasted into `CLAUDE.md` is put between markers, leaving your "Spec sync rules for this project" alone.

## Uninstall

**Turn the trigger off** in a clone, and nothing starts agents any more:

```bash
git config --unset core.hooksPath
```

**Remove specloop from a project.** Clear out finished syncs first with `tools/specloop cleanup`, then delete what `specloop init` added and commit:
- `tools/specloop` and `tools/githooks/`
- `.claude/skills/spec-sync/`, `.claude/skills/spec-init/` and `.claude/skills/spec-triage/`
- specloop's block in `CLAUDE.md` / `AGENTS.md`, from `<!-- specloop:begin` to `<!-- specloop:end -->`
- `specloop.json`, the ledger `docs/.spec-implemented`, and `docs/signals/` if you used signals

Your spec is yours: `docs/spec/` is plain Markdown and stays useful without specloop, and so do the rule IDs in your test names. Local state lives in `.git/specloop/` and goes when you delete it or the clone.

**Remove it from your Mac:**

```bash
brew uninstall specloop && brew untap KVTaniguchi/tap
```

For an `install.sh` setup, delete the `~/.local/bin/specloop` link instead.

## Day to day

| You want to… | Do this |
|---|---|
| Change behavior | Open a PR against `docs/spec/`, merge it, pull. Then review the `spec-sync/…` branch your agent made, and push it as a code PR |
| Build someone else's spec change | `/spec-sync` (the hook leaves it to its author; `status` says whose it is) |
| Build every spec change you pull | `"trigger": "all"` under `sync` in `specloop.json` |
| Skip the trigger once | `SPEC_SYNC=off git commit …` |
| Check the setup | `tools/specloop doctor`: config, tests, hooks, agent login and folder trust, each with its fix |
| See what's pending | `tools/specloop status` (each pending revision: not started, running, awaiting review, blocked, failed) / `tools/specloop pending` |
| Hotfix code directly | Change code **and** spec in one commit (`SPEC_SYNC=off`), then `tools/specloop mark` |
| Check test coverage | `tools/specloop coverage` (`--uncovered`, `--require XP,LVL`) |
| Watch a running sync | `tools/specloop status`; Claude Code: `claude agents`, `claude attach "Spec sync <sha>"`; Cursor: `tail -f .git/specloop/logs/<sha>.log` |
| Review a sync locally | `cd .claude/worktrees/spec-sync-<sha>` (Claude Code) or `.specloop/worktrees/spec-sync-<sha>` (Cursor); its branch is checked out there |
| Clean up sync worktrees | Automatic after a merge; `tools/specloop cleanup` ([details](docs/ci.md#cleaning-up-worktrees)) |
| Gate CI on the spec | `tools/specloop check --trailers <range>` ([CI setup](docs/ci.md)) |
| Commit code by hand | End the message with `tools/specloop trailers --rules XP-6 --human`, or `--none deps` |
| Find what built a line | `tools/specloop blame src/xp.swift:42` (also `--test`, `--rule`, `--commit`) |
| Report a crash, bug or review comment | `/spec-triage` with the evidence; `tools/specloop status` counts open ones, `signals` lists them |
| Close a signal | Commit the fix with `Fixes-Signal: <id>` (`trailers --fixes <id>`); it closes once on the default branch |
| See whether a harness change helped | `tools/specloop signals --by harness` |

## Docs

- [Your first sync](docs/first-sync.md): from install to a reviewed sync branch on your own app
- [Troubleshooting](docs/troubleshooting.md): what to do when a sync doesn't start, stalls or fails
- [Writing a spec](docs/spec-format.md): the tree, IDs, good rules, tagging tests in each framework
- [Sensors and CI](docs/ci.md): how syncs are tracked and cleaned up, and `specloop check` in GitHub Actions
- [Attribution and feedback](docs/attribution.md): commit trailers, blame, signals and triage
- [Distribution and updates](docs/distribution.md): installing per machine, the minimum version, and moving projects over
- [Lessons](docs/lessons.md): what happened on a real project
- [Measuring it](docs/measurement.md): how to tell whether the spec route pays off, and what to change if it doesn't
- [Example: iOS / Swift](examples/ios-swift/)

## Development

```bash
python3 -m unittest discover tests
```

## License

MIT
