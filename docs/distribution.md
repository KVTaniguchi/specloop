# Distribution and updates

> Status: built (October 2026), not yet released. The first release is cut with `scripts/release 0.1.0`, which prints the publishing steps.

specloop reaches a project today by `install.sh` copying the CLI, the git hooks and the skills into it. Updates arrive only when someone runs the installer again and commits the result. KTCatPokemon has three commits titled "Upgrade specloop to <sha>", each re-copying the same files by hand. Nothing tells anyone an update is waiting, and the version a project runs is recorded only in a commit message.

That works for one person. specloop is meant to be an open-source project anyone can adopt, so it needs to update the way developer tools normally do: a version number, a package manager, and release notes.

## Decisions

These came from the project's owner:

- **Anyone can use it.** Consumers aren't only iOS apps. The CLI is plain Python with no dependencies, and the test tags cover Swift, JS and Python.
- **Installed per machine through a package manager.** On a Mac that's Homebrew. Someone working on an iOS project updates specloop the way they update their other tools.
- **The higher version wins.** A project declares the **minimum** specloop version it needs. A machine with a newer version runs the newer one. The project doesn't pin an exact version.
- **An older version warns but runs, for people.** If the installed specloop is below the project's minimum, every command prints a warning and carries on.
- **A sync stops instead.** An agent doesn't build code from instructions older than the project relies on. Below `minVersion`, `/spec-sync` records itself as blocked and builds nothing (see [The minimum version](#the-minimum-version)).
- **specloop manages its own part of `CLAUDE.md` / `AGENTS.md`.** `init` and `update` keep it current inside markers. Everything outside them, the project's sync rules included, is never touched.

## Goals

- One install per machine (`brew install`, or `pipx install` off a Mac), and updates through that package manager (`brew upgrade`).
- Nothing the project commits goes stale when specloop is upgraded. The newer version's hooks, CLI and skill instructions are what run.
- A project states the minimum version it relies on, in a file it commits and reviews.
- Released versions with numbers and release notes, so a user can tell what changed and what they're running.
- Moving an existing project (KTCatPokemon) over takes one command and leaves its spec, ledger, signals and project rules alone.

## Non-goals

- **A Swift package.** A Swift Package Manager dependency pins one version per project and can't be overridden by a newer version on the machine, which contradicts "higher wins". Command plugins also run sandboxed and need extra flags to write to the project. It could be added later as an alternative way to install, not the main one.
- **npm, Mint, or other package managers.** Homebrew and PyPI cover macOS and everyone with Python. Others can wrap the PyPI package.
- **Checking for updates over the network.** `brew outdated` and `pipx list --outdated` already do that. specloop never phones home.
- **Updating itself.** Upgrading is the package manager's job.

## Anti-goals

The design has failed, even if it works, if any of these happen:

- **A commit or merge is blocked because specloop is missing or old.** Hooks must never fail a git command. A missing or old CLI gets a one-line message, and the commit or merge goes through.
- **Running a command leaves surprise changes in the working tree.** Only `specloop init` and `specloop update`, both run on purpose, write project files.
- **A newer specloop misreads a project made by an older one.** "Higher wins" only works if every release still reads every earlier project's files.
- **A project's own instructions get overwritten.** Only what's between specloop's markers in `CLAUDE.md` / `AGENTS.md` belongs to specloop. The rest, including "Spec sync rules for this project", is the project's.

## What the project keeps

After the change, a project commits only thin files that defer to the installed specloop:

| Path | Today | After |
|---|---|---|
| `tools/specloop` | The whole CLI (about 1,900 lines) | A shim that finds the installed `specloop` and runs it with the same arguments |
| `tools/githooks/*` | The trigger script (about 160 lines) plus the four hooks | Shims that run `specloop hook <name>` |
| `.claude/skills/*/SKILL.md` | Full instructions | A stub that has the agent run `specloop skill <name>` and follow its output |
| `specloop.json` | Config | Config plus `"minVersion"` |
| `CLAUDE.md` / `AGENTS.md` | A section pasted by hand from `templates/CLAUDE.md` | The same section between specloop's markers, kept current by `init` and `update` |
| `docs/spec/`, the ledger, `docs/signals/` | Unchanged | Unchanged |

The trigger's logic moves into the CLI as `specloop hook commit|merge|rebase|commit-msg`. The shell hooks keep only finding the CLI and passing along their arguments.

### Finding the CLI

Git GUIs, Xcode's source control among them, run hooks with a minimal `PATH` that often leaves out Homebrew. So the shims look in `PATH`, then `/opt/homebrew/bin`, `/usr/local/bin` and `~/.local/bin` (where pipx installs), in that order. The shims stay plain `sh`.

If none is found:
- **A hook** prints `specloop: not installed (brew install …); skipping` once and exits 0. The commit goes through.
- **`tools/specloop`** prints the same message with install instructions and exits non-zero, because a person or agent asked for it directly.

### Skills as stubs

A stub keeps the frontmatter that tells Claude Code and Cursor when to use the skill (`name`, `description`). Its body tells the agent to run `specloop skill spec-sync` and follow what it prints. The installed CLI carries the full skill text, so a newer specloop brings newer instructions with no copied file to refresh. Cursor reads `.claude/skills/` too, so this covers both agents.

The full text starts with a line naming the specloop version, so a session's transcript shows which instructions it followed.

A stub's `description` can still go stale if a release changes when a skill should be used. `specloop update` rewrites stubs whose frontmatter differs from the installed version's.

### specloop's block in `CLAUDE.md` / `AGENTS.md`

specloop's instructions for agents live between two markers:

```
<!-- specloop:begin (managed by specloop update; edits here are replaced) -->
…
<!-- specloop:end -->
```

- `init` adds the block to `CLAUDE.md` (Claude Code) or `AGENTS.md` (Cursor), creating the file if there isn't one. It goes at the end, with an empty "Spec sync rules for this project" section after it, outside the markers, if the file has none.
- `update` replaces only what's between the markers. If someone edited the inside, it prints the diff before replacing it, so a rule added in the wrong place can be moved out.
- Everything outside the markers is the project's and is never changed.
- The block is hashed into `Harness-Rev` as `claude-md@<hash>` today. With the block managed, that hash covers only the project's own part of the file (everything outside the markers). The block's own version is already covered by `specloop@X`.

## Versions

- **Semantic versioning, starting at 0.1.0.** Releases are git tags (`v0.1.0`) with a section in `CHANGELOG.md`. `specloop --version` prints the version.
- **Compatibility from the first release.** Every release reads `specloop.json`, the spec format, the ledger, sync records, signal records and trailers as any earlier release wrote them. When a format has to change, the new version keeps reading the old form. A project is never migrated without `specloop update` being run.
- **A fixture per release.** The test suite keeps a small project created by each released version and runs the current CLI against all of them (`status`, `check`, `coverage`, `pending`). This is what enforces the compatibility promise.
- **Older versions tolerate newer files.** Under warn-and-run, a teammate below `minVersion` still writes sync records, signals, trailers and the ledger. So every release, starting with 0.1.0, ignores config keys, record fields and trailer keys it doesn't know, and **keeps them** when it rewrites a record or config, instead of dropping them. *(Builder's call, made in review.)*
- **Trailers record the version.** In `Harness-Rev`, `specloop@0.3.0` **replaces** the `spec-sync@<hash>` entry, because a stub's hash would never change. The `claude-md@<hash>` entry stays, since `CLAUDE.md` is still the project's. `signals --by harness` treats old-style and new-style values as separate groups and doesn't try to line them up. This closes one of the open questions in [attribution.md](attribution.md): the specloop version shapes what a sync does as much as the skill files do. *(Builder's call, made in review.)*
- **Fixing the harness moves upstream.** With skill text in the package, a confirmed `harness/skill` pattern becomes an issue or PR against specloop, not an edit in the project. A project's own fixes go in its "Spec sync rules for this project" section, which is what that section is for. There's no local override of a skill. A full skill file that `update` keeps because it was edited locally is a fork: it stops getting updates, and `update` and `status` say so every time. `/spec-triage` and attribution.md change to match. *(Builder's call, made in review.)*

### The minimum version

`specloop.json` gets a top-level `"minVersion": "0.3.0"`.

- `specloop init` sets it to the installed version.
- `specloop update` raises it to the installed version, alongside refreshing the shims and stubs. Committing that change is how a project says it relies on that version, and teammates see it in review.
- Every command compares the installed version with `minVersion`. If it's lower, it prints to stderr: `specloop 0.2.1 is older than this project's minimum 0.3.0; upgrade with brew upgrade specloop` (or the pipx equivalent, depending on how it was installed), and carries on. `specloop status` shows the same line at the top.
- A project with no `minVersion` gets no warning.

**Syncs stop.** People get a warning, but an agent building code doesn't go ahead with older instructions:
- Below `minVersion`, `specloop skill spec-sync` prints, instead of the skill, a short instruction to record the sync as blocked and stop. It exits non-zero.
- The sync is recorded with `sync blocked` and a note naming both versions and the upgrade command. `status` shows it as `blocked: specloop 0.2.1 < 0.3.0`.
- Nothing is built and no signal is recorded, because nothing is wrong with the spec or the code.
- The hook doesn't launch a sync at all when the installed version is below the minimum. It prints the same line and exits 0, so the commit or merge goes through. Once specloop is upgraded, `/spec-sync` or the next spec commit picks the revision up.
- Other skills (`/spec-init`, `/spec-triage`) warn and run, like the CLI. Only building code stops.

## Packaging

- **A Python package.** `bin/specloop` becomes a package with the CLI as its entry point. The skill texts, hook shims, `templates/` and the `CLAUDE.md` template ship as package data. Standard library only, Python 3.8+, as today.
- **PyPI**, so `pipx install specloop` and `uvx specloop` work on any machine.
- **A Homebrew tap**, `KVTaniguchi/homebrew-tap`, with a `specloop` formula. `brew install KVTaniguchi/tap/specloop`. Getting into Homebrew core can come later, once the project has enough users for core's notability bar.
- **`install.sh`** stays for people who'd rather not use a package manager. It installs the CLI from the checkout into `~/.local/bin` and then runs `specloop init` on the target project.

## Commands

| Command | What it does |
|---|---|
| `specloop init [path]` | Writes the shims, skill stubs, `specloop.json` (if missing, with `minVersion`), specloop's block in `CLAUDE.md` / `AGENTS.md`, and starter spec templates (if there's no spec). Replaces `install.sh`'s copying. Never overwrites an existing spec or config, or anything in `CLAUDE.md` outside the markers |
| `specloop update` | Rewrites the shims, stubs and `CLAUDE.md` block where they differ from the installed version's, raises `minVersion`, and prints what changed and the release notes since the old `minVersion`. Leaves everything for the user to review and commit |
| `specloop hook <name>` | What the git hooks run: the trigger and the trailer check |
| `specloop skill <name>` | Prints a skill's full instructions for the installed version |
| `specloop --version` | The installed version |

## Moving an existing project over

KTCatPokemon has a full copy of the CLI, the hooks and the skills. Running `specloop update` (or `init`) there:

- recognizes an unedited copy of the CLI or trigger and replaces it with the shim. If the copied CLI was edited, it changes nothing at all and says why: the new hooks and stubs need the shim, and switching them to a CLI that can't run them would block every commit
- replaces full skill files with stubs. If a skill file was edited locally, it prints the diff against the last copied version and keeps the local file, so nothing is lost
- adds `minVersion` to `specloop.json`, leaving every other key as it is
- finds the section pasted from `templates/CLAUDE.md` (it has no markers yet), shows the diff, and wraps the current text in markers. Anything the project added inside that section is shown so it can be moved below the markers first
- leaves the spec, the ledger, `.git/specloop/`, `docs/signals/` and the rest of `CLAUDE.md` untouched

The upgrade becomes one reviewed commit, like the three by hand before it, but small.

## CI

`docs/ci.md` runs `tools/specloop check` from the copy committed in the repo. After the move that's a shim, so CI needs a step that installs specloop first. It installs **exactly `minVersion`** (`pipx install specloop==<minVersion>`, read from `specloop.json`), so the result of a gating check changes only when a project commit changes the minimum. "Higher wins" is about people's machines. CI has no installed version for anything to beat. specloop can ship a small GitHub Action that does this, and `ci.md` is rewritten around it. *(Builder's call, made in review.)*

## Releasing

Each release:
1. Update `CHANGELOG.md` and the version.
2. Tag `vX.Y.Z` and push the tag.
3. Publish to PyPI.
4. Update the tap's formula (URL and `sha256`).
5. Add the release's compatibility fixture.

These steps publish under the owner's accounts. Whether they run from a script the owner runs or from a GitHub Action on tags is left to the builder. Either way, the first release is cut by the owner.

## Left to the builder

- The package layout and how the existing tests find the CLI.
- The formula's style (a virtualenv formula, or installing the script and data directly).
- Exact wording of messages and the stub text.
- How `update` recognizes an older copied install, as long as it never replaces a file it doesn't recognize without showing the diff.

## Open questions

- ~~**Is `specloop` free on PyPI?**~~ Checked 2026-10-30: it is.
