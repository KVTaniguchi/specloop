# Lessons from real use

What happened when specloop was applied to a real project, the fix or open question, and whether the tool changed because of it. Newest at the top. Add entries as you go; one paragraph each is enough.

**Source project:** a shipped iOS app (SwiftUI + SwiftData, ~4.8k lines of Swift, on-device Core ML), adopted in October 2026. Called "the app" below.

---

### 2026-10-31 — Moving the app to the Homebrew install rewrote its CLAUDE.md wrongly (the app)
The first `specloop update` from the old copied install to 0.1.2 did two wrong things to the app's `CLAUDE.md`. specloop's block said "the spec in `docs/spec/` is the source of truth", but the app keeps one file, `docs/SPEC.md`: the block's text was written for a tree and ignored `specloop.json`. And the old hand-pasted section had a rule of the app's own ("Keep the spec in view": open the rule in the Files pane, link rule IDs to their lines). `update` treated the whole section as specloop's and replaced it, so the rule disappeared, shown only in the diff it printed. `specloop doctor` didn't catch either one, because it checks the files, not the block's text. Reading the diff before committing did; the change was stashed, not committed.
**Tool change:** the block is rendered from `specloop.json`: a single file or a tree, and the ledger's path. When `update` moves a pasted section into the block, it keeps every line that doesn't match some version of the template (a fuzzy match, since projects pasted older wordings) under "Kept from the old specloop section", and says how many it kept. Here that kept "Keep the spec in view" and a note about updating through `install.sh`, which was out of date and was deleted by hand.
**Takeaway:** `update` must never silently drop words a project wrote. When it can't tell whose a line is, it keeps it.

### 2026-10-21 — A sync started from `origin/main`, without the spec change (the app)
The app's ACH-1 spec commit was committed but not pushed. The hook started `claude --bg --worktree spec-sync-<sha>`, and Claude Code cut that worktree from `origin/main`, three commits behind. The session found nothing pending, stopped, and never ran `specloop sync`, so `status` said `failed to start?` for five hours. A second sync, started by hand in its own worktree, had the same problem. It merged local `main` in to get the spec change, and that merge fired the post-merge hook, which started a third, duplicate sync, also from `origin/main`. Then `status` kept showing ACH-1 as failed, because the sync that did build it had recorded itself under a later commit that didn't touch the spec.
**Tool change:** the hook now makes the Claude Code worktree at `HEAD` itself and starts `claude --bg` inside it. The trigger never starts a sync from a linked worktree. `/spec-sync` records `sync failed` when the hook started it and nothing is pending, which reports on the launch record. `status` credits a sync of a later commit to the pending revisions it builds.
**Cost:** Claude Code no longer locks the worktree with the session's pid, so a dead session is noticed when the sync goes quiet (10 minutes for a launch, `sync.staleAfterMinutes` once running) instead of at once.

### 2026-10-21 — A spec rule that quoted config values went stale (the app)
The app's REL-4 said coverage fails "if a BREED or LVL rule has no test", which copied the `sync.require` list from `specloop.json`. Once tier 2 landed and XP and ACH were added to that list, the rule was wrong. Nothing caught it, because `specloop check` validates IDs and tags, not whether the spec's prose matches the config.
**Fix:** the rule now points at the config ("a rule with one of the prefixes listed under `sync.require`") instead of copying its values.
**Takeaway:** when a rule is really about the tooling's configuration, point at the config. Don't copy its values into the spec.

### 2026-10-20 — Hooks hand their git variables to everything they start
The first real test of worktree cleanup failed when it ran from `post-commit`. Run by hand, the same cleanup worked. While a commit hook runs, git sets `GIT_INDEX_FILE=.git/index`, a path relative to the main checkout. Every git command cleanup ran in the sync's worktree inherited it and failed with `.git/index: index file open failed`. The background session the hook launches inherited it too, along with the commit's `GIT_AUTHOR_DATE`. The earlier successful end-to-end run had escaped this only because the hook was run by hand rather than through `git commit`. `post-merge` doesn't set the index variable, so the merge-based tests had passed.
**Tool change:** the hook unsets git's repository and commit-identity variables first thing, and the CLI strips the repository ones from every git call. Regression tests fail without the fix.
**Takeaway:** test a hook through the git command that fires it, not by running the script directly.

### 2026-10-20 — Claude Code's worktrees show up in `git status`
`.claude/worktrees/` was untracked in the main checkout. Claude Code doesn't exclude it, so `git add -A` would stage a running sync's worktree as an embedded repository.
**Tool change:** before launching, the hook adds `.claude/worktrees/` to the clone's `.git/info/exclude` if it isn't already ignored.

### 2026-10-20 — The worktree lock names the session's process
While a real sync was running, its worktree lock said `pid 59206`. `claude agents` reported pid 59206 for the session, and that pid was the `claude bg-spare` process. In the previous run, `claude stop` ended that process. So cleanup can rely on the lock: the session has died if its pid is gone, and stopping the session frees the worktree.

### 2026-10-20 — First end-to-end run of the trigger
On a toy Python project (not the app), committing a spec change (XP-1 by rarity, new XP-2) started a background session through the hook. In about a minute the session renamed its branch, reported `running`, implemented both rules with tagged tests, reached 3/3 coverage, marked the ledger and reported `done`. `status` showed `awaiting review`. A fast-forward merge brought the ledger to the spec revision, and `post-merge` correctly didn't start another sync. The session's process note said it found nothing surprising. It took three attempts to get there; the next three entries cover why.
**Takeaway:** the loop works once the environment is right. Every failure was in the environment, not in the skill.
After `done`, Claude Code leaves the worktree (`.claude/worktrees/spec-sync-<sha>`) in place and locked. A launch that dies also leaves its worktree locked, with a lock naming a process that has exited.
**Tool change:** `specloop cleanup`, run by the hooks, removes a sync's worktree once its revision is implemented or its session has died. It keeps anything still running, waiting for review, blocked, or carrying uncommitted changes. A session can't remove the worktree it's running in, so cleanup has to happen from outside it. The lock's pid also gives a quicker death signal than the timeouts.

### 2026-10-20 — A background session only starts in a trusted folder
The first launch failed immediately with "Workspace not trusted". The old hook sent `claude --bg` output to `/dev/null`, so this would have been silent. The new hook reported it, and `status` showed `failed`. After running `claude` in the folder and accepting the prompt, trust still didn't stick for a folder under the system temp directory (`/private/tmp/…`). The cause isn't confirmed. Moving the project to `~/Development` fixed it.
**Fix:** the README install steps now say to run `claude` in the project once and accept the trust prompt before enabling the trigger.
**Tool change:** on a launch failure, the hook puts the first line of claude's output in the record and in its own message.

### 2026-10-20 — The CLI's login is separate from the desktop app's
The second launch started a session that died at once with "Login expired". The desktop app was signed in, but the command-line `claude` that the hook calls was not (`claude auth status` showed `"loggedIn": false`). The reason only appeared in `claude logs <id>`. `status` flagged the sync `failed to start?`, but only after 10 minutes.
**Tool change:** the hook checks `claude auth status` before launching and fails right away with "run claude auth login". `status` points at `claude logs <id>` for a session that went quiet.

### 2026-10-20 — `claude --bg` ignores `--session-id`
The hook tried to choose the session ID up front so the record could name it before launch. `--bg` prints a warning and picks its own ID.
**Tool change:** the hook reads the ID from the launch output (`backgrounded · <id> · …`). It records it with `specloop sync --session-id <id>`, a field-only update that leaves the status alone in case the session has already reported `running`.

### 2026-10-20 — Moving to the generic skill dropped the app's own sync rules
The app's original hand-written `/spec-sync` contained project-specific checks: model threshold changes need evaluation numbers, store copy must follow feature changes, never bump the build number, and the Simulator can't check camera features. Replacing it with the generic skill would have dropped all of them without anyone noticing.
**Fix:** projects keep these in a **"Spec sync rules for this project"** section of `CLAUDE.md`, and the generic skill applies that section on top of its own steps.
**Tool change:** spec-sync step 3 reads the section, and `templates/CLAUDE.md` includes an empty one.

### 2026-10-20 — A wrong test path silently reported 0% coverage
While moving the app over, coverage briefly reported 0/82 because the config wasn't loaded and the default `tests/` path didn't exist. That looks exactly like a project with no tests.
**Fix:** `specloop coverage` now warns on stderr when it scans no test files at all.
**Tool change:** done.

### 2026-10-20 — Editing a table row didn't register as a rule change
While testing specloop against the app, changing one cell in the XP table (`Common | 10` → `12`) produced an empty `pending --ids`. The table's ID sits on the line *above* the table, so the changed line itself names no ID. A sync would have had to work out which rule the change touched.
**Fix:** a changed line belongs to the nearest ID defined at or above it, up to the next heading. Table rows, continuation lines and sub-bullets now count toward their rule.
**Tool change:** `specloop pending --ids` and `status` use that ownership rule.

### 2026-10-18 — The code-first rule held without anyone enforcing it
Two days after the baseline, a layout-only change for small and wide screens (onboarding, the success sheet, grid columns) went straight to code. The commit message ended with "Layout only; no spec change." The session that made it had read the CLAUDE.md rule and decided, correctly, that the spec described behavior, not layout.
**Takeaway:** writing "no spec change" in the commit message makes the decision visible and checkable later.
**Tool change:** the app's CLAUDE.md now asks for that line. **Open question:** should a `commit-msg` hook warn when app code changes with neither a spec change nor a "no spec change" note?

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

### 2026-10-21 — The spec is out of sight, and there's no obvious way to point at a rule
On KTCatPokemon the user had to ask to see the spec every time it came up, and wasn't sure how to propose a change: copy-paste a passage into chat? There's no equivalent of `File.swift:42` for the spec. Rule IDs (`SCAN-5`) are that reference and are steadier than line numbers, but nothing in the workflow teaches that. And a table row inside a rule (one SCAN-5 outcome) has no ID of its own.
**Open question:** should specloop ship a spec view that stays beside the chat, with rule IDs you can click to drop into a prompt, plus pending and coverage status? Should the skills always open the spec at the rule they're discussing? Does a README section on "how to ask for a spec change" cover enough?

---

## Open questions
- How do two pending spec syncs interact? Committing a second spec change before merging the first sync branch means the second sync redoes the first one's work. *Partly addressed:* the hook no longer starts a sync while another is running, and `status` lists the newer revision as not started until someone runs `/spec-sync` after the first branch is merged. Whether that's the right flow is untested. *(Not yet observed in practice.)*
- What's the right way to cover rules about UI feel (animation, palette)? Screenshot comparison, a human checklist, or just leave them as untested promises?
- The automatic trigger has been dry-run tested but hasn't yet carried a real spec change from start to finish.
