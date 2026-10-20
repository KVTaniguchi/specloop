# <Project> — Spec

> **This document is the source of truth for what <Project> does.**
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

## 2. Rules
<!-- Logic that can be checked without a UI: formulas, tables, state machines, limits. Aim for full test coverage here. -->

### 2.1 <Area>
- **<PFX>-1:** <One checkable claim.>
- **<PFX>-2:** <Each tier pays exactly:>

| Tier | Value |
|---|---|
| … | … |

---

## 3. Screens / interfaces
<!-- What a user sees and can do. Record user-facing text exactly. -->

### 3.1 <Screen> (`<PFX>`)
- **<PFX>-1:** <What it shows.>
- **<PFX>-2:** <What each action does.>

---

## 4. Data
- **DATA-1:** <Persistence rules, such as which migrations are allowed.>

---

## 5. Testing and release
- **REL-1:** Tests name the spec IDs they check at the start of their name, e.g. `@Test("PFX-1: …")`. `tools/specloop coverage` reports which IDs have tests.

---

## How this spec works

1. **This file describes the project as it is right now.** If it isn't written here, the project shouldn't do it. If it's written here, the project should do it.
2. **To change the project, edit this file and commit.** Give new rules an ID. Never reuse a retired ID.
3. **A commit that changes this file starts a background `/spec-sync` session.** It builds the change on a `spec-sync/…` branch for you to review. To skip it for one commit, use `SPEC_SYNC=off git commit …`.
4. **`docs/.spec-implemented`** records the commit whose spec the code matches. `/spec-sync` advances it.
5. **Change the code directly when you need to**, but update this file in the same commit.
6. **`/spec-sync` never edits this file.** If a change is ambiguous, it stops and asks.
