# Example: iOS / Swift

A trimmed-down version of how specloop runs on a real SwiftUI app.

- `specloop.json` — Xcode test command, Swift Testing + comment tag styles, `XP` and `LVL` required.
- `docs/SPEC.md` — a spec excerpt: a table rule (XP-1), behavior rules, a screen rule.
- `AppTests/RulesTests.swift` — tests that name the IDs they check.

Try it from this directory:

```bash
../../bin/specloop coverage
```

It reports 4/6 and **exits 1** on purpose: `LVL-2` is required but has no test. That's what the coverage gate looks like when a rule slips through.
