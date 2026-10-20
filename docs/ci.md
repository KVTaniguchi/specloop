# Sensors and CI

specloop has two kinds of sensor: one notices when the spec changes and tracks the sync that follows, and the other fails a build when the spec and the code have drifted apart.

## Tracking syncs

The hooks in `tools/githooks/` run after every way a spec change can reach a clone:

| Hook | Fires on | Compares |
|---|---|---|
| `post-commit` | a commit, including the one that concludes a conflicted merge | `HEAD^1..HEAD` |
| `post-merge` | `git merge` and `git pull`, fast-forward or not (not `--squash`: its commit fires `post-commit`) | `ORIG_HEAD..HEAD` |
| `post-rewrite` | a rebase, including `git pull --rebase` (not `--amend`: `post-commit` already ran) | `ORIG_HEAD..HEAD` |

Each one calls `tools/specloop trigger`, which starts a sync only when all three are true:
1. the update changed the spec,
2. the code doesn't match the spec at `HEAD` yet (a pull of an already-synced change starts nothing), and
3. no other sync is starting or running in this clone.

Every sync has a record in `.git/specloop/syncs/`, outside the work tree, so all worktrees of a clone share it. The hook picks the session's ID, writes `starting`, and sends the launch output to `.git/specloop/logs/<sha>.log`. A session that dies after launch usually explains why only in its own output, so `status` points at `claude logs <id>` for those. `/spec-sync` then reports `running`, followed by `done`, `blocked` or `failed`, through `tools/specloop sync <status>`.

`tools/specloop status` turns those records, the ledger and the branches into one line per pending spec revision:

```
pending:     XP-1, XP-2
  9f8e7d6  running          on spec-sync/9f8e7d6, last update 4m ago
  a1b2c3d  included         in the sync of 9f8e7d6
```

| State | Meaning |
|---|---|
| not started | nothing has picked it up; run `/spec-sync` |
| starting | the hook launched a session that hasn't reported in yet |
| failed to start? | launched over 10 minutes ago and never reported in; `claude logs <id>` shows why |
| running | `/spec-sync` is working on it |
| stalled? | running, but no update for `sync.staleAfterMinutes` (default 120) |
| included | a newer revision's sync covers it |
| awaiting review | finished; the branch is ready to merge |
| blocked | stopped with a question about the spec (shown) |
| failed | stopped because something broke (shown) |
| branch gone / merged | the record and the branches disagree; rerun `/spec-sync` or `specloop mark` |

A launch that went quiet (`failed to start?`, `stalled?`) no longer stops the hook from starting a new sync.

## Cleaning up worktrees

Each sync runs in a worktree that Claude Code creates and locks: `.claude/worktrees/spec-sync-<sha>`. Claude Code doesn't remove it when the session finishes. While a sync waits for review, its branch is checked out there, so you can `cd` into it to run the change, or `claude attach` to the session to ask about it.

`tools/specloop cleanup` removes these worktrees once they're no longer needed, and the hooks run it after every commit, merge and rebase. A worktree goes when either:
- **the sync is implemented:** the ledger has reached its revision, usually because you merged its branch. Its session is stopped first if it's still open.
- **its session ended without finishing:** the sync failed, or the process holding the worktree's lock has exited while the sync still said starting or running. The record becomes `failed`, so `status` still shows that the revision needs a sync.

It never touches:
- worktrees with any other name
- a sync that's running, waiting for review, or blocked on a question (you can still attach and answer it)
- a worktree with uncommitted changes
- a worktree locked by anything other than a Claude Code session

The branch is deleted when it's merged or has no commits of its own. Otherwise it's kept and the message says so. A squash-merged branch is one example. `claude rm` then clears the session from `claude agents`.

`status` reports leftover worktrees, and `cleanup --dry-run` shows what would go. `SPEC_SYNC=dry-run` also makes the hooks dry-run their cleanup.

## `specloop check`

`specloop check` gathers the checks a build should enforce and exits 1 if any of them fails:

- every ID is defined once
- no ID came back with a different meaning: a removed ID that is defined again with different rule text is an error. A straight restore, such as a revert, is fine. List deliberate exceptions under `check.allowReused`.
- no test names an ID the spec doesn't define (stale tags)
- every ID under the required prefixes (`sync.require`, or `--require`) has a test
- the ledger names a commit in this clone, and the code matches the spec at `HEAD`

A spec ahead of the code is an error by default. That's the state "the spec was merged but nothing built it". Pass `--allow-pending` to downgrade it to a warning, for example on pull requests that only change the spec.

`--format github` prints workflow annotations, so findings show up on the lines they're about.

### GitHub Actions

```yaml
name: spec
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # the ledger and the reused-ID check need history
      - run: tools/specloop check --format github
```

To let spec-only pull requests through while still gating the default branch:

```yaml
      - run: tools/specloop check --format github ${{ github.event_name == 'pull_request' && '--allow-pending' || '' }}
```

`check` only reads tags and history. It doesn't run your tests, so run your test command as its own step.
