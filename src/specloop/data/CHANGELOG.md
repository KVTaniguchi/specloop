# Changelog

## 0.1.0

- specloop installs once per machine (`brew install KVTaniguchi/tap/specloop` or `pipx install specloop`) and is updated by that package manager.
- A project keeps thin files that defer to the installed version: `tools/specloop`, the git hooks and the skill stubs. `specloop init` writes them and `specloop update` refreshes them.
- `specloop.json` has a `minVersion`. Below it, commands warn and run, and `/spec-sync` stops.
- specloop manages its own block in `CLAUDE.md` / `AGENTS.md`, between markers.
- `Harness-Rev` names the specloop version.
