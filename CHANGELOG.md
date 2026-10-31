# Changelog

## 0.1.2

- `specloop doctor` checks a project's setup: the installed version against `minVersion`, `specloop.json` and its test command, the test paths, the spec and ledger, the project's specloop files, the trigger, whether git GUIs can find specloop, the agent CLI's login, Claude Code's folder trust, and leftover sync worktrees. Each problem comes with its fix; it exits 1 when one stops syncs from working.
- README and docs: a plain-language intro, highlights, uninstall steps and a troubleshooting guide.

## 0.1.1

- The CI action installs specloop from its GitHub release tag instead of PyPI, where specloop isn't published. Workflows pinned to `KVTaniguchi/specloop@v0.1.0` failed to install; pin `@v0.1.1`.
- Install hints (the shim's "not installed" message, `/spec-init`, `install.sh`) name Homebrew only.
- The README is about iOS projects, and opens with a demo.

## 0.1.0

- specloop installs once per machine (`brew install KVTaniguchi/tap/specloop` or `pipx install specloop`) and is updated by that package manager.
- A project keeps thin files that defer to the installed version: `tools/specloop`, the git hooks and the skill stubs. `specloop init` writes them and `specloop update` refreshes them.
- `specloop.json` has a `minVersion`. Below it, commands warn and run, and `/spec-sync` stops.
- specloop manages its own block in `CLAUDE.md` / `AGENTS.md`, between markers.
- `Harness-Rev` names the specloop version.
