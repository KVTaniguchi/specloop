# Your first sync

From install to a reviewed sync branch on your own iOS app. It takes about half an hour, most of it reviewing the first spec.

You need a Mac with Xcode, an app in a git repository, and Claude Code or Cursor. The steps below use Claude Code; Cursor differences are noted.

## 1. Install specloop

```bash
brew install KVTaniguchi/tap/specloop
```

## 2. Set up the project

```bash
cd /path/to/YourApp
specloop init
```

This writes small files that defer to the installed specloop: `tools/specloop`, the git hooks in `tools/githooks/`, the `/spec-sync`, `/spec-init` and `/spec-triage` skills in `.claude/skills/`, specloop's block in `CLAUDE.md`, and `specloop.json`. It never overwrites a spec or config you already have.

Open `specloop.json` and fill in how your tests run. For an Xcode project with Swift Testing:

```json
"tests": {
  "paths": ["YourAppTests", "YourAppUITests"],
  "extensions": [".swift"],
  "tagStyles": ["swift-testing", "comment"]
},
"commands": {
  "test": "xcodebuild -project YourApp.xcodeproj -scheme YourApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test"
}
```

`comment` lets XCTest and UI tests tag themselves with a `// Spec: XP-6` line.

## 3. Draft the spec from your code

In Claude Code, in the project folder:

```
/spec-init
```

The agent reads your models, services and screens, then drafts a spec of what the app does **today**: one doc per feature under `docs/spec/`, every rule with a bold ID such as `**XP-2:**`. It tags the tests you already have with the IDs they check, commits, and records that spec revision in `docs/.spec-implemented` as the baseline. It ends with a report: coverage, untested areas, and any places where the spec and the code disagreed.

Review the draft. It's the contract from now on. Check that user-facing text is copied exactly, that numbers and tables match the code, and that quirks are written down as they are rather than "fixed" in prose. If you correct it, commit your fixes with `SPEC_SYNC=off`, then move the baseline to include them:

```bash
tools/specloop mark HEAD
git commit -m "Mark spec as implemented" docs/.spec-implemented
```

See where you stand:

```bash
tools/specloop coverage
```

Every rule is listed with the number of tests that name it. Rules with no test are the gaps to fill over time. List the prefixes that must always be covered under `sync.require`, and coverage fails while any of them has a gap.

## 4. Turn on the trigger

The hook starts a background agent that edits code on its own, so it's off until you turn it on in your clone:

```bash
git config core.hooksPath tools/githooks
```

Background sessions need the command-line `claude` to be logged in (`claude auth status`, then `claude auth login` if needed) and the project folder to be trusted (run `claude` in it once and accept the prompt). For Cursor, run `git config specloop.harness cursor` and log in with `agent login`.

Then check the whole setup:

```bash
tools/specloop doctor
```

It prints a line per check (config, tests, spec, ledger, the project's specloop files, the trigger, the claude CLI's login and folder trust) and the fix for anything that's wrong.

## 5. Try it as a dry run

Change one rule in the spec, for example a value in a table, and commit with the trigger in dry-run mode:

```bash
SPEC_SYNC=dry-run git commit -am "Rare catches pay 75 XP"
```

```
specloop: would start background claude session 'Spec sync 11f07fa'
```

`tools/specloop status` now shows the rule as pending:

```
pending:     XP-1
  11f07fa  not started      run /spec-sync
```

## 6. Run a real sync

Make your next spec change a real one and commit it normally. The hook starts a background Claude Code session in its own worktree (`.claude/worktrees/spec-sync-<sha>`, or `.specloop/worktrees/` for Cursor), on a `spec-sync/<sha>` branch. Your checkout isn't touched, so you can keep working.

Follow it with `tools/specloop status`, which moves through `starting`, `running` and `awaiting review`. In Claude Code, `claude agents` lists the session, and `claude attach "Spec sync <sha>"` lets you watch. For Cursor, the log is at `.git/specloop/logs/<sha>.log`.

The agent builds the change, writes or updates tests tagged with the rule IDs, runs your test command and coverage, records the new spec revision in the ledger, and commits with trailers that name the rules it built.

## 7. Review and merge

When `status` says `awaiting review`, review the `spec-sync/<sha>` branch like any other change: read the diff, and run the app if the change is visible. To share it as a pull request, push the branch yourself; the agent doesn't push. Once it's merged, `status` shows nothing pending and the hooks remove the sync's worktree.

If a sync gets stuck, `status` says `blocked` or `failed` with the reason, and you can run `/spec-sync` by hand.

## Next

- [Gate CI on the spec](ci.md): fail a pull request when the spec and the code drift apart.
- [Attribution and feedback](attribution.md): trace a crash or failing test to its rule with `specloop blame` and `/spec-triage`.
- [Writing a spec](spec-format.md): good rules, IDs and tag styles.
- Add project-specific rules for the agent, such as "never bump the build number", under "Spec sync rules for this project" in `CLAUDE.md`.
