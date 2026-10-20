## Spec-driven development (specloop)

- **`docs/SPEC.md` is the source of truth** for what this project does. Read it before changing behavior.
- Committing, merging or pulling a change to the spec starts `/spec-sync` as a background session in its own worktree (`tools/githooks/`). Enable it per clone with `git config core.hooksPath tools/githooks`. To skip it once, use `SPEC_SYNC=off`. `tools/specloop status` shows where each pending spec revision stands.
- `docs/.spec-implemented` holds the commit whose spec the code matches. Only `/spec-sync` advances it, or `tools/specloop mark` after a hand-made spec+code commit.
- Tests name the spec IDs they check at the start of their name, e.g. `@Test("XP-6: …")`. `tools/specloop coverage` reports which IDs have tests and fails on IDs the spec doesn't define.
- Any direct code change that alters behavior must update the spec in the same commit.

### Spec sync rules for this project

<!-- Checks /spec-sync must apply here on top of its generic steps, e.g. "threshold changes need eval numbers", "don't bump the version", "update store copy". Delete this section if there are none. -->
