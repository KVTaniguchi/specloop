# Troubleshooting

Start with two commands:

- `tools/specloop doctor` checks the setup: `specloop.json`, the test paths, the project's specloop files, the trigger, whether the agent's CLI is installed and logged in, and whether Claude Code trusts the folder. Each problem comes with its fix, and it exits 1 if any of them stops syncs from working.
- `tools/specloop status` lists every spec revision the code doesn't match yet, with the state of its sync and what to do next.

Most problems below show up in one of them first.

## A spec commit didn't start a sync

Check, in order:

- **The trigger isn't on.** `git config core.hooksPath` should print `tools/githooks`. If it prints nothing, run `git config core.hooksPath tools/githooks`.
- **It isn't your change.** By default the hook builds only spec changes you wrote, so a teammate's merge shows up in `status` without starting anything. `status` says whose it is. Run `/spec-sync` to build it yourself, or set `"trigger": "all"` under `sync` in `specloop.json`.
- **GitHub rewrote the author.** A squash merge under a `users.noreply.github.com` address doesn't look like you. Add that address: `git config --add specloop.email 12345+you@users.noreply.github.com`.
- **It was skipped on purpose.** `SPEC_SYNC=off` skips the trigger. It also doesn't fire mid-rebase, mid-cherry-pick, or on a `spec-sync/` branch.
- **specloop is older than the project needs.** The hook won't start a sync below `minVersion`. See [below](#specloop-is-older-than-this-projects-minimum).
- **specloop isn't installed.** The commit goes through with `specloop: not installed (…); skipping`. Install it with `brew install KVTaniguchi/tap/specloop`.

To see what the hook would do without starting anything, commit with `SPEC_SYNC=dry-run`.

## "claude CLI not found" or "Cursor's agent CLI not found"

The hook couldn't find the agent's command-line tool. Git GUIs, Xcode's among them, run hooks with a short `PATH`. Commit from a terminal, or run `/spec-sync` yourself. For Cursor, install the `agent` CLI.

## "the claude CLI isn't logged in"

The desktop app and the command-line `claude` have separate logins. Run `claude auth status`, then `claude auth login`, then `/spec-sync` for the revision that failed.

## "failed to start session: … Workspace not trusted"

Background sessions only start in a trusted folder. Run `claude` in the project folder once and accept the prompt. Trust may not stick for a project under the system temp directory (`/private/tmp/…`); keep projects somewhere like `~/Development`.

## `status` says "failed to start?"

The session launched but never reported in. Its first error is usually in `claude logs <id>` (the id is in the `status` line), or in `.git/specloop/logs/<sha>.log` for Cursor. Fix the cause, then run `/spec-sync`. `specloop cleanup` removes the dead session's worktree.

## `status` says "stalled?"

The session reported `running` but has gone quiet for longer than `sync.staleAfterMinutes`. Check it with `claude agents` and `claude attach "Spec sync <sha>"`. If it died, run `/spec-sync` again.

## `status` says "blocked"

The agent stopped with questions about the spec rather than guess. The note in `status` says what it needs. Clarify the rule in the spec, commit, and the next sync picks it up. A note of the form `specloop 0.1.0 < 0.2.0` means the installed specloop is too old; see the next section.

## "specloop … is older than this project's minimum …"

The project's `specloop.json` has a `minVersion` newer than the installed specloop, usually because a teammate ran `specloop update`. Commands still run, but syncs don't start. Run `brew upgrade specloop`.

## "couldn't make the worktree"

Usually a leftover worktree or branch from an earlier sync of the same commit. Run `tools/specloop cleanup`, or `git worktree list` and `git worktree remove` the stale one, then `/spec-sync`.

## Coverage says 0 tests

`specloop coverage` warns when it found no test files at all, which looks exactly like a project with no tests. Check `tests.paths` and `tests.extensions` in `specloop.json` against your test target folders.

## A test is tagged but coverage doesn't count it

The IDs must come before the first colon of the test's name: `@Test("XP-6: …")`, not `@Test("Rewards XP-6: …")`. For XCTest, put `// Spec: XP-6` on a line by itself, and make sure `comment` is in `tests.tagStyles`. See [tagging tests](spec-format.md#tagging-tests).

## `status` says "merged" but the rule is still pending

The sync branch was merged, but the ledger didn't move with it, for example after a squash merge that dropped the ledger change. Run `tools/specloop mark` and commit `docs/.spec-implemented`.

## Still stuck

[Open an issue](https://github.com/KVTaniguchi/specloop/issues) with the `status` output and the sync's log. [Lessons](lessons.md) has the full story behind most of the fixes above.
