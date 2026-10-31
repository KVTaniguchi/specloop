# A Claude Code plugin

> Status: design, not built. Nothing here changes how specloop installs today until the task list at the end is done.

Today a Claude Code user meets specloop's skills only after two steps outside Claude Code: `brew install KVTaniguchi/tap/specloop`, then `specloop init` in the project, which writes skill stubs into `.claude/skills/`. Popular tools in the same space (GSD Core, SwiftShip) install from inside Claude Code instead, with `/plugin marketplace add` and `/plugin install`. SwiftShip, for example, publishes its `apple` plugin through a separate marketplace repository (`rshankras/claude-code-apple-skills`, marketplace name `indie-apple-stack`) and tells users to run `/plugin install apple@indie-apple-stack`. That's the install Claude Code users expect.

This doc decides how specloop's skills (`/spec-sync`, `/spec-init`, `/spec-triage`) ship as a Claude Code plugin, while the CLI stays a Homebrew install. It follows [distribution.md](distribution.md) and doesn't revisit its decisions.

## Decisions

These are given:

- **The CLI stays a Homebrew install.** `brew install KVTaniguchi/tap/specloop`. specloop isn't on PyPI and won't be.
- **The design in [distribution.md](distribution.md) holds.** Projects keep thin files that defer to the installed CLI, `minVersion` gates syncs, and a newer CLI brings newer instructions with no copied file to refresh.

These are this doc's, with reasons below:

1. **The plugin sits alongside the project's skill stubs. It doesn't replace them.** `specloop init` and `specloop update` keep writing `.claude/skills/*/SKILL.md` exactly as today.
2. **The plugin's skills are stubs too.** Each one runs `specloop skill <name>` and follows what it prints, so the skill text still comes from the installed CLI, and the `minVersion` gate stays where it is.
3. **Cursor is unaffected**, because of 1.
4. **The marketplace lives in the specloop repository itself**, and `scripts/release` bumps the plugin's version in the same release commit as the CLI's.

## Goals

- A Claude Code user can go from nothing to a running `/spec-init` with `brew install`, `/plugin marketplace add`, `/plugin install`, and the skill itself, without first knowing about `specloop init`.
- Nothing a project commits changes because someone on the team uses the plugin.
- The skill instructions an agent follows are always the installed CLI's, whichever way the skill was invoked. One version number answers "what did this sync follow".
- A release publishes the plugin with no step beyond what `scripts/release` already prints.

## Non-goals

- **Shipping the CLI inside the plugin.** The plugin needs Python and the CLI on the machine either way, and Homebrew is how they get there. A plugin that bundled the CLI would be a second install path with its own version, which is the skew this design avoids.
- **Submitting to Anthropic's plugin directory.** Possible later, once the plugin has been used for a while. It doesn't change anything here.
- **A plugin for Cursor.** Cursor doesn't load Claude Code plugins.
- **Managing the plugin from the CLI.** `specloop init` doesn't install the plugin, and `specloop update` doesn't update it. Those are Claude Code's `/plugin` commands.

## Anti-goals

The design has failed, even if it works, if any of these happen:

- **A sync follows instructions from a different version than the CLI it runs.** Every step of `/spec-sync` calls `tools/specloop`. Instructions from plugin 0.4 driving CLI 0.2 would name commands and flags that don't exist.
- **A teammate without the plugin, or on Cursor, loses a skill.** Installing the plugin is one person's choice on one machine. A project can't depend on it.
- **Installing the plugin writes into a project.** Only `specloop init` and `specloop update` write project files, both run on purpose ([distribution.md](distribution.md#anti-goals)).
- **The `minVersion` gate can be bypassed by picking the other `/spec-sync`.**

## What the plugin contains

```
.claude-plugin/marketplace.json        the marketplace, at the specloop repository's root
plugin/
  .claude-plugin/plugin.json           name "specloop", version = the CLI's
  skills/spec-sync/SKILL.md            frontmatter from the packaged skill + the plugin stub
  skills/spec-init/SKILL.md
  skills/spec-triage/SKILL.md
  hooks/hooks.json                     SessionStart → scripts/session-start
  scripts/session-start                plain sh; read-only
```

The plugin is named `specloop`, so its skills are `/specloop:spec-sync`, `/specloop:spec-init` and `/specloop:spec-triage`. Claude Code prefixes every plugin skill with the plugin's name. Unlike SwiftShip, which names its plugin `apple` to get `/apple:*` commands, specloop keeps its own name: the prefix is what tells a user which `/spec-sync` came from where.

### The plugin's skill stubs

A plugin skill has the same frontmatter (`name`, `description`) as the packaged skill, generated from `src/specloop/data/skills/*/SKILL.md` the same way `render_stub` does. Its body differs from the project stub in `src/specloop/data/stub.md` in one way: it can't assume the project has `tools/specloop`, because the plugin is installed per machine and may be used in a project that has never run `specloop init`. So the body says, in order:

1. If the project has `tools/specloop`, run `tools/specloop skill <name>` and follow what it prints. This is exactly the project stub's path.
2. Otherwise, run `specloop skill <name>` (looking in `PATH`, then `/opt/homebrew/bin` and `/usr/local/bin`, as the shim does) and follow what it prints.
3. If neither is found, tell the user specloop isn't installed and give `brew install KVTaniguchi/tap/specloop`. Don't improvise the skill.

The plugin stub carries the same `<!-- specloop stub -->` marker as the project stub, so anything that greps for it (`forks`, `classify`) treats both the same.

**`/specloop:spec-init` in a project with no `specloop.json`.** The packaged `spec-init` text already expects a set-up project. When the plugin stub finds no `specloop.json` and no `tools/specloop`, it asks the user before running `specloop init`, then carries on. Asking keeps `init` something a person chose to run. This is the plugin's onboarding path: `brew install`, `/plugin install`, `/specloop:spec-init`.

### The session-start hook

The one thing a plugin can do that a stub file can't is run when a session starts. `scripts/session-start`:

- exits 0 silently unless the session's directory has a `specloop.json` (searching upward, as `find_root` does), so it costs nothing in other projects
- if the CLI isn't found, adds one line of context: specloop isn't installed, and the `brew install` command
- otherwise runs `specloop version-ok` and, if it fails, adds its message (`specloop 0.2.1 is older than this project's minimum 0.3.0; upgrade with brew upgrade specloop`) as context
- never writes anything, never fails the session (always exits 0), and finishes fast, since `version-ok` reads one file

This puts the warning in front of the agent before anyone types `/spec-sync`, instead of only when the sync stops. It's advisory: the gate itself stays in the CLI (below).

## 1. Alongside the project stubs, not instead of them

The plugin can't replace `.claude/skills/` stubs, for three reasons, any one of which is enough:

- **Cursor reads the project stubs.** It reads `.claude/skills/` and doesn't load Claude Code plugins (section 3).
- **The hook names the project skill.** The trigger starts Claude Code with the prompt `/spec-sync …`, which resolves to the project skill, not `/specloop:spec-sync`. Its Cursor path tells the agent to follow `.claude/skills/spec-sync/SKILL.md` by path.
- **A project can't require a plugin.** Each person installs plugins on their own machine. A teammate who hasn't installed it (or the CI job, or a background session with different settings) would have no skills at all. A project can *suggest* the marketplace through `extraKnownMarketplaces` in its committed `.claude/settings.json`, but that's a prompt each person can decline, not a guarantee.

So **`specloop update` changes nothing about stubs.** It keeps writing and refreshing `.claude/skills/*/SKILL.md` as today, classified by `classify` as `current`, `thin`, `copy` or `edited`. An existing project needs no migration, and installing the plugin doesn't show up in `git status`.

**What a Claude Code user with the plugin sees** in a set-up project: both `/spec-sync` and `/specloop:spec-sync` (and the same for the other two). They're the same skill, reached two ways, and both run the installed CLI's `specloop skill spec-sync`. Since both descriptions are the same, Claude may auto-invoke either; it doesn't matter which. The README says so in one line. This duplication is the cost of the plugin, and it's cosmetic.

**What the plugin adds**, given that it doesn't replace anything:

- An install that starts inside Claude Code, and the skills in a project before `specloop init` has been run.
- The session-start warning when the CLI is missing or below `minVersion`.
- Discovery in `/plugin`, and later, possibly, Anthropic's directory.

A future option, not part of this design, is a `specloop.json` setting that tells `init` and `update` not to write skill stubs, for teams that are all on Claude Code with the plugin. It would need the hook's Claude path to start `/specloop:spec-sync` instead, and it reintroduces "a project depends on a plugin". See open questions.

## 2. The minVersion gate

Today the gate is in `cmd_skill`: below `minVersion`, `specloop skill spec-sync` prints, instead of the skill, an instruction to record the sync as blocked and stop, and exits 1. Every `/spec-sync` passes through it because the stub's only instruction is to run that command.

**The plugin's skills run the same command, so the gate is unchanged.** Whether an agent starts from `/spec-sync`, `/specloop:spec-sync`, or the hook, it ends up running `specloop skill spec-sync` against the installed CLI, which compares its own version with `minVersion` and stops the sync if it's lower. There's no second gate to keep in step.

The alternative, putting the full skill text in the plugin, was rejected:

- The gate would have to move into the skill text ("first run `tools/specloop version-ok`; if it fails, stop"). That's an instruction the agent might skip, not a command that withholds the instructions.
- The plugin's version would be a second number, updated by `/plugin marketplace update` on its own schedule, independent of `brew upgrade`. A project can't declare a minimum plugin version: plugin dependency ranges are between plugins, not from a project. So `minVersion` would gate the CLI while the instructions came from something it doesn't cover. That's the first anti-goal.
- `Harness-Rev` records `specloop@<version>` because the CLI's version names the skill text exactly. With text in the plugin, a trailer would need both versions.

The plugin's frontmatter (the `description` that tells Claude when to use a skill) can still lag the CLI by a release. That's the same, already accepted, drift that project stubs have between `brew upgrade` and `specloop update`, and it changes only when a skill is offered, never what it does.

**The plugin's version** equals the CLI release it was cut with, so `/plugin` shows a number users recognize. It means "the stubs and hook as of that release", and nothing gates on it.

## 3. Cursor

Cursor reads `.claude/skills/` and not Claude Code plugins. Because the project stubs stay (section 1), Cursor users see no change at all: `specloop init` with `specloop.harness cursor`, the same stubs, the same `AGENTS.md` block, the hook's `agent -p` path reading `.claude/skills/spec-sync/SKILL.md`.

The README's install section keeps the Homebrew path as the one that works everywhere, and adds the plugin as an extra step for Claude Code users. A team with both Claude Code and Cursor users runs `specloop init` once and commits it, as today; the Claude Code users may also install the plugin.

## 4. Where the marketplace lives, and releasing

### The specloop repository is the marketplace

`.claude-plugin/marketplace.json` goes at the root of `KVTaniguchi/specloop`, with marketplace name `specloop`:

```
/plugin marketplace add KVTaniguchi/specloop
/plugin install specloop@specloop
```

The entry points at the plugin's directory in the same repository, pinned to the release tag:

```json
{
  "name": "specloop",
  "owner": { "name": "Kevin Taniguchi" },
  "plugins": [
    {
      "name": "specloop",
      "description": "Keep an iOS app's spec, code and tests in lockstep. Needs the CLI: brew install KVTaniguchi/tap/specloop",
      "source": { "source": "git-subdir", "url": "https://github.com/KVTaniguchi/specloop.git", "path": "plugin", "ref": "v0.2.0" }
    }
  ]
}
```

Pinning to the tag means a new install between releases gets the released plugin, not whatever is on `main`. A plain relative source (`"./plugin"`) would install `main`'s copy, which may reference CLI features that aren't released yet. If a `git-subdir` source pointing back at its own marketplace repository turns out not to work, fall back to `"./plugin"` and accept that window; the plugin is stubs and a read-only hook, so what can go wrong in it is small.

Options considered:

| Where | For | Against |
|---|---|---|
| **`KVTaniguchi/specloop` (chosen)** | One repository to name in the README. The plugin's stubs are generated from the skill texts in the same tree, so a test can check they match, and CI covers them. The release commit bumps both versions together. The repo already doubles as a GitHub Action (`action.yml`) | Adding the marketplace clones the whole repository (small today). The marketplace changes only through a reviewed PR on protected `main`, which is also when the release lands |
| `KVTaniguchi/homebrew-tap` | Already the "distribution" repository, already edited by hand at release, not branch-protected | `/plugin marketplace add KVTaniguchi/homebrew-tap` reads oddly to Claude Code users. The plugin's files would be copies of generated files from another repository, with nothing testing they're current |
| A new `KVTaniguchi/claude-plugins` | The SwiftShip pattern. Room for more plugins | A third repository to keep in step for one plugin. Worth it only if there's a second plugin |

Moving later is possible but costs users something: Claude Code identifies a marketplace by its `name`, so a move keeps the name `specloop` and users re-add it from the new place.

### `scripts/release`

`scripts/release` already sets `__version__` and refreshes packaged files before committing. It gains:

1. **Regenerate the plugin's files** from the packaged skills (a `scripts/plugin` step, like `scripts/known-copies`), so their frontmatter is the release's.
2. **Set the version** in `plugin/.claude-plugin/plugin.json` and the `ref` in `.claude-plugin/marketplace.json` to `v$version`, in the release commit, before tagging. The `ref` is a tag name, so the commit can name the tag that will point at it.

Nothing new runs under the owner's accounts. The plugin is published when the release PR merges to `main`, because that's where `/plugin marketplace update` reads `marketplace.json`. The printed steps get one line saying so.

The order matters only a little. The release PR merging (plugin live) and the tap's formula update (CLI live) happen in separate steps, so for a short time the plugin may be a release ahead of what `brew upgrade` gives. Because the plugin's skills only defer to the CLI, that window can't make a sync follow the wrong instructions. The worst case is a `description` one release newer than the CLI's.

**Updates for users.** Claude Code updates a plugin when its version changes, and background auto-update is off for third-party marketplaces until each user turns it on. Users get a new plugin with `/plugin marketplace update specloop`, the way they get a new CLI with `brew upgrade specloop`. The README says both. Since the plugin carries no instructions, a user who never updates it loses nothing important.

**CI.** A test checks the plugin's files are what the generator would write now (as the tests already do for `known-copies.json`), that `plugin.json`'s version equals `__version__`, and that the marketplace `ref` is `v` + `__version__`. If the `claude` CLI is available in CI, `claude plugin validate .` runs too; otherwise the JSON shape is checked in the test.

## Risks

- **Two names for every skill.** Users with the plugin see `/spec-sync` and `/specloop:spec-sync` in set-up projects. It's harmless but may confuse. Mitigation: one line in the README and in the plugin's description. If it turns out to bother people, the opt-out setting in the open questions removes the project copy.
- **The plugin without the CLI.** The marketplace makes it easy to install the plugin and skip `brew install`. Every stub and the session-start hook say what's missing and how to install it, and nothing is improvised, but the first experience is an install message. The plugin's description names the CLI as a requirement.
- **PATH in Claude Code's environment.** The desktop app and some launchers start Claude Code without Homebrew on `PATH`, the same problem git GUIs have with hooks. The plugin stub and hook search the same directories the shim does.
- **Self-referencing `git-subdir`.** Untested: whether a marketplace entry can point at a subdirectory of its own repository at a tag. Checked in the first implementation task; the fallback is a relative source.
- **Plugin features move.** Plugin hooks, skill namespacing and source types are newer than skills in `.claude/skills/`, and their behaviour may change. The design leans on them only where losing them is survivable: if the hook stopped running, the gate in the CLI still holds.
- **Marketplace name.** `specloop` is a plain name that someone else could also pick; a user can't add two marketplaces with the same name. Low risk, but the name is permanent once published.

## Open questions

- **Should a project be able to opt out of skill stubs?** A `specloop.json` key that stops `init`/`update` writing `.claude/skills/`, for Claude-Code-only teams that all use the plugin, and switches the hook's prompt to `/specloop:spec-sync`. It would break Cursor and plugin-less teammates for that project, so it's off by default and not in this design. Decide after the plugin has users.
- **Should `specloop init` suggest the plugin?** It could add `extraKnownMarketplaces` for `specloop` to the project's `.claude/settings.json`, so Claude Code offers the marketplace to each teammate when they trust the folder. That writes a file the project owns, so it would need to be opt-in. Not in the first version.
- **Should `/specloop:spec-init` run `specloop init` itself** after asking (as designed above), or only tell the user to? Asking is the friendlier onboarding; telling keeps `init` strictly a person's command. This doc picks asking; the owner may prefer telling.
- **Is the session-start hook worth it?** It's the plugin's one real addition beyond install. If hooks in plugins prove noisy or slow, the plugin can ship without it and nothing else changes.

## Tasks

1. Check that a `git-subdir` entry can point at `plugin/` in its own repository at a tag, with a throwaway marketplace on a test tag. Pick that or the relative source.
2. Add a plugin stub template next to `src/specloop/data/stub.md`, and a generator (`scripts/plugin`) that writes `plugin/skills/*/SKILL.md` from the packaged skills' frontmatter and that template.
3. Write `plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json` and `plugin/scripts/session-start` (plain `sh`, read-only, always exits 0).
4. Write `.claude-plugin/marketplace.json`.
5. Extend `scripts/release` to run the generator and set the plugin version and marketplace `ref`; add the "published when the release PR merges" line to its printed steps.
6. Tests: generated plugin files are current; versions and `ref` match `__version__`; the session-start script exits 0 and stays silent outside a specloop project, with no CLI, and with a CLI below `minVersion` (where it prints the gap).
7. README: under Install, a "Claude Code plugin (optional)" step after `brew install`; under Updating, `/plugin marketplace update specloop`; one line explaining `/spec-sync` vs `/specloop:spec-sync`. A CHANGELOG entry.
