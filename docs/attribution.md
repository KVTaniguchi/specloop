# Attribution and feedback

> Status: built (October 2026), but not yet tried on a real project. The "Done when" column under [Build order](#build-order) is what still has to happen for each piece to count as proven.

specloop already traces forward: rules have IDs, tests name the IDs they check, and the ledger records which spec revision the code matches. This design adds the trace backward. When something goes wrong with code a sync produced, specloop should be able to say which rules, which revision of them, and which harness the code came from, and then which part of the system to fix.

Four pieces, each useful without the ones after it:

1. **Commit trailers** record, in every commit, the spec revision, the rules and the harness behind it.
2. **`specloop blame`** follows a code location or a failing test back to those trailers.
3. **The signal record** captures one piece of feedback (a crash, a QA report, a review comment) with what it was traced to.
4. **Triage** sorts each signal into the layer that failed, and the fix goes to that layer.

## Terms

| Term | Meaning |
|---|---|
| **Signal** | Any evidence that code behaves wrongly or badly: a failing test, a crash, a QA report, a review comment, a user report |
| **Attribution** | The rules, spec revision, commits and harness a signal traces back to |
| **Layer** | The part of the system a signal is blamed on: the spec, the implementation, the tests, the harness, or something outside specloop |
| **Harness** | Everything that turned the spec into code: the agent, the model, the skill files, and the project's `CLAUDE.md` / `AGENTS.md` |

## 1. Commit trailers

Every commit that changes code carries trailers saying where it came from. `/spec-sync` already lists rule IDs in its commit body; this makes that list machine-readable and adds the rest.

```
Spec sync: XP bonus uses the scanner's breed

Spec-Rev: 9f8e7d6c2b1a
Spec-Rules: XP-6@3fa2c1, LVL-2@b71e09
Harness: claude-code claude-opus-5-5
Harness-Rev: spec-sync@41d0aa claude-md@9c2e11
Sync: 9f8e7d6
```

| Trailer | Value | Source |
|---|---|---|
| `Spec-Rev` | The commit whose spec this code implements, the same value `specloop mark` writes to the ledger | the ledger |
| `Spec-Rules` | Each rule the commit implements or changes, as `ID@version` | the spec diff the sync built |
| `Harness` | The agent and model | `specloop.harness` and the agent's own report |
| `Harness-Rev` | Short hashes of the skill file and of the project's agent instructions at the time | the files in the worktree |
| `Sync` | The sync record this commit came from | `.git/specloop/syncs/` |

### Versions

- **A rule's version** is a short hash of its text, as `rule_texts` already reads it (every line the ID owns, whitespace-normalized). Rewording a rule changes its version; moving it to another doc doesn't. Nobody bumps a number by hand.
- **The spec's version** is the git commit. Nothing new is needed.
- **The harness's version** is the agent and model plus `Harness-Rev`. Skill and instruction files change outcomes as much as the model does, so they're versioned the same way as rules: by content hash.

`specloop trailers` prints the block for the current worktree, so `/spec-sync` and people both get the same values without assembling them.

### Commits without a sync

- **Code-first commits** (a hotfix, code changed together with the spec) still name their rules: `Spec-Rules: SCAN-8@…` and `Harness: human`. An agent session that isn't a sync names itself: `Harness: claude-code claude-opus-5-5` with no `Sync`.
- **Commits no rule covers** (dependency bumps, formatting, build config) say so: `Spec-Rules: none (deps)`. The reason in brackets is required, so "none" is a decision rather than an omission.
- **Enforcement:** `specloop check --trailers <range>` fails on a code commit in the range with no `Spec-Rules`, or one naming an ID the spec at that commit doesn't define. In CI the range is the PR's commits ([setup](ci.md#github-actions)). The `commit-msg` hook gives the same answer locally when `trailers.hook` is `true` in `specloop.json`. It's off by default, and `git commit --no-verify` skips it once.

### Squash merges

GitHub's squash merge rewrites the message. For a PR with several commits, its default message joins the commit messages, so the trailers survive but end up mid-body, where `git interpret-trailers` won't find them. For a single-commit PR, depending on settings, it can use the PR title and description instead and drop them.

So:
- `blame` reads known keys from **anywhere in the message**, not only the final trailer block, and merges repeated keys.
- `/spec-sync` also puts the trailer block in the PR description it suggests.
- `check --trailers` runs on the default branch after merge too, so a squash that lost them is caught on the first push rather than months later during triage.

## 2. `specloop blame`

```
tools/specloop blame <file>:<line>
tools/specloop blame --test "<test name>"
tools/specloop blame --rule XP-6
tools/specloop blame --commit <sha>
```

| Input | How it's traced |
|---|---|
| `file:line` (a stack frame, a review comment) | `git blame -w -M -C` for the line, then the trailers of the commit it names |
| A test | The test's tags give the rules directly; `blame` of the test's own lines gives who wrote the test |
| A rule | Every commit whose `Spec-Rules` names it, newest first, and the tests tagged with it |
| A commit | Its trailers, parsed |

Output is one block per commit it reaches:

```
src/XP/Bonus.swift:42
  a1b2c3d  2026-10-20  Spec sync: XP bonus uses the scanner's breed
    spec     9f8e7d6  XP-6@3fa2c1 (current: 3fa2c1, unchanged)
    harness  claude-code claude-opus-5-5  spec-sync@41d0aa
    tests    XPTests.swift: "XP-6: picking another breed pays the scanner's XP"
```

It also says whether the rule's text has changed since that commit (`current: …`). A crash in code built from an older wording of a rule is a different story from one built from today's.

**Limits.** Blame finds the last commit that touched a line, not the one that caused a bug. A rename or a reformat with `Spec-Rules: none` hides the real author, so `blame` skips commits whose only reason is `(format)` or `(rename)`, the same way `.git-blame-ignore-revs` works, and keeps walking. It reports when it skipped one. When the trace still lands on the wrong commit, the person or agent doing triage corrects it on the signal record.

## 3. The signal record

One record per piece of feedback, one file per record under `docs/signals/` (`signals` in `specloop.json`). Signals are in the repo, not in `.git/specloop/`, because they have to reach everyone who works on the project, and their resolution should be reviewed like any other change.

```json
{
  "id": "sig-20261021-7c3e9a",
  "fingerprint": "crash:XPBonus.apply:EXC_BAD_ACCESS",
  "source": "crash",
  "received": "2026-10-21T14:02:00Z",
  "summary": "Crash applying the XP bonus when the picked breed has no XP table",
  "evidence": ["Stack: XPBonus.apply (src/XP/Bonus.swift:42)", "Build 1.4.2 (a1b2c3d)"],
  "locus": ["src/XP/Bonus.swift:42"],
  "attribution": {
    "rules": ["XP-6@3fa2c1"],
    "commits": ["a1b2c3d"],
    "harness": "claude-code claude-opus-5-5",
    "harness_rev": "spec-sync@41d0aa claude-md@9c2e11",
    "traced_by": "specloop blame"
  },
  "triage": {
    "layer": "spec",
    "kind": "missing-rule",
    "confidence": "medium",
    "reasoning": "XP-6 says which breed's XP applies but not what happens when it has none.",
    "confirmed_by": "you@example.com"
  },
  "resolution": { "status": "open", "fix": null },
  "duplicates": []
}
```

- **Attribution** comes from blaming each locus, plus each rule given with `--rule` and the latest commit that names it. `harness` and `harness_rev` are the first traced commit's, kept apart so reports can group by them.
- **IDs** are the date plus a short hash of the fingerprint and time. Sequential numbers would collide when two branches each add a signal, and there's no server to hand them out.
- **Fingerprints** collapse repeats. A crash's fingerprint is its top in-project frame and error type, a failing test's is the test's name, a review comment's is its file and the rule it cites. A signal with a fingerprint that's already open is added to that record's `duplicates` instead of becoming a new one. How often something recurs is evidence for triage.
- **Sources** are open-ended strings: `test`, `crash`, `qa`, `review`, `user`, `telemetry`. specloop doesn't pull from any of them. `specloop signal add` takes a file or standard input (a pasted stack trace, a comment), and adapters for crash reporters or issue trackers can call the same command. Nothing specloop ships talks to a network.
- **Resolution** links to what fixed it: a spec PR, a sync, a test commit, a skill change, a lesson. `status` is `open`, `fixed`, `wontfix` or `duplicate`.

### Closing signals

A commit that fixes a signal says so in a trailer, `Fixes-Signal: sig-20261021-7c3e9a` (`specloop trailers --fixes <id>` adds it). A signal is fixed once such a commit is on `HEAD`, which for most clones means merged into the default branch. Nothing has to edit the record, so everyone who pulls the fix sees the signal close.

A fix that changes the spec isn't a fix until the code catches up. Until the ledger reaches that commit, the signal shows as `fix pending sync`, and it still counts as open.

`signal resolve` is for what no commit will close: a harness lesson, a fix outside the repo, `wontfix`, `duplicate`. A status stored there wins over the trailers.

### Where signals come from

- **People and agents**, through `/spec-triage` or `specloop signal add`.
- **Syncs that stop.** `specloop sync blocked --signal` and `sync failed --signal` record the sync as a signal on the rules it was building, with source `sync` and the sync's harness. A blocked sync usually means the rule is ambiguous, so its signal comes with an unconfirmed `spec/ambiguous` guess for triage to check. These signals go to the main work tree, because the stopped sync's worktree is about to be cleaned up.

### Where signals show up

- `specloop status` counts open signals, the untriaged ones, and those waiting for a sync, and lists the ones on pending rules.
- `/spec-sync` starts with `specloop signals --pending`, the open signals on the rules it's about to build, so a spec change made to fix a signal is built with that signal in mind. It names the ones it fixes with `trailers --fixes`.
- `signals` in a sync's worktree also reads the main work tree, so a signal recorded there but not committed yet still reaches the sync.

## 4. Triage

Each signal is blamed on one layer. The layer decides what kind of fix it gets. This list borrows from IBM's Orthogonal Defect Classification, which classifies defects by where they were introduced so the counts can steer the process.

| Layer | Kind | The question that decides it | Fix |
|---|---|---|---|
| **spec** | `wrong` | Does the code do what the rule says, and the rule is what's wrong? | Spec PR to change the rule |
| | `ambiguous` | Could a careful reader implement the rule two ways, and this is the bad one? | Spec PR to sharpen it |
| | `missing-rule` | Is the behavior one no rule covers at all? | Spec PR to add a rule |
| **implementation** | `misread` | Is the rule clear, and the code does something else? | Re-sync, and count it against the harness |
| | `regression` | Did a later commit break a rule an earlier one implemented? | Fix it, and a test that would have caught it |
| **verification** | `weak-test` | Is there a test tagged with the rule that passed anyway? | Strengthen the test |
| | `untested` | Is the rule implemented with no test naming it? | Add a test; consider `--require` for its prefix |
| **harness** | `skill` | Did the agent follow its instructions, and the instructions led it wrong? | Change the skill, plus a lesson |
| | `context` | Was something the agent needed missing from `CLAUDE.md` / `AGENTS.md`? | Add it |
| | `model` | Do the same rule and instructions fail with one model and not another? | Record it; change the configured model if it's a pattern |
| **outside** | `env`, `ops`, `dependency` | Is the cause outside the code the spec describes? | Not specloop's to fix; close with a link |

Work down the table: a rule that's wrong is the cause even when the code also looks off, because fixing the code alone would make it match a wrong rule.

Many failures involve two layers, for example an `ambiguous` rule that was also `misread`. Record the earliest layer that, fixed alone, would have prevented the signal. That keeps the counts meaning one thing.

### `/spec-triage`

A skill that takes a signal ID, or raw evidence it records as a new signal, and:

1. Runs `specloop blame` on the signal's locus and fills in `attribution`.
2. Reads the rules it reached, at the version the code was built from and as they are now, and the tests tagged with them.
3. Proposes a `layer`, `kind`, `confidence` and `reasoning`, using the questions above.
4. Drafts the fix for that layer: the spec PR text, the test, or the skill change. It doesn't apply it.

A person confirms the classification (`confirmed_by`) before the fix is opened. Unconfirmed triage counts as nothing in reports.

The skill records its steps with:

```
tools/specloop signal add --source crash --summary "..." --evidence trace.txt [--locus F:L] [--rule ID]
tools/specloop signal triage <id> --layer spec --kind ambiguous --confidence medium --reasoning "..."
tools/specloop signal confirm <id>                 # the person agrees; records their user.email
tools/specloop signal resolve <id> --status fixed --fix "spec PR #14"
tools/specloop signal show <id>
```

`triage --confirm` does both at once, for when the person triages a signal themselves.

## 5. Feedback

Fixes to the spec, the code and the tests go through the normal loop: a spec PR, a sync, a review.

Fixes to the **harness** are different, because one bad session isn't evidence about the instructions. Changing a skill after every incident would fit it to anecdotes. So:

- A single `harness` signal produces a lesson in `docs/lessons.md`, which is what happens by hand today, and nothing more.
- A skill or instruction change is proposed when **several confirmed signals share a layer and kind** under the same `Harness-Rev` (`feedback.harnessThreshold`, default 3). The proposal cites them.
- That change is a reviewed PR like any spec change. Its new `Harness-Rev` makes the next signals comparable to the old ones.

`specloop signals` reports the counts:

```
tools/specloop signals                      open signals, newest first
tools/specloop signals --by layer           counts per layer and kind
tools/specloop signals --by harness         per Harness / Harness-Rev: syncs, signals, signals per sync
tools/specloop signals --rule XP-6          everything traced to one rule
```

Signals per sync, split by `Harness-Rev`, is how you see whether a skill change helped. It's the same idea as DORA's change failure rate, but per harness version instead of per team.

## Non-goals

- **No server and no ingestion.** specloop defines the record and the commands. Getting crashes or analytics into them is an adapter's job.
- **No automatic edits to skills or instructions.** The tool proposes; a person merges.
- **No scoring of people.** `Harness: human` is there so traces don't break at hand-written commits, not to compare authors.

## Build order

Each step is useful if the later ones never ship.

| # | Step (all built) | Done when |
|---|---|---|
| 1 | **Trailers.** `specloop trailers`; `/spec-sync` writes them in commits and PR descriptions; `check --trailers` in the CI setup; the template `CLAUDE.md` asks for them on hand-written commits | A week of commits on the iOS project all carry trailers, including after squash merges |
| 2 | **`specloop blame`** for `file:line`, `--test`, `--rule`, `--commit`, reading trailers from anywhere in a message | A real crash frame and a real failing test both trace to the right rule and sync |
| 3 | **Signal records.** `specloop signal add`, fingerprinting and duplicates, `docs/signals/`, `Fixes-Signal`, stopped syncs as signals, open signals in `status` and `/spec-sync` | The next three real problems on the iOS project are recorded as signals, not just fixed |
| 4 | **`/spec-triage`** with the layer table | It classifies those signals, and the person confirming agrees with most of them |
| 5 | **`specloop signals` reports** and the harness threshold | There's enough data for `--by harness` to compare two `Harness-Rev`s |

Steps 1 and 2 are cheap and pay off right away. Steps 4 and 5 depend on how good triage turns out to be on real signals, and may change once they exist.

## Open questions

- **Where should signals live for a team that doesn't want them in the repo?** GitHub issues with a label and the JSON in a code block would work, at the cost of reading them over the network.
- **Does `Harness-Rev` need to cover more?** Hooks, `specloop.json` and the specloop version itself also shape what a sync does.
- **Can triage tell `ambiguous` from `misread` reliably?** Both look like "the code doesn't do what I meant". If people disagree about it often, the two kinds may need to merge.
- **What about signals with no locus?** A QA report like "leveling feels slow" points at a rule, not a line. It can still be attributed by rule (`--rule LVL-1`), but blame has nothing to follow.
