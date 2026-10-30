"""
specloop — keep a spec, the code, and the tests in lockstep.

    specloop status                  ledger, pending spec change, coverage summary
    specloop pending [--ids]         spec diff since the implemented revision
    specloop coverage [--uncovered] [--require P1,P2] [--ids ID,...]
                                     spec ID -> test traceability
    specloop check [--format github] [--allow-pending]
                                     CI gate: IDs, tags, coverage, ledger
    specloop mark [REV]              record REV (default HEAD) as implemented
    specloop sync [STATUS] [--rev REV] [--note TEXT] [--session NAME] [--session-id ID]
                                     record a sync's progress (used by the hook
                                     and /spec-sync): starting, running, done,
                                     blocked, failed. Without STATUS, only
                                     updates the given fields.
    specloop trigger [--since REV]   exit 0 if the hook should start a sync now
    specloop cleanup [--dry-run]     remove sync worktrees that are merged or dead
    specloop harness                 print the coding agent the hook starts here
                                     (claude or cursor)
    specloop config [KEY]            print config (dotted KEY, e.g. sync.branchPrefix)

  Attribution and feedback (docs/attribution.md):
    specloop trailers [--rules ID,... | --none REASON] [--model M] [--human]
                                     print the Spec-Rev / Spec-Rules / Harness
                                     trailers for the commit you're about to make
    specloop check --trailers RANGE  also fail on code commits in RANGE without them
    specloop blame FILE:LINE | --test NAME | --rule ID | --commit REV [--json]
                                     trace code back to its rules, spec and harness
    specloop signal add --source S --summary TEXT [--locus FILE:LINE] [--rule ID]
                        [--evidence FILE|-] [--fingerprint F]
    specloop signal triage ID --layer L --kind K --confidence C --reasoning TEXT [--confirm]
    specloop signal confirm|show ID  /  signal resolve ID --status S [--fix TEXT]
    specloop signals [--all] [--rule ID] [--pending] [--by layer|harness]
                                     open signals, or counts of confirmed ones.
                                     A commit with `Fixes-Signal: <id>` closes
                                     one once it's on HEAD (and, for a spec
                                     change, once the code is built)

  Installing and updating (docs/distribution.md):
    specloop --version               the installed version
    specloop init [PATH]             set up a project: shims, hooks, skill stubs,
                                     specloop.json and a starter spec
    specloop skill NAME              a skill's instructions for this version
    specloop version-ok              exit 1, saying so, if this specloop is older
                                     than the project's minVersion
                                     (what the stubs in .claude/skills/ run)

Configuration lives in specloop.json at the project root (found by walking up
from the current directory). Python 3.8+, standard library only.

The spec is either one Markdown file ("spec": "docs/SPEC.md") or a tree of
them ("spec": "docs/spec"): every .md file under that directory, with
README.md at its top as the overview that links to the feature docs.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from specloop import __version__, project

DEFAULTS = {
    "spec": "docs/SPEC.md",
    "ledger": "docs/.spec-implemented",
    # How rule IDs look, and how the spec marks the place an ID is defined.
    "idPattern": r"[A-Z][A-Z0-9]*-\d+",
    "definitionPattern": r"\*\*({id})",
    "tests": {
        "paths": ["tests"],
        "extensions": [".swift", ".py", ".ts", ".tsx", ".js", ".kt", ".go", ".rb"],
        "tagStyles": ["swift-testing", "js", "pytest", "comment"],
        "extraPatterns": [],
    },
    "commands": {"test": ""},
    "sync": {
        "branchPrefix": "spec-sync/",
        "require": [],
        "permissionMode": "auto",
        "staleAfterMinutes": 120,
        # "mine": the hook only starts a sync for spec changes you authored, so
        # everyone who pulls a merged spec PR doesn't build it at once. "all":
        # any spec change that arrives.
        "trigger": "mine",
        # claude or cursor. Each person can pick their own with
        # `git config specloop.harness cursor`, which wins over this.
        "harness": "claude",
    },
    "check": {"allowReused": []},
    # One JSON file per signal (a crash, a QA report, a review comment).
    "signals": "docs/signals",
    "trailers": {
        # Commits that only touch these (globs, matched against the path and
        # its file name) need no Spec-Rules, nor do the spec, ledger and signals.
        "exempt": ["*.md", "LICENSE", ".gitignore"],
        # true: the commit-msg hook refuses code commits without Spec-Rules.
        "hook": False,
    },
    # Confirmed signals of one layer and kind under one Harness-Rev before
    # `specloop signals --by harness` says it's time to change the harness.
    "feedback": {"harnessThreshold": 3},
}

HARNESSES = ("claude", "cursor")
# The overview doc at the top of a spec tree.
TREE_ROOT = "README.md"

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# A session that hasn't reported in this long after the hook launched it
# probably never started.
START_TIMEOUT_MINUTES = 10
SYNC_STATUSES = ["starting", "running", "done", "blocked", "failed"]

TRAILER_KEYS = ("Spec-Rev", "Spec-Rules", "Harness", "Harness-Rev", "Sync", "Fixes-Signal")
# Anywhere in a message, not only its last paragraph: a squash merge joins its
# commits' messages, which leaves their trailers mid-body.
TRAILER = re.compile(r"^(%s):[ \t]*(.*?)\s*$" % "|".join(TRAILER_KEYS), re.MULTILINE)
# `Spec-Rules: none (format)`: commits that move lines without changing what
# they do. Blame looks past them to the commit that wrote the line.
PASS_THROUGH = {"format", "rename", "move"}
# What `Harness:` calls each agent the hook can start.
AGENT_NAMES = {"claude": "claude-code", "cursor": "cursor"}
# The files that tell an agent how to build, by the name Harness-Rev gives them.
HARNESS_FILES = (
    ("spec-sync", ".claude/skills/spec-sync/SKILL.md"),
    ("claude-md", "CLAUDE.md"),
    ("agents-md", "AGENTS.md"),
)
# The triage taxonomy: the layer a signal is blamed on, and its kinds.
LAYERS = {
    "spec": ["wrong", "ambiguous", "missing-rule"],
    "implementation": ["misread", "regression"],
    "verification": ["weak-test", "untested"],
    "harness": ["skill", "context", "model"],
    "outside": ["env", "ops", "dependency"],
}
# Layers a change to the skill or instructions can fix.
HARNESS_FIXABLE = ("implementation", "verification", "harness")
CONFIDENCE = ("low", "medium", "high")
SIGNAL_STATUSES = ("open", "fixed", "wontfix", "duplicate")

# Each style is a regex whose `ids` group holds the text that names spec IDs.
# A test only claims the IDs written before the first colon of its name, so a
# description that happens to mention another ID doesn't count as coverage.
TAG_STYLES = {
    # @Test("XP-6, BREED-1: every tier pays its reward")
    "swift-testing": r'@Test\(\s*"(?P<ids>[^":]*):',
    # it("XP-6: ...") / test("XP-6: ...") / describe("XP-6: ...")
    "js": r'\b(?:it|test|describe)\(\s*[\'"`](?P<ids>[^\'"`:]*):',
    # @pytest.mark.spec("XP-6", "BREED-1")
    "pytest": r"@pytest\.mark\.spec\((?P<ids>[^)]*)\)",
    # // Spec: XP-6, BREED-1   or   # Spec: XP-6   (any language)
    "comment": r"(?://|#)\s*Spec:\s*(?P<ids>.+)$",
}


# MARK: config


def find_root():
    here = Path.cwd().resolve()
    for directory in [here, *here.parents]:
        if (directory / "specloop.json").exists():
            return directory
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, env=GIT_ENV
        ).stdout.strip()
        return Path(top)
    except subprocess.CalledProcessError:
        return here


def merged(base, override):
    out = dict(base)
    for key, value in override.items():
        out[key] = merged(base[key], value) if isinstance(value, dict) and isinstance(base.get(key), dict) else value
    return out


def load_config(root):
    path = root / "specloop.json"
    user = json.loads(path.read_text()) if path.exists() else {}
    return merged(DEFAULTS, user)


# Variables git sets for hooks that would point every git call at the
# checkout the hook fired in. specloop always says where with -C instead.
HOOK_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX")
GIT_ENV = {k: v for k, v in os.environ.items() if k not in HOOK_GIT_VARS}


def git(root, *args, check=True):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=GIT_ENV)
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


# MARK: spec files
#
# Everything below works on a list of (path, text) docs. A single-file spec is
# a list of one; a tree lists its overview first, then the rest by path.


def is_tree(config):
    return not config["spec"].endswith(".md")


def spec_dir(config):
    return config["spec"].rstrip("/")


def spec_root(config):
    """The doc a reader starts from: the file itself, or the tree's overview."""
    return f"{spec_dir(config)}/{TREE_ROOT}" if is_tree(config) else config["spec"]


def spec_pathspec(config):
    """What to hand git to mean "the spec"."""
    return f":(glob){spec_dir(config)}/**/*.md" if is_tree(config) else config["spec"]


def spec_order(config, paths):
    root = spec_root(config)
    return sorted(paths, key=lambda p: (p != root, p))


def spec_docs(root, config, rev=None):
    """(path, text) for every spec doc in the work tree, or at `rev`."""
    if not is_tree(config):
        spec = config["spec"]
        if rev is None:
            path = root / spec
            return [(spec, path.read_text())] if path.exists() else []
        if not succeeds(root, "cat-file", "-e", f"{rev}:{spec}"):
            return []
        return [(spec, git(root, "show", f"{rev}:{spec}"))]
    if rev is None:
        base = root / spec_dir(config)
        paths = [p.relative_to(root).as_posix() for p in base.rglob("*.md") if p.is_file()] if base.exists() else []
    else:
        listed = git(root, "ls-tree", "-r", "--name-only", rev, "--", spec_dir(config), check=False).split("\n")
        paths = [p for p in listed if p.endswith(".md")]
    if rev is None:
        return [(p, (root / p).read_text()) for p in spec_order(config, paths)]
    return [(p, git(root, "show", f"{rev}:{p}", check=False)) for p in spec_order(config, paths)]


def spec_label(config, path, section):
    """A coverage heading: the section, plus which doc it's in for a tree."""
    if not is_tree(config):
        return section
    doc = os.path.relpath(path, spec_dir(config))
    return f"{doc} · {section}" if section else doc


LINK = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def doc_links(config, path, text):
    """(line number, target path) for each link in `path` to another .md file
    or a directory, resolved relative to `path`. Web links and anchors are skipped."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for target in LINK.findall(line):
            target = target.split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("/"):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target)).replace(os.sep, "/")
            if target.endswith("/"):
                resolved = f"{resolved}/{TREE_ROOT}"
            elif not target.endswith(".md"):
                continue
            found.append((number, resolved))
    return found


def tree_findings(config, docs):
    """(level, message, path, line) for broken links and for docs the overview
    can't reach. Only for a tree: that's what makes it one."""
    if not is_tree(config):
        return []
    findings, present, root = [], {p for p, _ in docs}, spec_root(config)
    if root not in present:
        return [("error", f"{root} doesn't exist. A spec tree starts from an overview there that links to the feature docs.", None, None)]
    inside = spec_dir(config) + "/"
    links = {p: doc_links(config, p, t) for p, t in docs}
    for path, found in links.items():
        for number, target in found:
            if target.startswith(inside) and target not in present:
                findings.append(("error", f"Links to {target}, which doesn't exist.", path, number))
    reached, queue = {root}, [root]
    while queue:
        for _, target in links.get(queue.pop(), []):
            if target in present and target not in reached:
                reached.add(target)
                queue.append(target)
    for path in spec_order(config, present - reached):
        findings.append((
            "error",
            f"Nothing links to {path} from {root} or the docs it links to. Link it from its parent so readers can find it.",
            path,
            1,
        ))
    return findings


# MARK: spec + ledger


def definitions(text, config):
    """Ordered (id, line number, section heading) for every ID definition."""
    definition = re.compile(config["definitionPattern"].format(id=config["idPattern"]))
    found, section = [], ""
    for number, line in enumerate(text.splitlines(), 1):
        if heading := re.match(r"^#{1,4} (.+)$", line):
            section = heading.group(1)
        for spec_id in definition.findall(line):
            found.append((spec_id, number, section))
    return found


def spec_ids(root, config):
    """Ordered (id, section label) pairs as defined across the spec."""
    return [
        (i, spec_label(config, path, section))
        for path, text in spec_docs(root, config)
        for i, _, section in definitions(text, config)
    ]


def rule_texts(docs, config):
    """Map of ID -> its rule's text (every line it owns, whitespace-normalized)."""
    texts = defaultdict(list)
    for _, text in docs:
        owner = owning_ids(text, config)
        for number, line in enumerate(text.splitlines(), 1):
            if owner.get(number) and line.strip():
                texts[owner[number]].append(" ".join(line.split()))
    return {i: "\n".join(lines) for i, lines in texts.items()}


def rule_version(text):
    """A rule's version: a short hash of its text. Rewording a rule changes it;
    moving the rule to another doc doesn't."""
    return hashlib.sha1(text.encode()).hexdigest()[:6]


def rule_versions(docs, config):
    return {i: rule_version(t) for i, t in rule_texts(docs, config).items()}


def is_shallow(root):
    return git(root, "rev-parse", "--is-shallow-repository", check=False).strip() == "true"


def commit_exists(root, rev):
    return succeeds(root, "cat-file", "-e", f"{rev}^{{commit}}")


def ledger_rev(root, config):
    ledger = root / config["ledger"]
    return ledger.read_text().strip() if ledger.exists() else ""


def baseline(root, config):
    """The implemented revision: the ledger, else the commit that added the spec."""
    if rev := ledger_rev(root, config):
        return rev
    added = git(root, "log", "--diff-filter=A", "--format=%H", "--", spec_pathspec(config)).split()
    return added[-1] if added else None


def missing_ledger_message(root, config, rev):
    hint = " This is a shallow clone; fetch full history (actions/checkout: fetch-depth: 0)." if is_shallow(root) else (
        " Was the history rewritten, or the spec commit squash-merged? Check that the code matches"
        " the spec, then run `specloop mark` and commit."
    )
    return f"{config['ledger']} names {rev[:12]}, which isn't a commit in this clone.{hint}"


def pending_diff(root, config):
    base = baseline(root, config)
    if base is None:
        return None, ""
    if not commit_exists(root, base):
        sys.exit(missing_ledger_message(root, config, base))
    return base, git(root, "diff", base, "HEAD", "--", spec_pathspec(config))


def owning_ids(text, config):
    """For each line number (1-based), the nearest ID defined at or above it.
    A table row or wrapped sentence belongs to the rule whose ID precedes it."""
    definition = re.compile(config["definitionPattern"].format(id=config["idPattern"]))
    owner, current = {}, None
    for number, line in enumerate(text.splitlines(), 1):
        if re.match(r"^#{1,4} ", line):
            current = None  # a new heading ends the previous rule's reach
        if found := definition.findall(line):
            current = found[0]
        owner[number] = current
    return owner


def changed_ids(root, config, base, head="HEAD"):
    """IDs whose rule text changed between `base` and `head`, in spec order.
    A doc that moved counts as removed and added, so its IDs all show."""
    old_docs, new_docs = dict(spec_docs(root, config, base)), dict(spec_docs(root, config, head))
    id_re = re.compile(config["idPattern"])
    found = []

    def add(spec_id):
        if spec_id and spec_id not in found:
            found.append(spec_id)

    for path in spec_order(config, set(old_docs) | set(new_docs)):
        old_owner = owning_ids(old_docs.get(path, ""), config)
        new_owner = owning_ids(new_docs.get(path, ""), config)
        old_line = new_line = 0
        for line in git(root, "diff", "-U0", "--no-renames", base, head, "--", path).splitlines():
            if hunk := re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line):
                old_line, new_line = int(hunk.group(1)), int(hunk.group(2))
            elif line.startswith("+") and not line.startswith("+++"):
                for spec_id in id_re.findall(line):
                    add(spec_id)
                add(new_owner.get(new_line))
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                for spec_id in id_re.findall(line):
                    add(spec_id)
                add(old_owner.get(old_line))
                old_line += 1
    return found


# MARK: tests


def test_claims(root, config):
    """Map of spec ID -> list of (path, line number, line text)."""
    tests = config["tests"]
    patterns = [re.compile(TAG_STYLES[s], re.MULTILINE) for s in tests["tagStyles"] if s in TAG_STYLES]
    patterns += [re.compile(p, re.MULTILINE) for p in tests["extraPatterns"]]
    id_re = re.compile(config["idPattern"])
    claims = defaultdict(list)
    scanned = 0
    for test_dir in tests["paths"]:
        base = root / test_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in tests["extensions"]:
                continue
            scanned += 1
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                for pattern in patterns:
                    if match := pattern.search(line):
                        where = (str(path.relative_to(root)), number, line.strip()[:80])
                        for spec_id in id_re.findall(match.group("ids")):
                            claims[spec_id].append(where)
                        break
    if scanned == 0:
        # 0% coverage from a wrong path looks just like 0% from no tests.
        print(
            f"warning: no test files found under {tests['paths']} "
            f"(extensions {tests['extensions']}). Check tests.paths in specloop.json.",
            file=sys.stderr,
        )
    return claims


def describe(where):
    path, number, text = where
    return f"{path}:{number}  {text}"


# MARK: sync state
#
# One JSON file per sync under <git common dir>/specloop/syncs/, named after
# the spec revision it implements. It lives in the git dir rather than the
# work tree: it is this clone's view of its syncs, shared by every worktree.


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat(timespec="seconds")


def minutes_since(iso):
    try:
        return (now() - datetime.fromisoformat(iso)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")


def ago(iso):
    minutes = minutes_since(iso)
    if minutes == float("inf"):
        return "at an unknown time"
    if minutes < 1:
        return "just now"
    if minutes < 90:
        return f"{int(minutes)}m ago"
    if minutes < 48 * 60:
        return f"{int(minutes // 60)}h ago"
    return f"{int(minutes // (24 * 60))}d ago"


def in_linked_worktree(root):
    def resolved(flag):
        path = Path(git(root, "rev-parse", flag).strip())
        return (path if path.is_absolute() else root / path).resolve()

    return resolved("--git-dir") != resolved("--git-common-dir")


def state_dir(root):
    common = Path(git(root, "rev-parse", "--git-common-dir").strip())
    return (common if common.is_absolute() else root / common) / "specloop"


def load_syncs(root):
    directory = state_dir(root) / "syncs"
    syncs = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        syncs[record.get("rev", path.stem)] = record
    return syncs


def save_sync(root, record, touch=True):
    directory = state_dir(root) / "syncs"
    directory.mkdir(parents=True, exist_ok=True)
    if touch or "updated" not in record:
        record["updated"] = stamp()
    (directory / f"{record['rev']}.json").write_text(json.dumps(record, indent=2) + "\n")


def remove_sync(root, rev):
    path = state_dir(root) / "syncs" / f"{rev}.json"
    if path.exists():
        path.unlink()


def archive_sync(root, record):
    """Move an implemented sync's record to syncs/done/, out of what `status`
    and the hook read, so its timing survives for measuring the spec route
    (docs/measurement.md)."""
    directory = state_dir(root) / "syncs" / "done"
    directory.mkdir(parents=True, exist_ok=True)
    record["archived"] = stamp()
    (directory / f"{record['rev']}.json").write_text(json.dumps(record, indent=2) + "\n")
    remove_sync(root, record["rev"])


def is_active(record, config):
    """A sync that should stop the hook from starting another: launched or
    running, and not gone quiet for longer than it plausibly could."""
    quiet = minutes_since(record.get("updated"))
    if record.get("status") == "starting":
        return quiet < START_TIMEOUT_MINUTES
    if record.get("status") == "running":
        return quiet < config["sync"]["staleAfterMinutes"]
    return False


def succeeds(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, env=GIT_ENV).returncode == 0


def my_emails(root):
    """The addresses that count as you: user.email, plus any `specloop.email`
    (e.g. the noreply address GitHub puts on your squash merges)."""
    found = git(root, "config", "--get-all", "user.email", check=False).split()
    found += git(root, "config", "--get-all", "specloop.email", check=False).split()
    return {e.lower() for e in found}


def commit_author(root, rev):
    return git(root, "log", "-1", "--format=%ae", rev).strip().lower()


def harness(root, config):
    chosen = git(root, "config", "--get", "specloop.harness", check=False).strip() or config["sync"]["harness"]
    if chosen not in HARNESSES:
        sys.exit(f"specloop: unknown harness {chosen!r}; use one of {', '.join(HARNESSES)}")
    return chosen


def short(root, rev):
    return git(root, "rev-parse", "--short", rev).strip()


def branch_exists(root, branch):
    return bool(branch) and succeeds(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")


def describe_sync(root, config, record, branch):
    """(state, detail) for one recorded sync."""
    status, note = record.get("status"), record.get("note")
    when = ago(record.get("updated"))
    session_id = record.get("sessionId", "")[:8]
    look = f"run `claude logs {session_id}`" if session_id else f"see {record['log']}" if record.get("log") else "check `claude agents`"
    if status == "starting":
        if is_active(record, config):
            return "starting", f"session '{record.get('session', '')}' launched {when}"
        return "failed to start?", f"launched {when} but never reported in; {look}"
    if status == "running":
        if is_active(record, config):
            return "running", f"on {branch}, last update {when}"
        return "stalled?", f"on {branch}, no update since {when}; {look}"
    if status == "done":
        if not branch_exists(root, branch):
            return "branch gone", f"finished {when}, but {branch} no longer exists; rerun /spec-sync"
        if succeeds(root, "merge-base", "--is-ancestor", branch, "HEAD"):
            return "merged", f"{branch} is merged but the ledger wasn't advanced; run specloop mark"
        return "awaiting review", f"on {branch}, finished {when}"
    if status == "blocked":
        if note and note.startswith("specloop ") and " < " in note:
            # Stopped because this machine's specloop is older than the project's minimum.
            reason, _, fix = note.partition(";")
            return f"blocked: {reason}", fix.strip() or "upgrade specloop, then run /spec-sync"
        return "blocked", note or "stopped with questions about the spec"
    return "failed", note or "the sync reported a failure"


def sync_report(root, config, base):
    """(short sha, state, detail) for each spec revision the code doesn't match
    yet, oldest first, plus any live sync of a revision not on this branch."""
    prefix = config["sync"]["branchPrefix"]
    revs = git(root, "log", "--format=%H", f"{base}..HEAD", "--", spec_pathspec(config)).split()
    syncs = load_syncs(root)
    mine = my_emails(root)
    lines, covered_by = [], None
    live = ("starting", "running", "awaiting review")
    # A sync records the commit it started from, which can be a later one that
    # didn't touch the spec. It still builds every pending revision before it.
    later = sorted(
        (r for rev, r in syncs.items() if revs and rev not in revs and commit_exists(root, rev)
         and succeeds(root, "merge-base", "--is-ancestor", revs[0], rev)),
        key=lambda r: r.get("updated", ""), reverse=True,
    )
    for record in later:
        state, detail = describe_sync(root, config, record, record.get("branch") or f"{prefix}{short(root, record['rev'])}")
        if not covered_by and state in live:
            covered_by = short(root, record["rev"])
        lines.append((short(root, record["rev"]), state, f"{detail} (builds {short(root, revs[0])})"))
    # Newest first: a sync implements the whole spec at its revision, so a live
    # one also covers every older pending revision.
    for rev in revs:
        record = syncs.get(rev)
        branch = (record or {}).get("branch") or f"{prefix}{short(root, rev)}"
        if record:
            state, detail = describe_sync(root, config, record, branch)
            if covered_by and state not in live:
                state, detail = "included", f"in the sync of {covered_by}"
        elif branch_exists(root, branch):
            state, detail = "awaiting review", f"on {branch}"
        elif covered_by:
            state, detail = "included", f"in the sync of {covered_by}"
        elif config["sync"]["trigger"] == "mine" and (author := commit_author(root, rev)) not in mine:
            state, detail = "not started", f"by {author}, so the hook left it to them; run /spec-sync to take it"
        else:
            state, detail = "not started", "run /spec-sync"
        if not covered_by and state in live:
            covered_by = short(root, rev)
        lines.append((short(root, rev), state, detail))
    lines.reverse()
    for rev, record in syncs.items():
        if rev not in revs and record not in later and is_active(record, config) and commit_exists(root, rev):
            state, detail = describe_sync(root, config, record, record.get("branch", ""))
            lines.append((short(root, rev), state, f"{detail} (revision not on this branch)"))
    return lines


def reused_ids(root, config, current_docs):
    """(id, commit that removed it, where it came back) for IDs that were
    removed and later defined again with different rule text, anywhere in the spec.
    Moving a rule to another doc isn't a removal."""
    revs = git(root, "log", "--reverse", "--format=%H", "--", spec_pathspec(config)).split()
    snapshots = [(rev[:7], spec_docs(root, config, rev)) for rev in revs]
    snapshots.append(("the working tree", current_docs))
    present, last_text, removed_at, reused = set(), {}, {}, {}
    for where, docs in snapshots:
        ids = {i for _, text in docs for i, _, _ in definitions(text, config)}
        texts = rule_texts(docs, config)
        for spec_id in present - ids:
            removed_at[spec_id] = where
        for spec_id in ids - present:
            if spec_id not in removed_at:
                continue
            if texts.get(spec_id) == last_text.get(spec_id):
                reused.pop(spec_id, None)  # a restore, e.g. a revert
            else:
                reused[spec_id] = (removed_at[spec_id], where)
        for spec_id in ids:
            last_text[spec_id] = texts.get(spec_id)
        present = ids
    return [(spec_id, removed, back) for spec_id, (removed, back) in reused.items() if spec_id in present]


# MARK: attribution
#
# Commits say where they came from in trailers (Spec-Rev, Spec-Rules, Harness,
# Harness-Rev, Sync). Blame follows a line or a test back to them.


def parse_trailers(message):
    """{key: [values]} for every known trailer anywhere in `message`."""
    found = defaultdict(list)
    for key, value in TRAILER.findall(message):
        if value:
            found[key].append(value)
    return found


def parse_rules(values, config):
    """(rules as (id, version or None), reasons given for `none`, items that
    aren't rule IDs) from Spec-Rules values."""
    item = re.compile(r"^(%s)(?:@([0-9a-f]+))?$" % config["idPattern"])
    rules, reasons, bad = [], [], []
    for value in values:
        if none := re.match(r"^none\b\s*(?:\((.*)\))?", value, re.I):
            reasons.append((none.group(1) or "").strip())
            continue
        for part in filter(None, (p.strip() for p in value.split(","))):
            if match := item.match(part):
                if (match.group(1), match.group(2)) not in rules:
                    rules.append((match.group(1), match.group(2)))
            else:
                bad.append(part)
    return rules, reasons, bad


def commit_info(root, config, rev):
    """A commit and what its trailers say about it."""
    full, abbrev, date, subject, body = git(root, "show", "-s", "--format=%H%x00%h%x00%as%x00%s%x00%B", rev).split("\x00", 4)
    found = parse_trailers(body)
    rules, reasons, bad = parse_rules(found.get("Spec-Rules", []), config)
    first = lambda key: found[key][0] if found.get(key) else ""
    return {
        "sha": full, "short": abbrev, "date": date, "subject": subject,
        "has_rules": bool(found.get("Spec-Rules")), "rules": rules, "none": reasons, "bad": bad,
        "spec_rev": first("Spec-Rev"), "harness": first("Harness"),
        "harness_rev": " ".join(found.get("Harness-Rev", [])), "sync": first("Sync"),
    }


def passes_through(info):
    """A commit that only reformats, renames or moves code."""
    return bool(info["none"]) and not info["rules"] and all(r.split(" ")[0].lower() in PASS_THROUGH for r in info["none"])


def blame_line(root, config, path, line, rev="HEAD"):
    """(commit info, commits looked past) for the last commit that changed
    `path`:`line`, skipping commits that only reformat, rename or move code.
    (None, []) when the line doesn't exist."""
    skipped = []
    while True:
        out = git(root, "blame", "-w", "-M", "-C", "--porcelain", "-L", f"{line},{line}", rev, "--", path, check=False)
        if not out:
            return (skipped.pop() if skipped else None), skipped
        lines = out.splitlines()
        sha, origin = lines[0].split()[0], int(lines[0].split()[1])
        origin_path = next((l[len("filename "):] for l in lines if l.startswith("filename ")), path)
        info = commit_info(root, config, sha)
        has_parent = bool(git(root, "rev-parse", "-q", "--verify", f"{sha}^", check=False).strip())
        if not passes_through(info) or not has_parent:
            return info, skipped
        skipped.append(info)
        rev, path, line = f"{sha}^", origin_path, origin


def commits_naming(root, config, spec_id):
    """Commits whose Spec-Rules name `spec_id`, newest first."""
    found = []
    for entry in git(root, "log", "--format=%H%x00%B%x01", "HEAD").split("\x01"):
        sha, _, body = entry.lstrip("\n").partition("\x00")
        if sha and spec_id in {i for i, _ in parse_rules(parse_trailers(body).get("Spec-Rules", []), config)[0]}:
            found.append(sha)
    return found


def resolve_locus(root, path):
    """`path` as a tracked file relative to the root, from a stack frame that may
    give it absolute or with a build prefix. None if no single file matches."""
    if (root / path).is_file():
        return Path(path).as_posix()
    absolute = Path(path)
    if absolute.is_absolute():
        try:
            return absolute.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    # A build machine's checkout prefix: drop leading parts until one file matches.
    tracked = git(root, "ls-files").splitlines()
    parts = [p for p in Path(path).parts if p not in ("/", ".", "..")]
    for start in range(len(parts)):
        tail = "/".join(parts[start:])
        matches = [t for t in tracked if t == tail or t.endswith("/" + tail)]
        if matches:
            return matches[0] if len(matches) == 1 else None
    return None


LOCUS = re.compile(r"((?:/|\.{0,2}/)?[\w@+.-]+(?:/[\w@+.-]+)*\.[A-Za-z0-9]+):(\d+)")


def loci_in(root, text):
    """`file:line` places in evidence that name a file in this repo."""
    found = []
    for path, line in LOCUS.findall(text):
        resolved = resolve_locus(root, path)
        if resolved and f"{resolved}:{line}" not in found:
            found.append(f"{resolved}:{line}")
    return found


def split_locus(locus):
    path, _, line = locus.rpartition(":")
    if not path or not line.isdigit():
        sys.exit(f"specloop: {locus!r} isn't FILE:LINE")
    return path, int(line)


def trace(root, config, locus=None, test=None, rule=None, commit=None):
    """What a place in the code traces back to: {commits, skipped, rules, tests,
    note}. Rules are (id, version the code was built from, or None)."""
    claims = test_claims(root, config)
    out = {"commits": [], "skipped": [], "rules": [], "tests": [], "note": ""}

    def add_rules(pairs):
        for pair in pairs:
            if pair not in out["rules"]:
                out["rules"].append(pair)

    if locus:
        path, line = split_locus(locus)
        resolved = resolve_locus(root, path)
        info, skipped = blame_line(root, config, resolved, line) if resolved else (None, [])
        if not info:
            out["note"] = f"{locus} isn't a line of a committed file"
            return out
        out["commits"], out["skipped"] = [info], skipped
        add_rules(info["rules"])
    elif test:
        places = sorted({where for found in claims.values() for where in found if test in where[2]})
        if not places:
            out["note"] = f"no tagged test matches {test!r}"
            return out
        out["tests"] = [list(where) for where in places]
        add_rules([(i, None) for i, found in claims.items() for where in found if where in places])
        for path, number, _ in places:
            info, skipped = blame_line(root, config, path, number)
            if info and info["sha"] not in {c["sha"] for c in out["commits"]}:
                out["commits"].append(info)
                out["skipped"] += skipped
        return out
    elif rule:
        out["commits"] = [commit_info(root, config, sha) for sha in commits_naming(root, config, rule)]
        add_rules([(rule, None)])
        if not out["commits"]:
            out["note"] = f"no commit's Spec-Rules names {rule}"
    else:
        info = commit_info(root, config, commit)
        out["commits"] = [info]
        add_rules(info["rules"])
    ids = {i for i, _ in out["rules"]}
    out["tests"] = [list(where) for i in sorted(ids) for where in claims.get(i, [])]
    return out


def harness_revs(root):
    """Harness-Rev: a short content hash of each instruction file present."""
    return " ".join(
        f"{name}@{git(root, 'hash-object', path).strip()[:6]}" for name, path in HARNESS_FILES if (root / path).is_file()
    )


def needs_trailers(config, files):
    """Whether a commit touching `files` changes code, so must name its rules."""
    own = [spec_dir(config) + "/" if is_tree(config) else config["spec"], config["ledger"], config["signals"].rstrip("/") + "/"]
    exempt = config["trailers"]["exempt"]
    for path in filter(None, files):
        if any(path == o or (o.endswith("/") and path.startswith(o)) for o in own):
            continue
        if any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(os.path.basename(path), g) for g in exempt):
            continue
        return True
    return False


def message_findings(info, defined, where):
    """(level, message) for what's wrong with one commit's Spec-Rules."""
    if not info["has_rules"]:
        return [(
            "error",
            f"{where} changes code without a Spec-Rules trailer. Name the rules it implements "
            f"(`tools/specloop trailers` prints them), or say `Spec-Rules: none (reason)`.",
        )]
    found = []
    if any(not reason for reason in info["none"]):
        found.append(("error", f"{where} says `Spec-Rules: none` without a reason in brackets, e.g. `none (deps)`."))
    for item in info["bad"]:
        found.append(("error", f"{where} has {item!r} in Spec-Rules, which isn't a rule ID."))
    for spec_id, _ in info["rules"]:
        if spec_id not in defined:
            found.append(("error", f"{where} names {spec_id} in Spec-Rules, which the spec there doesn't define."))
    return found


def trailer_findings(root, config, span):
    """(level, message, path, line) for each code commit in `span` whose
    trailers are missing or wrong."""
    findings = []
    for sha in git(root, "rev-list", "--no-merges", "--reverse", span).split():
        files = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).split("\n")
        if not needs_trailers(config, files):
            continue
        info = commit_info(root, config, sha)
        defined = {i for _, text in spec_docs(root, config, sha) for i, _, _ in definitions(text, config)}
        for level, message in message_findings(info, defined, f"{info['short']} ({info['subject'][:60]})"):
            findings.append((level, message, None, None))
    return findings


# MARK: signals
#
# One JSON file per signal under `signals` (default docs/signals/), in the
# repo, so everyone sees them and their resolution is reviewed like code.


def signals_dir(root, config):
    return root / config["signals"]


def main_worktree(root):
    """The clone's main work tree, which a sync's worktree hangs off."""
    first = git(root, "worktree", "list", "--porcelain").split("\n", 1)[0]
    return Path(first[len("worktree "):]) if first.startswith("worktree ") else root


def load_signals(root, config):
    """Every signal here, plus any in the main work tree this worktree's branch
    doesn't have yet (one recorded there, not committed). Each remembers its
    file in `_path`."""
    found = {}
    for base in dict.fromkeys([root, main_worktree(root)]):
        directory = signals_dir(base, config)
        for path in sorted(directory.glob("*.json")) if directory.exists() else []:
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                print(f"warning: couldn't read {path}", file=sys.stderr)
                continue
            record["_path"] = str(path)
            found.setdefault(record["id"], record)
    return list(found.values())


def save_signal(root, config, record):
    path = Path(record["_path"]) if record.get("_path") else signals_dir(root, config) / f"{record['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in record.items() if not k.startswith("_")}, indent=2) + "\n")
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def fixing_commits(root):
    """{signal id: sha} for each signal a commit on HEAD names in Fixes-Signal."""
    found = {}
    for entry in git(root, "log", "--format=%H%x00%B%x01", "HEAD").split("\x01"):
        sha, _, body = entry.lstrip("\n").partition("\x00")
        for value in parse_trailers(body).get("Fixes-Signal", []):
            for sid in re.split(r"[,\s]+", value):
                if sid:
                    found[sid] = sha  # oldest wins: the log is newest first
    return found


def with_status(root, config, records):
    """Fill in each record's `_status` and `_fix`: what's stored, unless it's
    open and a commit on HEAD fixes it. A fix that changed the spec counts
    once the code is built, so it's `fix pending sync` until the ledger has it."""
    fixes = fixing_commits(root)
    base = baseline(root, config)
    base_ok = bool(base) and commit_exists(root, base)
    for record in records:
        stored = record["resolution"]
        record["_status"], record["_fix"] = stored["status"], stored.get("fix")
        sha = fixes.get(record["id"])
        if stored["status"] != "open" or not sha:
            continue
        changes_spec = bool(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha, "--", spec_pathspec(config)).strip())
        built = not changes_spec or (base_ok and succeeds(root, "merge-base", "--is-ancestor", sha, base))
        record["_status"], record["_fix"] = ("fixed" if built else "fix pending sync"), short(root, sha)
    return records


def is_open(record):
    return record.get("_status", record["resolution"]["status"]) in ("open", "fix pending sync")


def sync_rule_ids(root, config):
    """The rules the sync on this branch builds, else the pending ones."""
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    record = next(
        (r for r in load_syncs(root).values() if r.get("branch") == branch and r.get("status") in ("running", "done")), None
    )
    if record:
        return record, changed_ids(root, config, record.get("base") or baseline(root, config), record["rev"])
    base, diff = pending_diff(root, config)
    return None, (changed_ids(root, config, base) if diff.strip() else [])


def on_rules(record, ids):
    return any(r.split("@")[0] in ids for r in record["attribution"]["rules"])


def new_signal(root, config, source, summary, evidence, loci, rules, fingerprint=None, attribution=None):
    """Record a signal, or add it to the open one with the same fingerprint.
    Returns (record, path or None, whether it was a repeat)."""
    fingerprint = fingerprint or f"{source}:{(loci or rules or [summary.lower()])[0]}"
    for record in with_status(root, config, load_signals(root, config)):
        if record["fingerprint"] == fingerprint and is_open(record):
            record.setdefault("duplicates", []).append({"received": stamp(), "summary": summary, "evidence": evidence[:20]})
            return record, save_signal(root, config, record), True
    received = stamp()
    digest = hashlib.sha1(f"{fingerprint}\0{received}\0{time.time_ns()}".encode()).hexdigest()[:6]
    record = {
        "id": f"sig-{now():%Y%m%d}-{digest}",
        "fingerprint": fingerprint,
        "source": source,
        "received": received,
        "summary": summary,
        "evidence": evidence,
        "locus": loci,
        "attribution": attribution or attribute(root, config, loci, rules),
        "triage": None,
        "resolution": {"status": "open", "fix": None},
        "duplicates": [],
    }
    return record, save_signal(root, config, record), False


def read_evidence(source):
    if not source:
        return []
    text = sys.stdin.read() if source == "-" else Path(source).read_text(errors="replace")
    return [l.rstrip() for l in text.splitlines() if l.strip()][:200]


def find_signal(root, config, wanted):
    matches = [s for s in load_signals(root, config) if s["id"] == wanted] or [
        s for s in load_signals(root, config) if s["id"].startswith(wanted)
    ]
    if len(matches) != 1:
        sys.exit(f"specloop: {'no' if not matches else 'more than one'} signal matches {wanted!r}")
    return matches[0]


def attribute(root, config, loci, rule_ids):
    """A signal's attribution, from blame of each place and the rules named."""
    versions = rule_versions(spec_docs(root, config), config)
    found = {"rules": [], "commits": [], "harness": "", "harness_rev": "", "traced_by": "none"}

    def take(info):
        if info["sha"][:12] not in found["commits"]:
            found["commits"].append(info["sha"][:12])
        for spec_id, version in info["rules"]:
            label = f"{spec_id}@{version}" if version else spec_id
            if label not in found["rules"]:
                found["rules"].append(label)
        if info["harness"] and not found["harness"]:
            found["harness"], found["harness_rev"] = info["harness"], info["harness_rev"]

    for locus in loci:
        for info in trace(root, config, locus=locus)["commits"]:
            take(info)
    for spec_id in rule_ids:
        if not any(r.split("@")[0] == spec_id for r in found["rules"]):
            found["rules"].append(f"{spec_id}@{versions[spec_id]}" if spec_id in versions else spec_id)
        if latest := commits_naming(root, config, spec_id)[:1]:
            take(commit_info(root, config, latest[0]))
    if found["commits"]:
        found["traced_by"] = "specloop blame"
    return found


def signal_line(record):
    triage = record.get("triage") or {}
    if triage:
        label = f"{triage['layer']}/{triage['kind']}" + (" ✓" if triage.get("confirmed_by") else " ?")
    else:
        label = "untriaged"
    extra = f"  (+{len(record['duplicates'])})" if record.get("duplicates") else ""
    state, fix = record.get("_status", record["resolution"]["status"]), record.get("_fix")
    status = "" if state == "open" else f" [{state}{' ' + fix if fix else ''}]"
    return f"  {record['id']}  {record['source']:<9} {label:<28} {record['summary'][:70]}{extra}{status}"


def confirmed(record):
    return bool((record.get("triage") or {}).get("confirmed_by"))


def sync_counts(root, config):
    """{(harness, harness_rev): number of syncs} from commit trailers."""
    syncs = defaultdict(set)
    for entry in git(root, "log", "--format=%H%x00%B%x01", "HEAD").split("\x01"):
        _, _, body = entry.lstrip("\n").partition("\x00")
        found = parse_trailers(body)
        if found.get("Sync"):
            syncs[(found["Harness"][0] if found.get("Harness") else "", " ".join(found.get("Harness-Rev", [])))].add(found["Sync"][0])
    return {key: len(revs) for key, revs in syncs.items()}


# MARK: worktrees
#
# With Claude Code, the hook makes .claude/worktrees/spec-sync-<sha> at HEAD
# and starts `claude --bg` inside it. Nothing locks it, so a dead session is
# found by the sync going quiet. (`claude --worktree` would cut the worktree
# from the remote's default branch instead.) With Cursor, the hook makes
# .specloop/worktrees/spec-sync-<sha> itself and locks it the same way.
# Cleanup only ever touches worktrees with that name.

WORKTREE_NAME = re.compile(r"^spec-sync-([0-9a-f]{4,40})$")


def worktrees(root):
    """Linked worktrees: dicts with path, branch and locked (reason or None)."""
    found, current = [], None
    for line in git(root, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line.startswith("worktree "):
            current = {"path": Path(line[len("worktree "):]), "branch": "", "locked": None}
        elif current is None:
            continue
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].replace("refs/heads/", "", 1)
        elif line == "locked" or line.startswith("locked "):
            current["locked"] = line[len("locked "):]
        elif not line:
            found.append(current)
            current = None
    return found[1:]  # the first entry is always the main worktree


def process_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_state(tree):
    """'unlocked', 'live' or 'dead' for a Claude Code session lock, or
    'foreign' for a lock someone else put there."""
    if tree["locked"] is None:
        return "unlocked", None
    match = re.search(r"\bpid (\d+)", tree["locked"])
    if not match:
        return "foreign", None
    pid = int(match.group(1))
    return ("live" if process_alive(pid) else "dead"), pid


def cleanup_candidates(root, config):
    """(worktree, record, rev, why) for each hook-made worktree that can go:
    the code now matches its revision, or its session ended without finishing."""
    syncs = load_syncs(root)
    base = baseline(root, config)
    base_ok = bool(base) and commit_exists(root, base)
    found = []
    for tree in worktrees(root):
        match = WORKTREE_NAME.match(tree["path"].name)
        if not match:
            continue
        record = next((r for r in syncs.values() if r["rev"].startswith(match.group(1))), None)
        rev = record["rev"] if record else git(root, "rev-parse", "-q", "--verify", f"{match.group(1)}^{{commit}}", check=False).strip()
        status = (record or {}).get("status")
        lock, _ = lock_state(tree)
        if rev and base_ok and succeeds(root, "merge-base", "--is-ancestor", rev, base):
            why = "implemented"
        elif status == "failed" or (status in ("starting", "running") and (lock == "dead" or not is_active(record, config))):
            why = "ended without finishing"
        else:
            continue
        found.append((tree, record, rev, why))
    return found


def remove_sync_worktree(root, config, tree, record, rev, why, dry_run):
    """Remove one worktree and, when nothing would be lost, its branch.
    Returns (removed, message)."""
    path = tree["path"]
    where = os.path.relpath(path, root)
    lock, pid = lock_state(tree)
    session_id = (record or {}).get("sessionId", "")
    # The hook started a cursor agent itself, so it's ours to stop by pid.
    # A Claude Code session is stopped through claude.
    by_cursor = (record or {}).get("harness") == "cursor"
    with_claude = bool(session_id) and shutil.which("claude")
    if lock == "foreign":
        return False, f"kept {where}: locked ({tree['locked']})"
    if lock == "live":
        if (record or {}).get("status") in ("starting", "running"):
            return False, f"kept {where}: its session is still running"
        if not by_cursor and not with_claude:
            return False, f"kept {where}: a live session (pid {pid}) holds it; stop it from `claude agents`"
    if git(root, "-C", str(path), "status", "--porcelain", check=False).strip():
        return False, f"kept {where}: it has uncommitted changes"
    if dry_run:
        return True, f"would remove {where} ({why})"

    if lock == "unlocked" and with_claude and not by_cursor:
        # The hook made this worktree, so nothing holds a lock on it; ask
        # Claude Code to stop the session that ran in it.
        subprocess.run(["claude", "stop", session_id], capture_output=True)
    if lock == "live":
        if by_cursor:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            subprocess.run(["claude", "stop", session_id], capture_output=True)
        for _ in range(20):
            if not process_alive(pid):
                break
            time.sleep(0.5)
        else:
            return False, f"kept {where}: session {session_id} didn't stop"
    if tree["locked"] is not None:
        git(root, "worktree", "unlock", str(path), check=False)
    removal = subprocess.run(
        ["git", "-C", str(root), "worktree", "remove", str(path)], capture_output=True, text=True, env=GIT_ENV
    )
    if removal.returncode != 0:
        return False, f"couldn't remove {where}: {removal.stderr.strip()}"

    branch, note, tip, merged = tree["branch"], "", "", False
    if branch:
        tip = git(root, "rev-parse", "-q", "--verify", f"{branch}^{{commit}}", check=False).strip()
        merged = succeeds(root, "merge-base", "--is-ancestor", branch, "HEAD")
        own_commits = git(root, "rev-list", f"{rev}..{branch}", check=False).strip() if rev else "unknown"
        if merged or not own_commits:
            git(root, "branch", "-D", branch, check=False)
            note = f"; deleted {branch}"
        else:
            note = f"; kept {branch}, which has unmerged commits"
    if with_claude and not by_cursor:
        subprocess.run(["claude", "rm", session_id], capture_output=True)  # its entry in `claude agents`
    if record:
        if why == "implemented":
            # A branch tip past the sync's own last commit means someone added
            # commits before merging. A squash merge reads as not merged.
            record["branchTip"], record["branchMerged"] = tip, merged
            record["ledger"] = baseline(root, config)
            archive_sync(root, record)
        elif record.get("status") != "failed":
            record["status"] = "failed"
            record["note"] = "the session ended without reporting; its worktree was cleaned up"
            save_sync(root, record)
    return True, f"removed {where} ({why}{note})"


# MARK: commands


def cmd_config(root, config, args):
    value = config
    for part in (args.key.split(".") if args.key else []):
        value = value[part]
    print(value if isinstance(value, str) else json.dumps(value, indent=2))
    return 0


def cmd_pending(root, config, args):
    base, diff = pending_diff(root, config)
    if base is None:
        print(f"{config['spec']} is not committed yet.")
        return 0
    if not diff.strip():
        print(f"Nothing pending: code matches the spec ({config['spec']}) at {base[:7]}.")
        return 0
    if args.ids:
        print("\n".join(changed_ids(root, config, base)) or "(changed lines sit outside any rule)")
    else:
        print(f"Spec changes since {base[:7]}:\n")
        print(diff)
    return 0


def cmd_coverage(root, config, args):
    ids = spec_ids(root, config)
    defined = {i for i, _ in ids}
    claims = test_claims(root, config)
    only = {i.strip() for i in args.ids.split(",")} if args.ids else None

    section = None
    for spec_id, heading in ids:
        covering = claims.get(spec_id, [])
        if (args.uncovered and covering) or (only and spec_id not in only):
            continue
        if heading != section:
            print(f"\n{heading}")
            section = heading
        print(f"  {'✓' if covering else '✗'} {spec_id}" + (f"  ({len(covering)})" if covering else ""))

    covered = sum(1 for i in defined if claims.get(i))
    print(f"\n{covered}/{len(defined)} spec IDs have at least one test.")

    failed = False
    unknown = sorted(set(claims) - defined)
    if unknown:
        failed = True
        print("\nTests name IDs the spec doesn't define (stale tags):")
        for spec_id in unknown:
            for where in claims[spec_id]:
                print(f"  {spec_id}  ← {describe(where)}")

    prefixes = [p.strip() for p in (args.require or ",".join(config["sync"]["require"])).split(",") if p.strip()]
    if prefixes:
        missing = [i for i, _ in ids if i.split("-")[0] in prefixes and not claims.get(i)]
        if missing:
            failed = True
            print(f"\nRequired but uncovered: {', '.join(missing)}")
    if only:
        missing = sorted(i for i in only if i in defined and not claims.get(i))
        if missing:
            failed = True
            print(f"\nNamed but uncovered: {', '.join(missing)}")
    return 1 if failed else 0


def cmd_mark(root, config, args):
    if git(root, "status", "--porcelain", "--", spec_pathspec(config)).strip():
        sys.exit(f"The spec ({config['spec']}) has uncommitted changes; commit them first.")
    sha = git(root, "rev-parse", args.rev).strip()
    ledger = root / config["ledger"]
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(sha + "\n")
    print(f"Recorded {sha[:7]} as the implemented spec in {config['ledger']}. Commit it.")
    return 0


def cmd_sync(root, config, args):
    syncs = load_syncs(root)
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    record = None
    if args.status not in ("starting", "running") and not args.rev:
        # A finishing sync is on its branch, past the revision it implements.
        record = next((r for r in syncs.values() if r.get("branch") == branch and r.get("status") == "running"), None)
    if record is None:
        rev = git(root, "rev-parse", args.rev or "HEAD").strip()
        record = syncs.get(rev)
        if record is None and not args.rev and args.status in ("done", "blocked", "failed"):
            # A session that stops before `sync running`, say because it found
            # nothing to build, reports on the launch that started it.
            launches = [r for r in syncs.values() if r.get("status") == "starting"]
            record = max(launches, key=lambda r: r.get("updated", ""), default=None)
        if record is None and not args.status:
            sys.exit(f"No sync recorded for {rev[:7]}; give a status to start one.")
        record = record or {"rev": rev, "started": stamp()}
    if not args.status:
        for key, field in (("note", "note"), ("session", "session"), ("session_id", "sessionId"), ("log", "log"), ("harness", "harness")):
            if getattr(args, key):
                record[field] = getattr(args, key)
        save_sync(root, record, touch=False)  # a field update isn't news from the session
        return 0
    if args.status == "running":
        record["branch"] = branch
        # Where the sync started from, so `trailers` can name the rules it
        # built after `mark` has moved the ledger.
        record.setdefault("base", baseline(root, config))
        # The hook recorded the revision it launched from. If the session
        # started from a later one, that launch record is now this sync.
        for other, old in syncs.items():
            if other != record["rev"] and old.get("status") == "starting" and succeeds(root, "merge-base", "--is-ancestor", other, record["rev"]):
                remove_sync(root, other)
    if args.status in ("done", "blocked", "failed"):
        record["finished"] = stamp()
        if args.status == "done":
            record["built"] = git(root, "rev-parse", "HEAD").strip()
    else:
        record.pop("finished", None)  # a new attempt at a revision that failed before
    record["status"] = args.status
    record["note"] = args.note or ""
    for key, field in (("session", "session"), ("session_id", "sessionId"), ("log", "log"), ("harness", "harness")):
        if getattr(args, key):
            record[field] = getattr(args, key)
    save_sync(root, record)
    print(f"specloop: sync of {record['rev'][:7]} is {args.status}")
    if args.signal:
        if args.status not in ("blocked", "failed"):
            sys.exit("specloop: --signal is for a sync that's blocked or failed")
        record_sync_signal(root, config, record, args)
    return 0


def record_sync_signal(root, config, record, args):
    """A sync that stopped is a signal about the rules it was building: blocked
    on a question usually means the spec is ambiguous, failed means the code or
    the tests wouldn't come right. Written to the main work tree, because a
    stopped sync's worktree is cleaned up."""
    ids = changed_ids(root, config, record.get("base") or baseline(root, config), record["rev"])
    versions = rule_versions(spec_docs(root, config), config)
    agent = AGENT_NAMES[record.get("harness") or harness(root, config)]
    attribution = {
        "rules": [f"{i}@{versions[i]}" if i in versions else i for i in ids],
        "commits": [],
        "harness": f"{agent} {args.model}" if args.model else agent,
        "harness_rev": harness_revs(root),
        "traced_by": f"sync {short(root, record['rev'])}",
    }
    summary = f"Sync of {short(root, record['rev'])} {args.status}: {args.note or 'no reason given'}"
    target = main_worktree(root)
    signal, path, repeat = new_signal(
        target, config, "sync", summary, read_evidence(args.evidence), [], ids,
        fingerprint=f"sync:{short(root, record['rev'])}:{args.status}", attribution=attribution,
    )
    if not repeat and args.status == "blocked":
        # A guess for triage to check, not a finding: nobody has confirmed it.
        signal["triage"] = {
            "layer": "spec", "kind": "ambiguous", "confidence": "low",
            "reasoning": f"The sync stopped to ask: {args.note or '(no question recorded)'}", "confirmed_by": None,
        }
        save_signal(target, config, signal)
    word = "added to open signal" if repeat else "recorded signal"
    print(f"specloop: {word} {signal['id']} in {path}; commit it from {target}")


def cmd_trigger(root, config, args):
    since = args.since or git(root, "rev-parse", "--verify", "-q", "HEAD^1", check=False).strip() or EMPTY_TREE
    if not git(root, "diff", "--name-only", since, "HEAD", "--", spec_pathspec(config), check=False).strip():
        return 1
    if in_linked_worktree(root):
        # A sync's worktree, or a session's, that merged in a spec change to
        # work on it. Syncs start from the main work tree, where the change
        # arrives for real; starting one here builds it a second time.
        print("specloop: this is a linked worktree, so the hook won't start a sync here. Syncs start from the main work tree.")
        return 1
    base, diff = pending_diff(root, config)
    if not diff.strip():
        print(f"specloop: the spec changes here are already implemented (ledger at {base[:7]}).")
        return 1
    active = [r for r in load_syncs(root).values() if is_active(r, config)]
    if active:
        latest = max(active, key=lambda r: r.get("updated", ""))
        print(
            f"specloop: a sync of {latest['rev'][:7]} is already {latest['status']}; not starting another. "
            f"After its branch is merged, run /spec-sync to pick up {short(root, 'HEAD')}."
        )
        return 1
    if config["sync"]["trigger"] == "mine":
        # Everyone who pulls a merged spec PR gets the same change. Only its
        # author's machine builds it, so two people don't build it at once.
        span = "HEAD" if since == EMPTY_TREE else f"{since}..HEAD"
        authors = git(root, "log", "--no-merges", "--format=%ae", span, "--", spec_pathspec(config)).lower().split()
        if authors and not set(authors) & my_emails(root):
            print(
                f"specloop: the spec changes here are by {', '.join(sorted(set(authors)))}, so their sync is "
                f"theirs to start. To take it yourself, run /spec-sync. If one of those addresses is you, "
                f"`git config --add specloop.email <address>`."
            )
            return 1
    return 0


def cmd_harness(root, config, args):
    print(harness(root, config))
    return 0


def cmd_cleanup(root, config, args):
    for tree, record, rev, why in cleanup_candidates(root, config):
        removed, message = remove_sync_worktree(root, config, tree, record, rev, why, args.dry_run)
        if removed or not args.quiet or message.startswith("couldn't"):
            print(f"specloop: {message}")
    return 0


def cmd_trailers(root, config, args):
    if args.verify:
        return verify_message(root, config, args.verify)
    record, pending = sync_rule_ids(root, config)
    versions = rule_versions(spec_docs(root, config), config)
    spec_rev = (record or {}).get("rev") or ""
    fixes = [i for i in re.split(r"[,\s]+", args.fixes or "") if i]
    if fixes:
        known = {r["id"] for r in load_signals(root, config)}
        if unknown := [i for i in fixes if i not in known]:
            sys.exit(f"specloop: no signal {', '.join(unknown)} (tools/specloop signals --all lists them)")
    if args.none:
        rules = f"none ({args.none})"
    else:
        if args.rules:
            ids = [i.strip() for i in args.rules.split(",") if i.strip()]
            unknown = [i for i in ids if i not in versions]
            if unknown:
                sys.exit(f"specloop: the spec doesn't define {', '.join(unknown)}")
        else:
            ids = pending
            if not record and ids:
                spec_rev = git(root, "rev-parse", "HEAD").strip()
            if not ids:
                sys.exit(
                    "specloop: no sync on this branch and no pending rules to name. Say which rules this commit "
                    "implements with --rules ID,..., or why none apply with --none REASON (e.g. deps, format)."
                )
        rules = ", ".join(f"{i}@{versions[i]}" if i in versions else i for i in ids)
    spec_rev = spec_rev or ledger_rev(root, config) or baseline(root, config) or ""
    lines = [f"Spec-Rev: {spec_rev[:12]}"] if spec_rev else []
    lines.append(f"Spec-Rules: {rules}")
    if args.human:
        lines.append("Harness: human")
    else:
        agent = AGENT_NAMES[(record or {}).get("harness") or harness(root, config)]
        lines.append(f"Harness: {agent} {args.model}" if args.model else f"Harness: {agent}")
        if revs := harness_revs(root):
            lines.append(f"Harness-Rev: {revs}")
    if record:
        lines.append(f"Sync: {short(root, record['rev'])}")
    if fixes:
        lines.append(f"Fixes-Signal: {', '.join(fixes)}")
    print("\n".join(lines))
    return 0


def verify_message(root, config, path):
    """The commit-msg hook: refuse a code commit whose message names no rules."""
    if not config["trailers"]["hook"]:
        return 0
    git_dir = Path(git(root, "rev-parse", "--git-dir").strip())
    if (git_dir if git_dir.is_absolute() else root / git_dir).joinpath("MERGE_HEAD").exists():
        return 0  # a merge brings in commits that were checked on their own
    # The index being committed: a hook's GIT_INDEX_FILE, which GIT_ENV drops.
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split("\n")
    if not needs_trailers(config, staged):
        return 0
    message = "\n".join(l for l in Path(path).read_text().splitlines() if not l.startswith("#"))
    found = parse_trailers(message)
    rules, reasons, bad = parse_rules(found.get("Spec-Rules", []), config)
    info = {"has_rules": bool(found.get("Spec-Rules")), "rules": rules, "none": reasons, "bad": bad}
    defined = {i for _, text in spec_docs(root, config) for i, _, _ in definitions(text, config)}
    problems = message_findings(info, defined, "This commit")
    for _, text in problems:
        print(f"specloop: {text}", file=sys.stderr)
    if problems:
        print("specloop: to commit anyway, use git commit --no-verify.", file=sys.stderr)
    return 1 if problems else 0


def describe_rule(spec_id, version, versions):
    current = versions.get(spec_id)
    if current is None:
        return f"{spec_id}@{version} (no longer in the spec)" if version else f"{spec_id} (no longer in the spec)"
    if not version:
        return f"{spec_id} (current: {current})"
    return f"{spec_id}@{version} (current: {current}, {'unchanged' if version == current else 'changed since'})"


def cmd_blame(root, config, args):
    chosen = [x for x in (args.locus, args.test, args.rule, args.commit) if x]
    if len(chosen) != 1:
        sys.exit("specloop: give one of FILE:LINE, --test NAME, --rule ID or --commit REV")
    found = trace(root, config, locus=args.locus, test=args.test, rule=args.rule, commit=args.commit)
    if args.json:
        print(json.dumps(found, indent=2))
        return 0 if found["commits"] or found["tests"] else 1
    versions = rule_versions(spec_docs(root, config), config)
    print(args.locus or (f"test {args.test!r}" if args.test else args.rule or args.commit))
    if found["note"]:
        print(f"  {found['note']}")
    for info in found["commits"]:
        print(f"  {info['short']}  {info['date']}  {info['subject']}")
        if not info["has_rules"]:
            print("    spec     no trailers: this commit doesn't say which rules it implements")
        elif info["none"] and not info["rules"]:
            print(f"    spec     none ({', '.join(info['none'])})")
        else:
            rules = ", ".join(describe_rule(i, v, versions) for i, v in info["rules"])
            print(f"    spec     {info['spec_rev'][:7] or '?':<8} {rules}")
        if info["harness"]:
            print(f"    harness  {info['harness']}" + (f"  {info['harness_rev']}" if info["harness_rev"] else ""))
        if info["sync"]:
            print(f"    sync     {info['sync']}")
    if args.test and found["rules"]:
        print(f"  rules    {', '.join(describe_rule(i, v, versions) for i, v in found['rules'])}")
    for path, number, text in found["tests"]:
        print(f"  test     {path}:{number}  {text}")
    for info in found["skipped"]:
        print(f"  (looked past {info['short']}, {', '.join(info['none'])}: {info['subject'][:60]})")
    return 0 if found["commits"] or found["tests"] else 1


def cmd_signal(root, config, args):
    if args.action == "add":
        evidence = read_evidence(args.evidence)
        loci = list(dict.fromkeys(
            [f"{resolve_locus(root, p) or p}:{n}" for p, n in map(split_locus, args.locus or [])] + loci_in(root, "\n".join(evidence))[:5]
        ))
        record, path, repeat = new_signal(root, config, args.source, args.summary, evidence, loci, args.rule or [], args.fingerprint)
        if repeat:
            print(f"specloop: same as open signal {record['id']} ({len(record['duplicates'])} repeats); added to it")
            return 0
        found = record["attribution"]
        print(f"specloop: recorded {record['id']} in {path}")
        print(f"  rules    {', '.join(found['rules']) or 'none traced'}")
        print(f"  commits  {', '.join(c[:7] for c in found['commits']) or 'none traced'}")
        if found["harness"]:
            print(f"  harness  {found['harness']}" + (f"  {found['harness_rev']}" if found["harness_rev"] else ""))
        return 0

    record = find_signal(root, config, args.id)
    if args.action == "show":
        with_status(root, config, [record])
        shown = {k: v for k, v in record.items() if not k.startswith("_")}
        if record["_status"] != record["resolution"]["status"]:
            shown["resolution"] = {"status": record["_status"], "fix": record["_fix"], "by": "Fixes-Signal trailer"}
        print(json.dumps(shown, indent=2))
        return 0
    if args.action == "triage":
        if args.kind not in LAYERS[args.layer]:
            sys.exit(f"specloop: a {args.layer} signal's kind is one of {', '.join(LAYERS[args.layer])}")
        record["triage"] = {
            "layer": args.layer, "kind": args.kind, "confidence": args.confidence, "reasoning": args.reasoning,
            "confirmed_by": my_address(root) if args.confirm else None,
        }
        word = "confirmed" if args.confirm else "proposed; confirm with `specloop signal confirm`"
    elif args.action == "confirm":
        if not record.get("triage"):
            sys.exit(f"specloop: {record['id']} has no triage to confirm yet")
        record["triage"]["confirmed_by"] = my_address(root)
        word = "confirmed"
    else:  # resolve
        record["resolution"] = {"status": args.status, "fix": args.fix or record["resolution"].get("fix")}
        word = args.status
    save_signal(root, config, record)
    print(f"specloop: {record['id']} {word}")
    return 0


def my_address(root):
    return git(root, "config", "--get", "user.email", check=False).strip() or "unknown"


def cmd_signals(root, config, args):
    records = sorted(with_status(root, config, load_signals(root, config)), key=lambda r: r["received"], reverse=True)
    if args.rule:
        records = [r for r in records if on_rules(r, {args.rule})]
    if args.pending:
        _, ids = sync_rule_ids(root, config)
        records = [r for r in records if on_rules(r, set(ids)) and is_open(r)]
        if not records:
            print(f"No open signals on {', '.join(ids)}." if ids else "Nothing pending, so no signals on pending rules.")
            return 0
    if not args.by:
        shown = records if args.all or args.rule else [r for r in records if is_open(r)]
        if not shown:
            print("No open signals." if not args.all else "No signals.")
        for record in shown:
            print(signal_line(record))
        return 0
    counted = [r for r in records if confirmed(r)]
    unconfirmed = len(records) - len(counted)
    if args.by == "layer":
        counts = defaultdict(int)
        for record in counted:
            counts[(record["triage"]["layer"], record["triage"]["kind"])] += 1
        for layer, kinds in LAYERS.items():
            total = sum(counts[(layer, k)] for k in kinds)
            if total:
                print(f"{layer:<15} {total:>3}   " + ", ".join(f"{k} {counts[(layer, k)]}" for k in kinds if counts[(layer, k)]))
        if not counted:
            print("No confirmed signals yet.")
    else:
        syncs = sync_counts(root, config)
        groups = defaultdict(list)
        for record in counted:
            if record["triage"]["layer"] != "outside":
                groups[(record["attribution"]["harness"], record["attribution"]["harness_rev"])].append(record)
        keys = sorted(set(syncs) | set(groups), key=lambda k: (k[0], k[1]))
        print(f"{'harness':<30} {'harness rev':<36} {'syncs':>5} {'signals':>7} {'per sync':>8}")
        for key in keys:
            n, found = syncs.get(key, 0), len(groups.get(key, []))
            rate = f"{found / n:.2f}" if n else "-"
            print(f"{key[0] or '(none)':<30} {key[1] or '-':<36} {n:>5} {found:>7} {rate:>8}")
        threshold = config["feedback"]["harnessThreshold"]
        for key, found in groups.items():
            patterns = defaultdict(list)
            for record in found:
                if record["triage"]["layer"] in HARNESS_FIXABLE:
                    patterns[(record["triage"]["layer"], record["triage"]["kind"])].append(record["id"])
            for (layer, kind), ids in patterns.items():
                if len(ids) >= threshold:
                    print(
                        f"\npattern: {len(ids)} confirmed {layer}/{kind} signals under {key[1] or key[0] or 'no harness'}: "
                        f"{', '.join(ids)}. Propose a skill or instruction change that cites them."
                    )
    if unconfirmed:
        print(f"\n({unconfirmed} signal{'s' * (unconfirmed != 1)} without confirmed triage aren't counted)")
    return 0


def cmd_check(root, config, args):
    findings = []

    def add(level, message, path=None, line=None):
        findings.append((level, message, path, line))

    spec = config["spec"]
    docs = spec_docs(root, config)
    if not docs:
        add("error", f"{spec} doesn't exist. Set `spec` in specloop.json.")
        return report(findings, args)
    for finding in tree_findings(config, docs):
        add(*finding)

    first = {}
    for path, text in docs:
        for spec_id, number, _ in definitions(text, config):
            if spec_id in first:
                where = f"line {first[spec_id][1]}" if first[spec_id][0] == path else f"{first[spec_id][0]}:{first[spec_id][1]}"
                add("error", f"{spec_id} is defined more than once (first at {where}).", path, number)
            else:
                first[spec_id] = (path, number)

    if is_shallow(root):
        add("warning", "Shallow clone: skipped the reused-ID check. Fetch full history (actions/checkout: fetch-depth: 0).")
    else:
        allowed = set(config["check"]["allowReused"])
        for spec_id, removed, back in reused_ids(root, config, docs):
            if spec_id not in allowed:
                add(
                    "error",
                    f"{spec_id} was removed in {removed} and defined again in {back} with different text. "
                    f"IDs are permanent: give the new rule a new number, or list {spec_id} under check.allowReused.",
                    *first[spec_id],
                )

    claims = test_claims(root, config)
    for spec_id in sorted(set(claims) - set(first)):
        for path, number, _ in claims[spec_id]:
            add("error", f"Test names {spec_id}, which the spec doesn't define (stale tag).", path, number)

    prefixes = [p.strip() for p in (args.require or ",".join(config["sync"]["require"])).split(",") if p.strip()]
    for spec_id, where in first.items():
        prefix = spec_id.split("-")[0]
        if prefix in prefixes and not claims.get(spec_id):
            add("error", f"{spec_id} has no test, and every {prefix} rule is required to have one.", *where)

    rev = ledger_rev(root, config)
    if rev and not commit_exists(root, rev):
        add("error", missing_ledger_message(root, config, rev), config["ledger"], 1)
    else:
        if not rev:
            add("warning", f"No {config['ledger']} yet; treating the commit that added the spec as implemented.")
        base = baseline(root, config)
        if base and git(root, "diff", base, "HEAD", "--", spec_pathspec(config)).strip():
            ids = changed_ids(root, config, base)
            add(
                "warning" if args.allow_pending else "error",
                f"The spec changed after the implemented revision {base[:7]}"
                + (f" ({', '.join(ids)})" if ids else "")
                + " and the code hasn't caught up. Run /spec-sync, or merge its spec-sync branch.",
                spec_root(config),
            )
    if args.trailers:
        findings += trailer_findings(root, config, args.trailers)
    return report(findings, args)


def report(findings, args):
    errors = sum(1 for level, *_ in findings if level == "error")
    for level, message, path, line in findings:
        if args.format == "github":
            where = ",".join(part for part in (path and f"file={path}", line and f"line={line}") if part)
            print(f"::{level} {where}::{message}" if where else f"::{level}::{message}")
        else:
            where = f"{path}:{line}: " if path and line else f"{path}: " if path else ""
            print(f"{level}: {where}{message}")
    warnings = len(findings) - errors
    print(f"specloop check: {errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}")
    return 1 if errors else 0


def report_changes(changes):
    verbs = {"create": "created", "replace": "replaced", "delete": "removed"}
    for change in changes:
        if change.action == "keep":
            print(f"kept {change.path}: {change.note}")
        else:
            print(f"{verbs[change.action]} {change.path}")
            if change.note:
                print(change.note.rstrip("\n"))


def cmd_init(root, config, args):
    target = Path(args.path).resolve()
    if not succeeds(target, "rev-parse", "--git-dir"):
        print(f"error: {target} is not a git repository", file=sys.stderr)
        return 1
    config = load_config(target)
    changes = project.plan_init(target, config, harness(target, config))
    project.write_files(target, changes)
    report_changes(changes)
    print(f"\nspecloop {__version__} set up in {target}\n")
    print("Next:")
    print("  1. Fill in specloop.json, especially commands.test and tests.paths.")
    print("  2. Run /spec-init in Claude Code or Cursor to draft the spec from the code, or write it yourself.")
    print(f"  3. Enable the trigger:  git -C \"{target}\" config core.hooksPath tools/githooks")
    print(f"     Using Cursor?        git -C \"{target}\" config specloop.harness cursor")
    return 0


def cmd_hook(root, config, args):
    """What the git hooks run. The trigger is a shell script shipped with
    the package; commit-msg checks trailers in-process."""
    first = args.args[0] if args.args else ""
    if args.mode == "commit-msg":
        return verify_message(root, config, first)
    if args.mode == "merge" and first == "1":
        return 0  # a squash merge commits nothing yet; post-commit handles that commit
    if args.mode == "rebase" and first != "rebase":
        return 0  # amends are left to post-commit, which has already run
    return subprocess.run(["sh", str(project.DATA / "specloop-trigger"), args.mode]).returncode


def parse_version(text):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text).strip())
    if not match:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(part) for part in match.groups())


def upgrade_command():
    """How this copy of specloop is upgraded, from where it's installed."""
    here = Path(__file__).resolve()
    if "/Cellar/" in str(here):
        return "brew upgrade specloop"
    if "/pipx/" in str(here):
        return "pipx upgrade specloop"
    return f"git pull in {here.parents[2]}"


def version_gap(config):
    """The warning when this specloop is older than the project's minVersion,
    or None. A minVersion that isn't a version is reported and ignored."""
    wanted = config.get("minVersion")
    if not wanted:
        return None
    try:
        minimum = parse_version(wanted)
    except ValueError:
        print(f'specloop: minVersion "{wanted}" in specloop.json isn\'t a version like 0.3.0; ignoring it', file=sys.stderr)
        return None
    if parse_version(__version__) >= minimum:
        return None
    return f"specloop {__version__} is older than this project's minimum {wanted}; upgrade with {upgrade_command()}"


def cmd_version_ok(root, config, args):
    if args.gap:
        print(args.gap)
        return 1
    return 0


def cmd_skill(root, config, args):
    if args.name not in project.SKILLS:
        print(f"specloop: no skill named {args.name}; there are {', '.join(project.SKILLS)}", file=sys.stderr)
        return 2
    if args.gap and args.name == "spec-sync":
        # People get a warning; an agent doesn't build code from instructions
        # older than the project relies on.
        print(args.gap)
        print("Don't build anything. Record this sync as blocked and stop:\n")
        print(f'    tools/specloop sync blocked --note "specloop {__version__} < {config["minVersion"]}; {upgrade_command()}"')
        return 1
    if args.gap:
        print(args.gap, file=sys.stderr)
    print(f"<!-- specloop {__version__} -->")
    print(project.skill_text(args.name), end="")
    return 0


def cmd_status(root, config, args):
    if args.gap:
        print(args.gap)
    base, diff = pending_diff(root, config)
    claims = test_claims(root, config)
    defined = {i for i, _ in spec_ids(root, config)}
    docs = len(spec_docs(root, config))
    print(f"spec:        {config['spec']}" + (f" ({docs} doc{'s' * (docs != 1)})" if is_tree(config) else ""))
    print(f"implemented: {base[:7] if base else '(spec not committed)'}")
    print(f"pending:     {(', '.join(changed_ids(root, config, base)) or 'changes outside any rule') if diff.strip() else 'nothing'}")
    if diff.strip():
        for sha, state, detail in sync_report(root, config, base):
            print(f"  {sha}  {state:<17}{detail}")
    print(f"coverage:    {sum(1 for i in defined if claims.get(i))}/{len(defined)} IDs")
    stale = sorted(set(claims) - defined)
    if stale:
        print(f"stale tags:  {', '.join(stale)}")
    records = [r for r in with_status(root, config, load_signals(root, config)) if is_open(r)]
    if records:
        untriaged = sum(1 for r in records if not r.get("triage"))
        waiting = sum(1 for r in records if r["_status"] == "fix pending sync")
        ids = set(changed_ids(root, config, base)) if diff.strip() else set()
        on_pending = [r for r in records if on_rules(r, ids)]
        parts = [f"{len(records)} open"]
        parts += [f"{untriaged} untriaged"] if untriaged else []
        parts += [f"{waiting} fixed in the spec, waiting for the sync"] if waiting else []
        parts += [f"{len(on_pending)} on pending rules"] if on_pending else []
        print(f"signals:     {', '.join(parts)} (tools/specloop signals)")
        for record in on_pending:
            print(f"  {record['id']}  {record['summary'][:70]}")
    leftover = cleanup_candidates(root, config)
    if leftover:
        print(f"worktrees:   {len(leftover)} left over from finished or dead syncs (tools/specloop cleanup)")
    return 0


def run():
    parser = argparse.ArgumentParser(prog="specloop", description=__doc__.strip().split("\n")[0])
    parser.add_argument("--version", action="version", version=f"specloop {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p = sub.add_parser("pending")
    p.add_argument("--ids", action="store_true", help="only list IDs on changed lines")
    p = sub.add_parser("coverage")
    p.add_argument("--uncovered", action="store_true")
    p.add_argument("--require", help="comma-separated ID prefixes that must be fully covered")
    p.add_argument("--ids", help="comma-separated IDs to report on (and require)")
    p = sub.add_parser("check")
    p.add_argument("--format", choices=["text", "github"], default="text", help="github: workflow annotations")
    p.add_argument("--allow-pending", action="store_true", help="a spec ahead of the code is a warning, not an error")
    p.add_argument("--require", help="comma-separated ID prefixes that must be fully covered (default: sync.require)")
    p.add_argument("--trailers", metavar="RANGE", help="also check the trailers of code commits in RANGE (e.g. origin/main..HEAD)")
    p = sub.add_parser("mark")
    p.add_argument("rev", nargs="?", default="HEAD")
    p = sub.add_parser("sync")
    p.add_argument("status", nargs="?", choices=SYNC_STATUSES)
    p.add_argument("--rev", help="spec revision the sync implements (default: HEAD, or the running sync on this branch)")
    p.add_argument("--note", help="why it's blocked or failed")
    p.add_argument("--session", help="Claude Code session name")
    p.add_argument("--session-id", help="Claude Code session ID, for `claude logs`")
    p.add_argument("--log", help="where the launch output went")
    p.add_argument("--harness", choices=HARNESSES, help="which coding agent runs the sync")
    p.add_argument("--signal", action="store_true", help="with blocked or failed: also record it as a signal")
    p.add_argument("--evidence", help="with --signal: a file with the failing output or the question")
    p.add_argument("--model", help="with --signal: the model that ran the sync")
    p = sub.add_parser("cleanup")
    p.add_argument("--dry-run", action="store_true", help="say what would be removed")
    p.add_argument("--quiet", action="store_true", help="only report removals")
    p = sub.add_parser("trigger")
    p.add_argument("--since", help="revision before this update (default: HEAD's first parent)")
    sub.add_parser("harness")
    p = sub.add_parser("trailers")
    p.add_argument("--rules", help="comma-separated rule IDs (default: the sync on this branch, or what's pending)")
    p.add_argument("--none", metavar="REASON", help="no rule covers this commit, e.g. deps, format, rename")
    p.add_argument("--model", help="the model building the change, for Harness")
    p.add_argument("--human", action="store_true", help="written by hand: Harness: human")
    p.add_argument("--fixes", metavar="IDS", help="signals this commit fixes (comma-separated): Fixes-Signal")
    p.add_argument("--verify", metavar="MSGFILE", help=argparse.SUPPRESS)  # the commit-msg hook
    p = sub.add_parser("blame")
    p.add_argument("locus", nargs="?", help="FILE:LINE, e.g. from a stack frame")
    p.add_argument("--test", help="a tagged test, by part of its line")
    p.add_argument("--rule", help="every commit that names this rule")
    p.add_argument("--commit", help="one commit's trailers")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("signal")
    actions = p.add_subparsers(dest="action", required=True)
    a = actions.add_parser("add")
    a.add_argument("--source", required=True, help="test, crash, qa, review, user, telemetry, ...")
    a.add_argument("--summary", required=True)
    a.add_argument("--locus", action="append", help="FILE:LINE (repeatable); also read from the evidence")
    a.add_argument("--rule", action="append", help="a rule it's about (repeatable)")
    a.add_argument("--evidence", help="a file with the stack trace, report or comment, or - for stdin")
    a.add_argument("--fingerprint", help="what makes two signals the same (default: source and first locus)")
    a = actions.add_parser("triage")
    a.add_argument("id")
    a.add_argument("--layer", required=True, choices=list(LAYERS))
    a.add_argument("--kind", required=True)
    a.add_argument("--confidence", required=True, choices=CONFIDENCE)
    a.add_argument("--reasoning", required=True)
    a.add_argument("--confirm", action="store_true", help="you agree with it (records your user.email)")
    for name in ("confirm", "show"):
        actions.add_parser(name).add_argument("id")
    a = actions.add_parser("resolve")
    a.add_argument("id")
    a.add_argument("--status", required=True, choices=SIGNAL_STATUSES, help="open reopens it")
    a.add_argument("--fix", help="what fixed it: a PR, a commit, a lesson")
    p = sub.add_parser("signals")
    p.add_argument("--all", action="store_true", help="resolved ones too")
    p.add_argument("--rule", help="only signals traced to this rule")
    p.add_argument("--pending", action="store_true", help="open signals on the rules this sync (or the pending spec change) touches")
    p.add_argument("--by", choices=["layer", "harness"], help="counts of confirmed signals")
    p = sub.add_parser("config")
    p.add_argument("key", nargs="?")
    p = sub.add_parser("init", help="set up specloop in a project")
    p.add_argument("path", nargs="?", default=".")
    p = sub.add_parser("hook", help="what the git hooks run")
    p.add_argument("mode", choices=sorted(set(project.HOOKS.values())))
    p.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("version-ok", help="exit 1, saying why, if this specloop is older than minVersion")
    p = sub.add_parser("skill", help="print a skill's instructions for this version")
    p.add_argument("name")
    args = parser.parse_args()

    root = find_root()
    config = load_config(root)
    # init works on another project; the rest report the gap themselves.
    args.gap = None if args.command == "init" else version_gap(config)
    if args.gap and args.command not in ("version-ok", "skill", "status", "hook"):
        print(args.gap, file=sys.stderr)
    handler = {
        "status": cmd_status,
        "pending": cmd_pending,
        "coverage": cmd_coverage,
        "check": cmd_check,
        "mark": cmd_mark,
        "sync": cmd_sync,
        "trigger": cmd_trigger,
        "cleanup": cmd_cleanup,
        "harness": cmd_harness,
        "trailers": cmd_trailers,
        "blame": cmd_blame,
        "signal": cmd_signal,
        "signals": cmd_signals,
        "config": cmd_config,
        "skill": cmd_skill,
        "init": cmd_init,
        "hook": cmd_hook,
        "version-ok": cmd_version_ok,
    }[args.command]
    return handler(root, config, args)


def main_entry():
    sys.exit(run())


if __name__ == "__main__":
    main_entry()
