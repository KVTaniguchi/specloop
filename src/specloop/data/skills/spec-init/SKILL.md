---
name: spec-init
description: Set up specloop spec-driven development in an existing project — draft the spec from the code as it is today, tag the existing tests, and record the baseline. Use when the user wants to start spec-driven development, "write a spec for this project", or adopt specloop.
---

# Spec init

The goal: a spec that describes what the project **does today**, accurately enough that a later spec diff can be turned into code. You aren't writing a wish list.

## 1. Install the plumbing

If `tools/specloop` doesn't exist, run `specloop init` at the project root (install specloop first with `brew install KVTaniguchi/tap/specloop` or `pipx install specloop` if it isn't). Then fill in `specloop.json`:
- `commands.test`: the exact command that runs the test suite
- `tests.paths`: the test directories
- `tests.tagStyles`: which tag styles the project's test framework uses

## 2. Read before writing

Read the code, not just the README: models, services and every screen or endpoint. Record user-facing text exactly, and note thresholds, formulas and tables. Check the git history to see which features are recent.

## 3. Draft the spec

A spec is a tree of docs (the default, `"spec": "docs/spec"`), or one file for a small project (`"spec": "docs/SPEC.md"`).

For a tree, start from the templates `specloop init` put in `docs/spec/`:
- **`README.md` is the overview:** what the product is, its pillars and non-goals, and a link to every feature doc. Rules that cut across features go here too.
- **One doc per feature**, from `docs/spec/feature.md`, e.g. `docs/spec/scanning.md`. A large feature can be a folder with its own `README.md` that links to its parts.
- **Every doc must be reachable by links from the overview.** `tools/specloop check` fails on broken links and on docs nothing links to.

Either way:
- **Give every rule a stable ID** in bold: `**PREFIX-N:**`. Use one prefix per area (`XP`, `SCAN`, `AUTH`). In a tree, one prefix per feature doc keeps them easy to find. IDs are unique across the whole spec, and permanent: retire one rather than reuse it.
- **One checkable claim per ID.** A rule is "level n takes 50·n·(n−1) XP", not "levels feel fair".
- **Tables are rules too.** Give each table its own ID in the line above it.
- **Write down quirks as they are** (for example, "the Map tab hosts the camera"). If you think one is a bug, tell the user; don't fix it in the spec.
- **Include non-goals.** They're what lets a later sync refuse a change that breaks them.
- **Keep secrets and private identifiers out of it**: no API keys or account IDs.

## 4. Tag the tests that already exist

For each existing test that checks a rule, add the IDs at the start of its name. Then run `tools/specloop coverage`.
- If writing a test exposes a place where the spec and the code disagree, that's a spec bug. Fix the spec to match the code, and tell the user.
- Delete empty template tests.

## 5. Record the baseline

The baseline needs two commits, because a commit can't contain its own SHA:

```bash
SPEC_SYNC=off git commit -m "Add spec and specloop"   # off: don't start a sync for the baseline
tools/specloop mark HEAD
git commit -m "Mark spec as implemented" docs/.spec-implemented
tools/specloop check                                  # links, IDs and tags all line up
```

## 6. Report

Report these:
- coverage (N of M IDs)
- which areas have no tests, and why: logic stuck inside UI code, no UI tests, or the rule depends on data
- any disagreements between the spec and the code you found

Suggest the next layer of tests to add, with no more than three items.
