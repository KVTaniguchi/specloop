---
name: spec-triage
description: Triage feedback about code a spec produced (specloop): a crash, a failing test, a QA report, a review comment. Records it as a signal, traces it to the rules, commits and harness behind the code, and proposes which layer failed (spec, implementation, verification, harness, outside) and the fix for that layer. Use when the user pastes a stack trace or bug report, says "triage this", or names a signal ID.
---

# Spec triage

A signal is any evidence that code behaves wrongly. Your job is to find which part of the system let it through, so the fix goes there and not only into the code. You propose; the user confirms. You never apply the fix yourself.

This skill works the same in Claude Code and in Cursor. Where it says `CLAUDE.md`, read `AGENTS.md` too if the project has one. The design is in specloop's `docs/attribution.md`.

## 1. Record the signal

If the user gave a signal ID, `tools/specloop signal show <id>` and go to step 2.

Otherwise save the evidence (stack trace, report, comment) to a file and record it:

```bash
tools/specloop signal add --source <test|crash|qa|review|user|telemetry> \
    --summary "<one line>" --evidence <file> [--locus FILE:LINE] [--rule ID]
```

- `file:line` places in the evidence are found on their own. Add `--locus` for one it missed, such as the line a review comment is on.
- With no place in the code (a QA report like "leveling feels slow"), name the rule with `--rule`.
- If it says `same as open signal <id>`, it's a repeat. Continue with that ID: how often something recurs is evidence too.

## 2. Trace it

```bash
tools/specloop blame <file>:<line>       # for each locus
tools/specloop blame --test "<name>"     # for a failing test
tools/specloop blame --rule <ID>         # every commit that built a rule
```

Note for each commit: the rules and their versions, whether each rule has **changed since** (code built from an older wording is a different story), the harness and `Harness-Rev`, and the tests tagged with those rules. If blame landed on the wrong commit, say which one is right and why.

Then read:
- each rule as it was at the commit's `Spec-Rev` (`git show <Spec-Rev>:<spec doc>`) and as it is now
- the code at the locus, and the tests tagged with the rules
- `CLAUDE.md`'s **Spec sync rules** and the spec-sync skill (`tools/specloop skill spec-sync`), if the harness is in question

## 3. Classify

Pick **one** layer and kind. Work down the table and stop at the first row whose question is "yes". A rule that's wrong is the cause even if the code also looks off, because fixing only the code would make it match a wrong rule.

| Layer | Kind | Yes when… | Fix |
|---|---|---|---|
| spec | `wrong` | the code does what the rule says, and the rule is what's wrong | spec PR changing the rule |
| | `ambiguous` | a careful reader could implement the rule two ways, and this is the bad one | spec PR sharpening it |
| | `missing-rule` | no rule covers the behavior at all | spec PR adding a rule |
| implementation | `misread` | the rule is clear and the code does something else | re-sync; counts against the harness |
| | `regression` | a later commit broke what an earlier one built | fix, plus a test that would have caught it |
| verification | `weak-test` | a test tagged with the rule passed anyway | strengthen the test |
| | `untested` | the rule is implemented and no test names it | add one; consider `--require` for its prefix |
| harness | `skill` | the agent followed its instructions and they led it wrong | an issue or PR against specloop, plus a lesson |
| | `context` | something the agent needed wasn't in `CLAUDE.md` / `AGENTS.md` | add it |
| | `model` | the same rule and instructions fail with one model and not another | record it; change models only on a pattern |
| outside | `env`, `ops`, `dependency` | the cause is outside what the spec describes | none here; link where it's handled |

When two layers are involved, record the earliest one that, fixed alone, would have prevented the signal.

Record the proposal, unconfirmed:

```bash
tools/specloop signal triage <id> --layer <layer> --kind <kind> \
    --confidence <low|medium|high> --reasoning "<one or two sentences citing the rule and the code>"
```

`low` means you'd want someone who knows the feature to look before acting on it.

## 4. Draft the fix (don't apply it)

Draft the fix for that layer:
- **spec:** the exact rule text to change or add, with its ID (a new rule gets a new number; IDs are never reused), ready for a spec PR whose commit ends with `Fixes-Signal: <id>`. Once it merges, `/spec-sync` builds it, sees the signal through `signals --pending`, and the signal closes when the code is built.
- **implementation:** what's wrong in the code, by rule ID. Suggest a re-sync or a hand fix whose trailers name the rule and the signal: `tools/specloop trailers --rules <ID> --human --fixes <id>`.
- **verification:** the test to add or strengthen, tagged with the rule ID, committed with `Fixes-Signal: <id>`.
- **harness:** a dated entry for `docs/lessons.md` (what happened, the takeaway). Then run `tools/specloop signals --by harness`. Propose a change **only** if it reports a pattern for this layer and kind, and cite the signal IDs it lists. One bad session isn't evidence about the instructions. The skills ship with specloop, so a fix to one is an issue or PR against specloop, not an edit here. A fix that's specific to this project goes in `CLAUDE.md`'s "Spec sync rules for this project" section, outside specloop's markers.
- **outside:** where it should go instead.

## 5. Report

Keep it short:
- the signal ID and what it traced to (rules with versions, commits, harness)
- the proposed layer and kind, the confidence, and why
- the drafted fix
- what you couldn't check

Then ask the user to confirm the triage. Unconfirmed triage counts for nothing in reports. On a yes:

```bash
tools/specloop signal confirm <id>
```

A fix whose commit says `Fixes-Signal: <id>` closes the signal by itself once it's on the default branch. A spec change closes it once the sync that builds it is merged. Close it by hand only when no commit will: `tools/specloop signal resolve <id> --status fixed --fix "<lesson or link>"` (a harness lesson, an outside fix), `wontfix` for one you won't act on, `duplicate` for one that's the same as another.

Commit the signal file with the fix, or on its own, so the rest of the team sees it.
