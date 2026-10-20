# Lessons from real use

What happened when specloop was applied to a real project, the fix or open question, and whether the tool changed because of it. Newest at the top. Add entries as you go; one paragraph each is enough.

**Source project:** a shipped iOS app (SwiftUI + SwiftData, ~4.8k lines of Swift, on-device Core ML), adopted in October 2026. Called "the app" below.

---

### 2026-10-20 — Editing a table row didn't register as a rule change
While testing specloop against the app, changing one cell in the XP table (`Common | 10` → `12`) produced an empty `pending --ids`. The table's ID sits on the line *above* the table, so the changed line itself names no ID. A sync would have had to work out which rule the change touched.
**Fix:** a changed line belongs to the nearest ID defined at or above it, up to the next heading. Table rows, continuation lines and sub-bullets now count toward their rule.
**Tool change:** `specloop pending --ids` and `status` use that ownership rule.

### 2026-10-17 — Rules buried in views can't be tested
After the spec was drafted, about a third of the §2 game rules lived inside SwiftUI views as private functions: XP-on-relabel, achievements, the "Cat Presence" label, and confidence routing. The coverage report showed them as ✗, and no test could reach them. A second pass moved them into plain model types first (behavior unchanged), then tested them. Coverage went from 14/82 to 26/82.
**Takeaway:** coverage gaps cluster where logic sits next to UI. `/spec-init` should report *why* an ID is uncovered (logic inside UI code, no UI harness, depends on data), because each has a different fix.
**Tool change:** spec-init step 6 asks for exactly that breakdown.

### 2026-10-16 — Writing tests found spec drift right away
Tagging tests against a freshly drafted spec found two errors within an hour. The spec said spawn pins keep fixed positions, but the code anchors them to the player's current location. The spec's list of debug launch arguments was missing two. Both were cases of the spec being wrong, not the code.
**Takeaway:** a spec drafted from reading code is a hypothesis until tests confirm it. Draft, tag, and fix the spec before you call it the baseline.
**Tool change:** spec-init step 4 treats a test/spec disagreement as a spec bug to fix and report.

### 2026-10-16 — The baseline needs two commits
The ledger has to hold the SHA of the commit containing the implemented spec, and a commit can't contain its own SHA. Also, the commit that adds the spec would trigger a sync of itself.
**Fix:** commit the spec with `SPEC_SYNC=off`, then `specloop mark HEAD` and commit the ledger separately. Until a ledger exists, the commit that first added the spec counts as the baseline.
**Tool change:** built into `specloop mark` and the spec-init skill.

### 2026-10-16 — Edits that only touch IDs still trigger a sync
Adding IDs to existing tables changed the spec without changing behavior, but the hook can't tell the difference.
**Fix:** `SPEC_SYNC=off` for edits that only touch IDs or wording, then `specloop mark`.
**Open question:** should the hook skip diffs that only add `**ID:**` markers? Not yet — the false-negative risk seems worse than an occasional no-op sync.

### 2026-10-16 — Auto-starting agents needs explicit approval
Claude Code's auto-mode safety check blocked writing the post-commit hook itself, because it creates autonomous agents. The user had to approve it explicitly before it could be added.
**Takeaway:** this is the right default. Setup docs should say plainly that the hook starts background agents and needs the user's opt-in, and that `/spec-sync` by hand is the fallback.
**Tool change:** README's "Enable the trigger" step explains this.

### 2026-10-16 — The first draft of the spec came from the code, not from intent
For an app that already existed, drafting the spec from intent ("what should it do?") would have produced a wish list that didn't match the code. Drafting from code produced an accurate baseline. It also wrote down odd behavior faithfully (the "Map" tab hosts the camera) rather than fixing it quietly.
**Takeaway:** for existing projects, describe what the code does first. Intent changes come afterwards as normal spec diffs.

---

## Open questions
- How do two pending spec syncs interact? Committing a second spec change before merging the first sync branch means the second sync redoes the first one's work. A lock or queue may be needed. *(Not yet observed in practice.)*
- What's the right way to cover rules about UI feel (animation, palette)? Screenshot comparison, a human checklist, or just leave them as untested promises?
- The automatic trigger has been dry-run tested but hasn't yet carried a real spec change from start to finish.
