# <Project> — Spec

> **This tree of documents is the source of truth for what <Project> does.**
> When it changes, the code changes to match it. See [How this spec works](#how-this-spec-works) at the end.

- **Platform:** <e.g. iOS 18+, iPhone only>
- **Naming:** <canonical product terms, and terms to avoid>

---

## 1. Product

### 1.1 What it is
<Two or three sentences: who it's for and what they do with it.>

### 1.2 Pillars
1. **<Pillar>.** <One line on what this means in practice.>

### 1.3 Non-goals
- <Things this project deliberately does not do. /spec-sync refuses changes that break these.>

---

## 2. Features
<!-- One doc per feature, next to this file. Every doc in this folder must be linked from here, or from a doc linked from here. -->

| Feature | Doc | IDs |
|---|---|---|
| <Feature> | [<feature>.md](feature.md) | `<PFX>` |

---

## 3. Cross-cutting rules
<!-- Rules that belong to no single feature: data, persistence, accessibility, release. -->
- **DATA-1:** <Persistence rules, such as which migrations are allowed.>
- **REL-1:** Tests name the spec IDs they check at the start of their name, e.g. `@Test("PFX-1: …")`. `tools/specloop coverage` reports which IDs have tests.

---

## How this spec works

1. **These docs describe the project as it is right now.** If it isn't written here, the project shouldn't do it. If it's written here, the project should do it.
2. **To change the project, open a pull request against the spec.** Edit the docs, give new rules an ID, and never reuse a retired ID. A new feature gets its own doc, linked from [Features](#2-features).
3. **Once the change is merged and pulled, the author's coding agent builds it.** The specloop hook starts a background `/spec-sync` (Claude Code or Cursor) on the machine of whoever wrote the spec change. It builds the change on a `spec-sync/…` branch for review. To skip it for one commit, use `SPEC_SYNC=off git commit …`.
4. **`docs/.spec-implemented`** records the commit whose spec the code matches. `/spec-sync` advances it.
5. **Change the code directly only when you must**, and update the spec in the same commit.
6. **`/spec-sync` never edits the spec.** If a change is ambiguous, it stops and asks.
