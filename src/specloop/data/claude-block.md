## Spec-driven development (specloop)

<!-- Paste this into CLAUDE.md for Claude Code, AGENTS.md for Cursor, or both. -->

- **The spec in `docs/spec/` is the source of truth** for what this project does. `docs/spec/README.md` is the overview and links to one doc per feature. Read the overview and the relevant feature docs before changing behavior.
- **Behavior changes start as spec changes**, normally a pull request against `docs/spec/`. Once it's merged and pulled, the specloop hook starts `/spec-sync` as a background session in its own worktree, on the machine of the person who wrote the spec change. Enable it per clone with `git config core.hooksPath tools/githooks`, and pick your agent with `git config specloop.harness claude` (or `cursor`). To skip it once, use `SPEC_SYNC=off`. `tools/specloop status` shows where each pending spec revision stands.
- `docs/.spec-implemented` holds the commit whose spec the code matches. Only `/spec-sync` advances it, or `tools/specloop mark` after a hand-made spec+code commit.
- Tests name the spec IDs they check at the start of their name, e.g. `@Test("XP-6: …")`. `tools/specloop coverage` reports which IDs have tests and fails on IDs the spec doesn't define.
- Any direct code change that alters behavior must update the spec in the same commit.
- **Every commit that changes code names its rules in trailers.** `tools/specloop trailers --rules ID,... --human` prints the block for a hand-written commit (or `--model <id>` instead of `--human` for an agent session); paste it at the end of the message. A commit no rule covers says why: `Spec-Rules: none (deps)`. Use `none (format)`, `none (rename)` or `none (move)` for changes that only move code, so `specloop blame` looks past them.
- **Feedback about the code is a signal.** For a crash, a failing test, a QA report or a review comment, run `/spec-triage` to trace it to its rules and harness and find which layer to fix. A commit that fixes one says so with `Fixes-Signal: <id>` (`trailers --fixes <id>`), which closes it once the commit is on the default branch. `tools/specloop status` counts the open ones.

### Spec sync rules for this project

<!-- Checks /spec-sync must apply here on top of its generic steps, e.g. "threshold changes need eval numbers", "don't bump the version", "update store copy". Delete this section if there are none. -->
