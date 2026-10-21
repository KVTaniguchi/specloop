# Writing a specloop spec

A spec is ordinary Markdown with one convention: **every rule has a stable ID, in bold, where it's defined.**

## The tree

Point `spec` in `specloop.json` at a directory (`"spec": "docs/spec"`) and every `.md` file under it is part of the spec:

- **`README.md` at the top is the overview.** It says what the product is, lists its non-goals, and links to every feature doc. Rules that cut across features live here.
- **One doc per feature**, with its own ID prefix. A feature that grows can become a folder with its own `README.md` linking to its parts.
- **Links hold it together.** `specloop check` fails when a link points at a spec doc that doesn't exist, or when a doc can't be reached by following links from the overview. Link to a folder with a trailing slash (`[Billing](billing/)`) to mean its `README.md`.
- **IDs are unique across the tree.** Moving a rule to another doc keeps its ID; that isn't a reuse.
- **Renaming a doc** counts as removing it and adding it, so its rules show as pending. Rename in a commit of its own with `SPEC_SYNC=off`, then `specloop mark`.

A small project can keep one file (`"spec": "docs/SPEC.md"`). Everything below applies to both.

```markdown
- **XP-2:** Picking a different breed pays the scanner's XP, not the picked breed's.
```

## IDs

- **Format:** `PREFIX-N`, matching `[A-Z][A-Z0-9]*-\d+` by default (`idPattern` in `specloop.json`).
- **Where an ID is defined:** a bold `**ID` marks the definition (`definitionPattern`). Elsewhere you can mention an ID in plain text without defining it again.
- **One prefix per area**, short and obvious: `XP`, `LVL`, `SCAN`, `AUTH`, `BILLING`.
- **IDs are permanent.** When a rule goes away, delete it and don't reuse the number. A test that still names the ID then fails coverage as a stale tag, which is the point.
- **Numbering doesn't need to be in order.** Adding `XP-6` above `XP-1` is fine. Renumbering to keep things tidy breaks traceability.

## What makes a good rule

| Weak | Strong |
|---|---|
| Levels feel fair | **LVL-1:** Level *n* takes `50·n·(n−1)` total XP |
| Spawns are random-ish | **SPAWN-1:** Same location bucket + day + dex → identical spawns |
| Errors are handled | **SCAN-8:** Without a camera the app shows *Camera Access Needed* and does not crash |

- **One claim per ID.** If a rule has an "and", consider splitting it.
- **Tables are rules.** Give the table its own ID in the line above it, and test it value for value.
- **Copy user-facing text exactly.** It's both a spec and a test oracle.
- **Write negative rules down** ("no backend", "never recalculated"). Some can't be tested, but `/spec-sync` uses them to refuse changes that would break them.

## Sections

The overview template ([templates/spec/README.md](../templates/spec/README.md)) has product, features, cross-cutting rules, and how the spec works. Each feature doc ([templates/spec/feature.md](../templates/spec/feature.md)) has rules, then screens or interfaces. For a single-file spec, this order works for most projects:
1. **Product:** what it is, pillars, non-goals
2. **Rules:** logic that can be checked without UI. Aim for full test coverage here.
3. **Screens / interfaces:** what users see and do
4. **Data:** storage and migration rules
5. **Testing & release:** how the spec itself is checked
6. **How this spec works:** the contract, written into the spec so every reader sees it

## Tagging tests

A test claims the IDs written **before the first colon** of its name:

| Framework | Form |
|---|---|
| Swift Testing | `@Test("XP-6, BREED-1: every tier pays its reward")` |
| Jest / Vitest / Mocha | `it("XP-6: every tier pays its reward", …)` |
| pytest | `@pytest.mark.spec("XP-6", "BREED-1")` |
| Anything (XCTest, Go, …) | `// Spec: XP-6` or `# Spec: XP-6` on a line by itself |

Add your own patterns under `tests.extraPatterns`. Each is a regex with an `ids` named group.
