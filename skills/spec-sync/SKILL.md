---
name: spec-sync
description: Implement the pending changes in the project's spec (specloop). Use when the spec has changed since its implemented revision, when started by the specloop post-commit hook, or when the user says "sync the spec" or "build what's in the spec".
---

# Spec sync

The spec is the source of truth for what this project does. Its path is in `specloop.json`. It's either one Markdown file, or a directory of them: a `README.md` overview at the top that links to one doc per feature. The ledger file records the commit whose spec the code currently matches. Your job is to make the code match the spec at `HEAD`, then advance the ledger.

This skill works the same in Claude Code and in Cursor. Where it says `CLAUDE.md`, read `AGENTS.md` too if the project has one.

`tools/specloop` does the bookkeeping. Run `tools/specloop --help` if you need details.

## 1. Find the pending change

```bash
tools/specloop pending         # the spec diff since the implemented revision
tools/specloop pending --ids   # the rule IDs on changed lines
```

- If nothing is pending, report that the spec and the code already match, and stop.
- If the spec has uncommitted edits, stop and ask the user to commit them first. A sync only works from committed spec revisions.
- Read more than the diff. For a single file, read all of it. For a tree, read the overview, every doc the diff touches, and the docs those link to. A change in one feature often affects rules in another.

## 2. Branch

Read the prefix with `tools/specloop config sync.branchPrefix` (default `spec-sync/`).
- If you're on the default branch, create `<prefix><short-sha-of-HEAD>`.
- If you're already on that branch (the hook makes it for Cursor), stay on it.
- If the hook started you in a worktree on some other branch, rename that branch to the same name with `git branch -m`.

Then record that the sync is underway, so `tools/specloop status` can show it and the hook won't start a second one:

```bash
tools/specloop sync running
```

## 3. Plan, then build

- Turn each diff hunk into concrete code changes, and name the rule IDs you're addressing.
- **Never edit the spec**, in any of its docs. If a change is ambiguous, contradicts another rule, or breaks the spec's own non-goals, stop. Run `tools/specloop sync blocked --note "<the question, one line>"` and put the question in your report instead of guessing.
- Follow the project's existing conventions (see `CLAUDE.md`). If `CLAUDE.md` has a **Spec sync rules** section, those rules apply on top of this skill. That's where project-specific checks go, such as evaluation numbers for model thresholds or store copy to keep in step.
- Every rule you add or change gets a test. Tag the test with the rule IDs at the start of its name, before the first colon: `@Test("XP-6: …")`, `it("XP-6: …")`, `@pytest.mark.spec("XP-6")`, or a `// Spec: XP-6` comment above the test.
- If the diff renames or removes an ID, update the tests that name it.

## 4. Verify

Run the project's test command, which is `tools/specloop config commands.test`. It must pass. If you changed UI, run the app and look at it.

```bash
tools/specloop coverage --ids "$(tools/specloop pending --ids | paste -sd, -)"
```

- This must exit 0. Every changed ID should show ✓ and no test should name an ID the spec doesn't define.
- If an ID really can't be tested yet (for example, pure UI feel), say so in the report instead of skipping it quietly.
- Also run `tools/specloop coverage` with no arguments to check that the required prefixes are still covered.

## 5. Commit

```bash
tools/specloop mark HEAD                         # before making your own commit; HEAD is the spec revision you implemented
tools/specloop trailers --model <your model ID>  # the trailer block for this sync's commit
```

- Make one commit with the code, the tests and the ledger. Use the message `Spec sync: <one-line summary>`, then a body saying what changed by rule ID, then a blank line and the trailer block **exactly as `trailers` printed it**. The trailers are how a later crash or review comment is traced back to these rules and to this harness, so don't edit or drop them.
- `--model` is the model ID you're running as (e.g. `claude-opus-5-5`). Leave it out only if you don't know it.
- **Don't** push or merge into the default branch. The user reviews and merges.

Then record the outcome:

```bash
tools/specloop sync done                              # committed, ready for review
tools/specloop sync failed --note "<what broke>"      # tests or coverage won't pass and you're stopping
```

Always record one of `done`, `blocked` or `failed` before you finish. Otherwise `status` shows the sync as running until it goes stale.

## 6. Report

Keep it short:
- the branch to review, and that it's checked out in this worktree (`git rev-parse --show-toplevel`) if the hook started you. The worktree is removed automatically once the branch is merged.
- to share it as a pull request, the user pushes the branch; you don't. Give them a PR description that ends with the same trailer block, because a squash merge of a one-commit PR can use the description as the commit message.
- what changed, by rule ID
- test and coverage results
- anything you couldn't verify
- open questions about the spec

Then add one line to the report if anything about the *process* surprised you, such as a rule that was hard to test or a hunk without an ID. That's the raw material for specloop's lessons.
