---
name: spec-sync
description: Implement the pending changes in the project's spec (specloop). Use when the spec has changed since its implemented revision, when started by the specloop post-commit hook, or when the user says "sync the spec" or "build what's in the spec".
---

# Spec sync

The spec (path in `specloop.json`, usually `docs/SPEC.md`) is the source of truth for what this project does. The ledger file records the commit whose spec the code currently matches. Your job is to make the code match the spec at `HEAD`, then advance the ledger.

`tools/specloop` does the bookkeeping. Run `tools/specloop --help` if you need details.

## 1. Find the pending change

```bash
tools/specloop pending         # the spec diff since the implemented revision
tools/specloop pending --ids   # the rule IDs on changed lines
```

- If nothing is pending, report that the spec and the code already match, and stop.
- If the spec has uncommitted edits, stop and ask the user to commit them first. A sync only works from committed spec revisions.
- Read the **whole** spec, not just the diff. A change in one section often affects rules in other sections.

## 2. Branch

Read the prefix with `tools/specloop config sync.branchPrefix` (default `spec-sync/`).
- If you're on the default branch, create `<prefix><short-sha-of-HEAD>`.
- If the hook started you in a worktree on some other branch, rename that branch to the same name with `git branch -m`.

## 3. Plan, then build

- Turn each diff hunk into concrete code changes, and name the rule IDs you're addressing.
- **Never edit the spec.** If a change is ambiguous, contradicts another rule, or breaks the spec's own non-goals, stop. Put the question in your report instead of guessing.
- Follow the project's existing conventions (see `CLAUDE.md`).
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
tools/specloop mark HEAD     # before making your own commit; HEAD is the spec revision you implemented
```

- Make one commit with the code, the tests and the ledger. Use the message `Spec sync: <one-line summary>` and list the rule IDs in the body.
- **Don't** push or merge into the default branch. The user reviews and merges.

## 6. Report

Keep it short:
- what changed, by rule ID
- test and coverage results
- anything you couldn't verify
- open questions about the spec

Then add one line to the report if anything about the *process* surprised you, such as a rule that was hard to test or a hunk without an ID. That's the raw material for specloop's lessons.
