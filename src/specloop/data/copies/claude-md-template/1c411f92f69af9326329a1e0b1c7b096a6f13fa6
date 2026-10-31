## Spec-driven development (specloop)

- **`docs/SPEC.md` is the source of truth** for what this project does. Read it before changing behavior.
- Committing a change to the spec starts `/spec-sync` as a background session in its own worktree (`tools/githooks/post-commit`). Enable it per clone with `git config core.hooksPath tools/githooks`. To skip it for one commit, use `SPEC_SYNC=off`.
- `docs/.spec-implemented` holds the commit whose spec the code matches. Only `/spec-sync` advances it, or `tools/specloop mark` after a hand-made spec+code commit.
- Tests name the spec IDs they check at the start of their name, e.g. `@Test("XP-6: …")`. `tools/specloop coverage` reports which IDs have tests and fails on IDs the spec doesn't define.
- Any direct code change that alters behavior must update the spec in the same commit.
