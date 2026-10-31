# Sensors and CI

specloop has two kinds of sensor: one notices when the spec changes and tracks the sync that follows, and the other fails a build when the spec and the code have drifted apart.

## Tracking syncs

The hooks in `tools/githooks/` run after every way a spec change can reach a clone:

| Hook | Fires on | Compares |
|---|---|---|
| `post-commit` | a commit, including the one that concludes a conflicted merge | `HEAD^1..HEAD` |
| `post-merge` | `git merge` and `git pull`, fast-forward or not (not `--squash`: its commit fires `post-commit`) | `ORIG_HEAD..HEAD` |
| `post-rewrite` | a rebase, including `git pull --rebase` (not `--amend`: `post-commit` already ran) | `ORIG_HEAD..HEAD` |

Each one calls `tools/specloop trigger`, which starts a sync only when all of these are true:
1. the update changed the spec,
2. the code doesn't match the spec at `HEAD` yet (a pull of an already-synced change starts nothing), and
3. no other sync is starting or running in this clone,
4. you wrote the spec change, and
5. it happened in the main work tree. A merge in a sync's worktree, or in any other linked worktree, never starts one: the change starts its sync when it reaches the main work tree. (with `sync.trigger` at its default, `mine`).

The fourth one is how specloop avoids collisions without a server. A spec PR merged on GitHub reaches everyone who pulls, and every clone with the hook enabled would otherwise start building it. Instead, only the clone whose `user.email` (or any `git config specloop.email`) matches the author of a spec commit in the update starts a sync. Everyone else sees the revision in `status` as `not started  by <author>, so the hook left it to them`, and can take it over with `/spec-sync`. Set `"trigger": "all"` under `sync` if you work alone across addresses or want every clone to build.

Every sync has a record in `.git/specloop/syncs/`, outside the work tree, so all worktrees of a clone share it. The hook writes `starting` and sends the launch output to `.git/specloop/logs/<sha>.log`.

- **Claude Code** (`claude --bg`) picks the session's ID, which the hook records. A session that dies after launch usually explains why only in its own output, so `status` points at `claude logs <id>` for those.
- **Cursor** (`agent -p`) has no background mode, so the hook makes the worktree and branch itself, starts the agent there in the background, and writes all of its output to the log. If the agent exits within a second without reporting in, as it does when it isn't logged in, the hook marks the sync `failed` with the first line of its output. `/spec-sync` then reports `running`, followed by `done`, `blocked` or `failed`, through `tools/specloop sync <status>`.

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

Each sync runs in a worktree the hook makes at `HEAD`, on the branch `spec-sync/<sha>`: `.claude/worktrees/spec-sync-<sha>` for Claude Code, `.specloop/worktrees/spec-sync-<sha>` for Cursor. The hook makes it itself because `claude --worktree` would cut it from the remote's default branch, which doesn't have a spec change you haven't pushed. A Cursor worktree is locked with its agent's pid. A Claude Code one isn't locked, because `claude --bg` doesn't say which process runs the session, so a dead Claude Code session shows up as a sync that went quiet (`failed to start?`, `stalled?`). Neither agent removes its worktree when it finishes. While a sync waits for review, its branch is checked out there, so you can `cd` into it to run the change, or `claude attach` to the session to ask about it.

`tools/specloop cleanup` removes these worktrees once they're no longer needed, and the hooks run it after every commit, merge and rebase. A worktree goes when either:
- **the sync is implemented:** the ledger has reached its revision, usually because you merged its branch. Its session is stopped first if it's still open. Its record moves to `.git/specloop/syncs/done/`, where `status` and the hook no longer see it, along with the commit the sync finished on (`built`), the branch's last commit (`branchTip`), whether that was merged (`branchMerged`) and the ledger at cleanup. Those are kept for [measuring](measurement.md) the spec route.
- **its session ended without finishing:** the sync failed, or the process holding the worktree's lock has exited while the sync still said starting or running. The record becomes `failed`, so `status` still shows that the revision needs a sync.

It never touches:
- worktrees with any other name
- a sync that's running, waiting for review, or blocked on a question (you can still attach and answer it)
- a worktree with uncommitted changes
- a worktree locked by anything other than a sync's agent

The branch is deleted when it's merged or has no commits of its own. Otherwise it's kept and the message says so. A squash-merged branch is one example. For Claude Code, `claude stop` ends the session first and `claude rm` then clears it from `claude agents`. A Cursor agent that's still open is stopped by its pid.

`status` reports leftover worktrees, and `cleanup --dry-run` shows what would go. `SPEC_SYNC=dry-run` also makes the hooks dry-run their cleanup.

## `specloop check`

`specloop check` gathers the checks a build should enforce and exits 1 if any of them fails:

- for a spec tree: every link to a spec doc resolves, and every doc can be reached from the overview
- every ID is defined once, across all docs
- no ID came back with a different meaning: a removed ID that is defined again with different rule text is an error. A straight restore, such as a revert, is fine. List deliberate exceptions under `check.allowReused`.
- no test names an ID the spec doesn't define (stale tags)
- every ID under the required prefixes (`sync.require`, or `--require`) has a test
- the ledger names a commit in this clone, and the code matches the spec at `HEAD`
- with `--trailers RANGE`: every commit in the range that changes code has a `Spec-Rules` trailer naming rules the spec defines at that commit, or `none (reason)`. Merge commits are skipped, and so are commits that only touch the spec, the ledger, the signals, or `trailers.exempt` (default `*.md`, `LICENSE`, `.gitignore`). See [attribution](attribution.md#1-commit-trailers).

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
          fetch-depth: 0   # the ledger, the reused-ID check and the trailers need history
      - uses: KVTaniguchi/specloop@v0.1.0   # installs the project's minVersion
      - run: |
          if [ "${{ github.event_name }}" = pull_request ]; then
            range="origin/${{ github.base_ref }}..HEAD"
          elif [ "${{ github.event.before }}" != 0000000000000000000000000000000000000000 ]; then
            range="${{ github.event.before }}..${{ github.sha }}"
          fi
          tools/specloop check --format github ${range:+--trailers "$range"}
```

`tools/specloop` runs the specloop installed on the machine, and a CI runner has none, so the workflow installs it first. The action installs exactly the project's `minVersion` from `specloop.json`, not the latest release. That way the result of a gating check only changes when a commit changes the minimum (`specloop update` raises it). Without the action, `pipx install "specloop==<minVersion>"` does the same.

This checks trailers on the commits each run brings in: a pull request's own commits, or what a push added to the branch. The push check is what catches a squash merge that dropped them. A branch's first push has no `before` to compare with, so it skips the trailer check.

Leave out `--trailers` only if you don't want attribution. Without it, a hand-written commit with no trailers goes in silently, and the code it touches can't be traced from then on.

To let spec-only pull requests through while still gating the default branch, add `--allow-pending` on pull requests:

```yaml
          tools/specloop check --format github ${range:+--trailers "$range"} \
            ${{ github.event_name == 'pull_request' && '--allow-pending' || '' }}
```

The same check runs locally on each commit if you set `"trailers": {"hook": true}` in `specloop.json` and have the hooks enabled (`core.hooksPath tools/githooks`). `git commit --no-verify` skips it once.

`check` only reads tags and history. It doesn't run your tests, so run your test command as its own step.
