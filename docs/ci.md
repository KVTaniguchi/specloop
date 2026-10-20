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

Every sync has a record in `.git/specloop/syncs/`, outside the work tree, so all worktrees of a clone share it. The hook writes `starting` and sends the launch output to `.git/specloop/logs/<sha>.log`. `/spec-sync` then reports `running`, followed by `done`, `blocked` or `failed`, through `tools/specloop sync <status>`.

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
| failed to start? | launched over 10 minutes ago and never reported in; see the log |
| running | `/spec-sync` is working on it |
| stalled? | running, but no update for `sync.staleAfterMinutes` (default 120) |
| included | a newer revision's sync covers it |
| awaiting review | finished; the branch is ready to merge |
| blocked | stopped with a question about the spec (shown) |
| failed | stopped because something broke (shown) |
| branch gone / merged | the record and the branches disagree; rerun `/spec-sync` or `specloop mark` |

A launch that went quiet (`failed to start?`, `stalled?`) no longer stops the hook from starting a new sync.

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
