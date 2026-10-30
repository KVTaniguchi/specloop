# Measuring whether the spec pays off

> Status: plan (October 2026). Nothing here is built or measured yet. [lessons.md](lessons.md) records that the automatic trigger hasn't yet carried a real spec change from start to finish, so there is no evidence either way.

specloop costs something on every change: a spec edit, a wait for the sync, a second review. The case for it is that a second record of intent catches mistakes the code alone can't, and that agents with no memory change the code more safely when they can read what was meant. That case can be tested, and should be before specloop asks anyone else to pay the cost.

This plan answers two separate questions:

1. **Routing:** for a given kind of change, is it better to edit the spec first and let a sync build it, or to prompt the agent directly and update the spec in the same commit (the code-first route specloop already allows)?
2. **Having a spec at all:** does the prose spec help an agent do the right thing, beyond what the code and the tagged tests already tell it?

The first is measured on real changes. The second needs a controlled probe, because nobody is going to run a real project without its spec for a month.

## Hypotheses

Each one says what result would refute it.

| # | Claim | Refuted if |
|---|---|---|
| H1 | Spec-first changes need fewer follow-up fixes than direct ones | Follow-up fixes per change are the same or higher on the spec route, for the same kind of change |
| H2 | The spec route finds ambiguity before merge, not after | The share of confirmed `spec/ambiguous` and `spec/missing-rule` signals raised *after* merge is no lower on the spec route |
| H3 | Agents with the spec get intent right more often than agents with only the code and tests | The probe's score is within noise with and without the spec |
| H4 | The spec route's extra cost is small next to what it saves | Lead time or review time more than doubles while H1 and H2 show no gain |

If H3 fails, the prose spec isn't helping, and IDs plus tagged tests may be enough. If H1 and H2 hold only for some kinds of change, send the other kinds direct, the way layout changes already skip the spec.

## The routes, from trailers

The commit trailers already tell the routes apart, so nobody has to label them:

| Route | How a commit shows it |
|---|---|
| **Spec-first** | A `Sync` trailer |
| **Direct agent** | `Harness: claude-code …` (or cursor) with no `Sync` |
| **Hand-written** | `Harness: human` |

A change can span several commits. In what follows, a **change** is one request: everything committed toward it until it merges, plus the spec commit when it went spec-first.

## Kinds of change

Results will differ by kind, so each change is tagged with one before it starts:

| Kind | Example from the app |
|---|---|
| `rule` | Numbers or logic a test can pin: an XP table, a confidence threshold |
| `behavior` | A visible flow with no single number: what a sheet shows after a scan |
| `layout` | Where things sit, sizes, spacing |
| `refactor` | No behavior change intended |

`layout` and `refactor` are controls. Neither route should differ much on them, and if the spec route wins there, something other than the spec is causing it.

## Metrics

| Metric | Definition | Source | Exists now? |
|---|---|---|---|
| **Lead time** | From the request being written down to the change merging into the default branch | The change log below, and git | No. Nothing records when a request starts |
| **Agent time** | From a sync's start to its finish, or from a direct session's start to its last commit | Sync records, archived in `.git/specloop/syncs/done/`; `claude logs` for direct sessions | For syncs, yes. Direct sessions, unchecked |
| **First-pass merge** | Whether the agent's branch merged with no commits on top from someone else | The archived record: `branchTip` equal to `built`, and `branchMerged` | Yes, except a squash merge reads as not merged |
| **Follow-up fixes** | Commits within 14 days of the merge, other than the change itself, whose `Spec-Rules` names a rule the change touched or whose `Fixes-Signal` names a signal traced to it | Trailers | Yes |
| **Escaped signals** | Confirmed signals traced to the change's commits, by layer and kind | `docs/signals/` | Yes, once signals are being recorded |
| **Caught before merge** | Disagreements found before the merge: a sync that stopped as `blocked`, a test that showed the spec was wrong, a review comment that changed a rule | Sync signals, review notes in the change log | Partly. Blocked syncs become signals; the rest needs the log |
| **Cross-rule regressions** | Signals of kind `regression` on a rule the change didn't name | Signals | Yes |
| **Review minutes** | Your time reading and fixing the change, including the spec PR on the spec route | The change log, estimated to the nearest 5 minutes | No |
| **Agent cost** | Tokens or dollars for the sessions that built the change | Session usage, written into the change log | No. Whether `claude logs` exposes usage per session isn't checked yet |
| **Spec upkeep** | Spec commits that changed no behavior (`SPEC_SYNC=off`, wording, IDs), and confirmed `spec/wrong` signals where the rule had gone stale rather than started out wrong | git, signals | Partly |

Environment failures (auth, worktrees, hooks, everything most of the current lessons are about) are excluded from follow-up fixes and escaped signals, because they aren't about the change. They count toward agent time and review minutes, because they are part of the cost. Triage already files them under `outside/env`.

### The change log

The metrics that git can't supply go in one line per change in `docs/measurement/changes.jsonl`:

```json
{"id": "chg-20261102-1", "requested": "2026-11-02T09:10:00-05:00", "kind": "rule", "route": "spec", "request": "Rare breeds give 15 XP instead of 12", "rules": ["XP-1"], "merged": "a1b2c3d", "review_minutes": 15, "agent_cost": "0.42 USD", "caught_before_merge": ["the spec didn't say what happens to existing XP"], "notes": ""}
```

`requested`, `kind`, `route` and `request` are written **before** any work starts. The rest is filled in when the change merges. Writing the request first matters most: it is the only record of intent the direct route has, and the probe below uses these requests too.

## Assigning routes

If you pick the route yourself, you will send the hard changes through the spec and the easy ones direct, and the comparison will measure your judgment instead. So:

- Within each kind, alternate routes: the first `rule` change goes spec-first, the second direct, and so on. Log the assignment before looking at the code.
- A change may break assignment only when a route can't work for it, such as a hotfix with no time for a spec PR. Log it with `"route_override"` and a reason, and leave it out of the comparison.
- Both routes end with the spec true. The direct route updates the spec in the same commit, as specloop already requires. This compares the order of work, not having a spec or not, which is the probe's job.

### How many

This is one person on one app, so the numbers will be small and only large effects will show. Run until each route has at least 8 `rule` changes and 5 `behavior` changes, or for six weeks, whichever comes first. Report counts with the raw numbers, not percentages alone. A 2-of-8 versus 5-of-8 difference in follow-up fixes is a hint, not a result.

## The probe: does the prose spec help?

A fixed test, run on demand, that compares fresh agent sessions **with** the spec and **without** it.

**Setup.** Make two worktrees at the same commit. In one, delete `docs/spec/` and the spec section of `CLAUDE.md`. Tests keep their rule-ID tags in both, since the question is what the prose adds beyond them. Each session starts cold, with no conversation history.

**Questions** (about 15, kept in `docs/measurement/probe.md` with their answers):

- **Intent questions** with one right answer the code doesn't make obvious. "Is it intended that the Map tab opens the camera?" "When a scan is relabeled, should XP change?" Score: right, wrong, or "can't tell". "Can't tell" counts as better than wrong.
- **Change tasks** where the obvious edit breaks a rule. For example, "make common breeds give more XP", if another rule fixes the gap between common and rare breeds and a naive change would move both. Score: whether every tagged test still passes, and whether the agent changed anything the task didn't ask for.
- **Non-goal tasks** that the spec rules out. Take each from the overview's non-goals, phrased as an ordinary feature request. Score: whether the agent pushes back or asks before building it.

Write the questions from rules you already know cause trouble: the [lessons](lessons.md), past signals, and the drift found during spec-init.

**Runs.** Each question three times per worktree, since one sample of an agent says little. Run it once at the start, then again after every model or `Harness-Rev` change, and record the `Harness` with each score.

**Reading it.** If with-spec beats without-spec on intent and non-goal questions but not on change tasks, the tests are doing most of the protecting and the prose mainly prevents scope creep. That's still worth knowing, and a reason to keep the spec short.

## Decisions this should drive

These are written down before the data exists, so the data can't be explained away afterwards:

| Result | Decision |
|---|---|
| For a kind, the spec route has at least 2× the lead time and no fewer follow-up fixes or escaped signals | Send that kind direct by default, and say so in the README and the template `CLAUDE.md` |
| The spec route has clearly fewer follow-up fixes on `rule` changes | Keep it as the default for rules, and look at whether `behavior` should join |
| The probe shows no difference on any question type | Slim the spec to rule IDs, one line each, plus non-goals, and measure again |
| Spec upkeep (stale rules, wording-only syncs) costs more review time than the spec route saves | Cut what goes stale: rules that copy config, and prose about layout |
| The controls (`layout`, `refactor`) differ between routes as much as `rule` does | Don't trust the other results; look for what else changed |

## Prerequisites

1. **Keep sync records and timing after cleanup.** Done: `cleanup` moves an implemented sync's record to `.git/specloop/syncs/done/` instead of deleting it, with `started`, `finished`, `built`, `branchTip`, `branchMerged` and `ledger`. It lives only on the clone that ran the sync, which is fine for one person.
2. **Trailers on every commit**, which is [attribution](attribution.md) build step 1. Without them the routes can't be told apart.
3. **Signals recorded, not just fixed**, which is attribution build step 3. Escaped signals and regressions come from them.
4. **The environment is stable enough** that most syncs finish. While the plumbing is still failing every few runs, the spec route's numbers measure the plumbing.

## Build order

Do it by hand first. Build a report only once the hand-run numbers are worth automating.

| # | Step | Done when |
|---|---|---|
| 1 | Archive sync records instead of deleting them (prerequisite 1). Built | A real merged sync's record is still readable in `syncs/done/` a week later |
| 2 | Start `changes.jsonl` and log every change on the app, with assigned routes | Two weeks of changes logged, none written after the fact |
| 3 | Write the probe and run it once against the current spec | 15 questions with answers, scored 3 times per worktree |
| 4 | Compute the metrics by hand (a short script is fine) at the end of the run | One table per kind, both routes, with raw counts |
| 5 | Act on the decision table and write the outcome in [lessons.md](lessons.md) | The decision and its numbers are a lesson entry, including if the answer is "drop the spec route for most changes" |
| 6 | Only if steps 2–5 were worth it: `specloop report`, reading trailers, signals, archived syncs and the change log | It reproduces step 4's table without hand work |

## Threats to the result

- **The tool is still changing.** A fix to the hook halfway through the run changes the spec route's cost. Record the specloop commit with each change and compare like with like.
- **You are the author of the tool and the only reviewer.** You'll want it to win. Alternating assignment and the decision table written ahead of time are the main defenses, along with logging requests before work starts.
- **Learning.** Later changes are easier on both routes because you know the app better. Alternating within a kind spreads that across both routes.
- **Models change.** Group every number by `Harness`. A model upgrade partway through starts a new comparison, not a continuation.
- **One app.** A SwiftUI game with numeric rules may favor specs more than a CRUD app would. The result says where specloop pays off on this kind of project, not everywhere.

## Open questions

- Is 14 days the right window for follow-up fixes? Some mistakes in game rules surface only when someone plays long enough to hit them.
- Should the probe also run with the spec present but the tests' tags stripped, to see how much the tags alone carry?
- How should a change count that started direct and was moved to the spec route partway through, because the agent found the rule was ambiguous? That may be the spec earning its keep, so it shouldn't be dropped.
