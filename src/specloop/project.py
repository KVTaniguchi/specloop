"""
The files specloop keeps in a project: thin ones that defer to the
installed version. `specloop init` and `specloop update` write them; nothing
else does.
"""

import difflib
import hashlib
import json
import re
from collections import namedtuple
from pathlib import Path

from specloop import __version__

# Skill texts, the trigger and templates, shipped with the package.
DATA = Path(__file__).resolve().parent / "data"

SKILLS = ("spec-sync", "spec-init", "spec-triage")
# In every stub, so `update` and `status` can tell a stub from a full copy.
STUB_MARKER = "<!-- specloop stub -->"


def skill_text(name):
    return (DATA / "skills" / name / "SKILL.md").read_text()


def frontmatter(text):
    """The leading `---` block, verbatim, through its closing line."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return ""
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[: i + 1])
    return ""


def render_stub(name):
    """A skill as a project keeps it: the frontmatter that tells the agent
    when to use it, and a body that sends it to the installed version."""
    body = (DATA / "stub.md").read_text().replace("<name>", name)
    return frontmatter(skill_text(name)) + "\n" + body


# Each git hook a project keeps, and the `specloop hook` mode it runs.
HOOKS = {"post-commit": "commit", "post-merge": "merge", "post-rewrite": "rebase", "commit-msg": "commit-msg"}
# In tools/specloop, so `update` can tell the shim from a copied CLI.
SHIM_MARKER = "# specloop shim"

# One file `init` or `update` writes, keeps or removes. `note` is a message
# or a diff to print, or ""; `text` is the new contents for create and replace.
Change = namedtuple("Change", "path action note text", defaults=("",))
ACTIONS = ("create", "replace", "keep", "delete")
EXECUTABLE = ("tools/specloop", "tools/githooks/")


def render_shim():
    return (DATA / "shim.sh").read_text()


def render_hook(git_hook):
    return (DATA / "hook.sh").read_text().replace("<hook>", git_hook).replace("<mode>", HOOKS[git_hook])


def thin_files():
    """{relative path: contents} for every file a project keeps that defers to
    the installed specloop."""
    files = {"tools/specloop": render_shim()}
    files.update({f"tools/githooks/{hook}": render_hook(hook) for hook in HOOKS})
    files.update({f".claude/skills/{name}/SKILL.md": render_stub(name) for name in SKILLS})
    return files


def plan_init(root, config, harness="claude"):
    """What `specloop init` writes: the thin files where they're missing,
    specloop.json if there's none, and the starter spec if there's no spec.
    It never replaces a file that's already there."""
    changes = []
    for rel, text in thin_files().items():
        path = root / rel
        if not path.exists():
            changes.append(Change(rel, "create", "", text))
        elif path.read_text() != text:
            changes.append(Change(rel, "keep", "already exists; `specloop update` replaces it"))
    if not (root / "specloop.json").exists():
        template = json.loads((DATA / "templates" / "specloop.json").read_text())
        changes.append(Change("specloop.json", "create", "", json.dumps({"minVersion": __version__, **template}, indent=2) + "\n"))
        spec, ledger = template["spec"], template["ledger"]
    else:
        spec, ledger = config["spec"], config["ledger"]
    if not spec.endswith(".md") and not (root / spec).exists():
        for name in ("README.md", "feature.md"):
            changes.append(Change(f"{spec}/{name}", "create", "", (DATA / "templates" / "spec" / name).read_text()))
    return changes + block_changes(root, harness, {"spec": spec, "ledger": ledger})


def write_files(root, changes):
    """Apply `create`, `replace` and `delete` changes. `keep` ones write nothing."""
    for change in changes:
        path = root / change.path
        if change.action == "delete":
            path.unlink()
        elif change.action in ("create", "replace"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(change.text)
            if change.path.startswith(EXECUTABLE):
                path.chmod(0o755)


# specloop's part of CLAUDE.md / AGENTS.md sits between these markers.
# `init` and `update` rewrite what's between them and nothing else.
BEGIN = "<!-- specloop:begin (managed by specloop update; edits here are replaced) -->"
END = "<!-- specloop:end -->"
RULES_HEADING = "### Spec sync rules for this project"
# How the section began when it was pasted in by hand, before the markers.
PASTED_HEADING = "## Spec-driven development (specloop)"
# Where `update` puts the lines of a pasted section the project wrote itself.
KEPT_HEADING = "### Kept from the old specloop section"
# How close an old line must be to some version of the template to count as
# specloop's wording rather than the project's. Older wordings score 0.88 and
# up; a project's own instruction scores well under 0.5.
TEMPLATE_LIKENESS = 0.8


def block_body(config=None):
    """specloop's part of CLAUDE.md / AGENTS.md, for this project's spec
    layout: one file or a tree, and where the ledger is."""
    config = config or {}
    spec, ledger = config.get("spec", "docs/spec"), config.get("ledger", "docs/.spec-implemented")
    if spec.endswith(".md"):
        source = f"**`{spec}` is the source of truth** for what this project does. Read it before changing behavior."
    else:
        spec = spec.rstrip("/") + "/"
        source = (f"**The spec in `{spec}` is the source of truth** for what this project does. `{spec}README.md` is the "
                  "overview and links to one doc per feature. Read the overview and the relevant feature docs before changing behavior.")
    return (DATA / "claude-block.md").read_text().replace("{source}", source).replace("{spec}", spec).replace("{ledger}", ledger)


def render_block(config=None):
    return f"{BEGIN}\n{block_body(config)}{END}\n"


def template_lines():
    """Every line the pasted template and the managed block have had."""
    texts = [p.read_text() for p in sorted((DATA / "copies" / "claude-md-template").glob("*"))]
    texts += [block_body(), block_body({"spec": "docs/SPEC.md"})]
    return {line.strip() for text in texts for line in text.splitlines() if line.strip()}


def own_lines(section):
    """The lines of an old pasted section that the project wrote itself, not
    any version of specloop's template."""
    known = template_lines()

    def specloops(line):
        return line in known or any(difflib.SequenceMatcher(None, line, k).ratio() >= TEMPLATE_LIKENESS for k in known)

    return [
        line for line in section.splitlines()
        if line.strip() and line.strip() != PASTED_HEADING and not line.startswith("<!--") and not specloops(line.strip())
    ]


def block_span(text):
    """(start, end, inside) of the marked block, or None."""
    start = text.find(BEGIN)
    end = text.find(END, start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    inside = text[start + len(BEGIN) + 1 : end]
    end += len(END)
    if text[end : end + 1] == "\n":
        end += 1
    return start, end, inside


def pasted_span(text):
    """(start, end) of a section pasted from the old template: from its
    heading to the project's rules, the next `## ` heading, or the end."""
    if text.startswith(PASTED_HEADING):
        start = 0
    else:
        start = text.find("\n" + PASTED_HEADING)
        if start < 0:
            return None
        start += 1
    after = start + len(PASTED_HEADING)
    ends = [i for i in (text.find("\n" + RULES_HEADING, after), text.find("\n## ", after)) if i >= 0]
    return start, (min(ends) + 1 if ends else len(text))


def unified(old, new, old_label, new_label):
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), old_label, new_label))


def apply_block(text, name="CLAUDE.md", config=None):
    """(new text, diff of what it replaced). The diff is "" when the block was
    already current, or when it was added rather than replacing anything.
    Lines a project added to a section pasted by hand are kept, under their
    own heading after the block."""
    body = block_body(config)
    label = f"{name} (specloop {__version__})"
    marked = block_span(text)
    if marked:
        start, end, inside = marked
        if inside == body:
            return text, ""
        return text[:start] + render_block(config) + text[end:], unified(inside, body, name, label)
    pasted = pasted_span(text)
    if pasted:
        start, end = pasted
        old = text[start:end]
        tail = text[end:]
        kept = own_lines(old)
        keep = f"\n{KEPT_HEADING}\n\n" + "\n".join(kept) + "\n" if kept else ""
        note = f"kept {len(kept)} line{'s' * (len(kept) != 1)} this project wrote, under \"{KEPT_HEADING}\"\n" if kept else ""
        return text[:start] + render_block(config) + keep + ("\n" if tail else "") + tail, unified(old, body, name, label) + note
    head = text.rstrip("\n") + "\n\n" if text.strip() else ""
    rules = "" if RULES_HEADING in text else "\n" + (DATA / "rules-section.md").read_text()
    return head + render_block(config) + rules, ""


def outside_block(text):
    """The project's own part of CLAUDE.md / AGENTS.md."""
    marked = block_span(text)
    return text[: marked[0]] + text[marked[1] :] if marked else text


def block_targets(root, harness):
    """The instruction files that get the block: every CLAUDE.md and AGENTS.md
    there is, or the one the configured agent reads if there are none."""
    present = [root / name for name in ("CLAUDE.md", "AGENTS.md") if (root / name).exists()]
    return present or [root / ("AGENTS.md" if harness == "cursor" else "CLAUDE.md")]


def block_changes(root, harness, config=None):
    changes = []
    for path in block_targets(root, harness):
        text = path.read_text() if path.exists() else ""
        new, diff = apply_block(text, path.name, config)
        if new != text:
            changes.append(Change(path.name, "replace" if path.exists() else "create", diff, new))
    return changes


# In each hook script, so `update` can tell it from a copied hook.
HOOK_MARKER = "Runs the installed specloop"
TRIGGER = "tools/githooks/specloop-trigger"  # copied by install.sh; now inside the package


def parse_version(text):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text).strip())
    if not match:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(part) for part in match.groups())


def kind_of(rel):
    """Which entry of known-copies.json a project file is checked against."""
    if rel == "tools/specloop":
        return "cli"
    if rel == TRIGGER:
        return "trigger"
    if rel.startswith("tools/githooks/"):
        return rel.rsplit("/", 1)[1]
    return rel.split("/")[2]  # .claude/skills/<name>/SKILL.md


def blob_hash(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def classify(path, rel):
    """current: what init would write now. thin: a shim, hook or stub from
    another version. copy: an unedited copy of a past full file. edited:
    anything else, which update keeps."""
    text = path.read_text()
    if text == thin_files().get(rel):
        return "current"
    marker = SHIM_MARKER if rel == "tools/specloop" else STUB_MARKER if rel.endswith("SKILL.md") else HOOK_MARKER
    if rel != TRIGGER and marker in text:
        return "thin"
    known = json.loads((DATA / "known-copies.json").read_text())
    return "copy" if blob_hash(path.read_bytes()) in known.get(kind_of(rel), []) else "edited"


def closest_copy(rel, local):
    """The past version of this file the local one is closest to: most likely
    the copy it was edited from. None if specloop has no texts for its kind."""
    directory = DATA / "copies" / kind_of(rel)
    texts = [p.read_text() for p in sorted(directory.iterdir())] if directory.is_dir() else []
    return max(texts, key=lambda t: difflib.SequenceMatcher(None, t, local).ratio(), default=None)


def kept_note(rel, local):
    """Why an edited file is kept, and what was changed in it."""
    base = closest_copy(rel, local)
    if base is None:
        return "edited here, so it's kept and won't get updates"
    diff = unified(base, local, f"{rel} (as copied from specloop)", rel)
    return f"edited here, so it's kept and won't get updates. What was changed since it was copied:\n{diff}"


def config_change(root):
    """specloop.json with minVersion raised to this version, every other key
    as it was."""
    path = root / "specloop.json"
    if not path.exists():
        template = json.loads((DATA / "templates" / "specloop.json").read_text())
        return Change("specloop.json", "create", "", json.dumps({"minVersion": __version__, **template}, indent=2) + "\n")
    text = path.read_text()
    raw = json.loads(text)
    if raw.get("minVersion") == __version__:
        return None
    return Change("specloop.json", "replace", f"minVersion is now {__version__}", with_min_version(text, raw))


def with_min_version(text, raw):
    """`text` with minVersion set, editing only that key so the project's
    formatting stays as it was. Falls back to rewriting the whole file if the
    edit doesn't parse back to the same config."""
    value = json.dumps(__version__)
    if "minVersion" in raw:
        new = re.sub(r'("minVersion"\s*:\s*)"[^"]*"', lambda m: m.group(1) + value, text, count=1)
    else:
        brace = text.index("{")
        after = text[brace + 1 :]
        if after.startswith("\n"):
            indent = re.match(r"\n([ \t]*)", after).group(1) or "  "
            new = text[: brace + 1] + f'\n{indent}"minVersion": {value},' + after
        elif after.lstrip().startswith("}"):
            new = text[: brace + 1] + f'"minVersion": {value}' + after
        else:
            new = text[: brace + 1] + f'"minVersion": {value}, ' + after
    wanted = {**raw, "minVersion": __version__}
    try:
        if json.loads(new) == wanted:
            return new
    except ValueError:
        pass
    return json.dumps({"minVersion": __version__, **{k: v for k, v in raw.items() if k != "minVersion"}}, indent=2) + "\n"


def edited_cli(root):
    """Why update can't go ahead, or None. Every file update writes relies on
    tools/specloop being the shim, so an edited copy of the old CLI means
    switching nothing until it's dealt with."""
    path = root / "tools" / "specloop"
    if path.exists() and classify(path, "tools/specloop") == "edited":
        return (
            "tools/specloop is edited here, so update changed nothing: the hooks and skill stubs it would write "
            "need tools/specloop to be specloop's shim. Move your changes out of it (or delete it), then run "
            "specloop update again."
        )
    return None


def plan_update(root, config, harness="claude"):
    """What `specloop update` changes: thin files brought to this version,
    unedited copies replaced by thin files, edited files kept, the managed
    block refreshed, and minVersion raised."""
    changes = []
    for rel, text in thin_files().items():
        path = root / rel
        if not path.exists():
            changes.append(Change(rel, "create", "", text))
            continue
        state = classify(path, rel)
        if state in ("thin", "copy"):
            changes.append(Change(rel, "replace", "", text))
        elif state == "edited":
            changes.append(Change(rel, "keep", kept_note(rel, path.read_text())))
    trigger = root / TRIGGER
    if trigger.exists():
        if classify(trigger, TRIGGER) == "copy":
            changes.append(Change(TRIGGER, "delete", "the trigger now ships with specloop"))
        else:
            changes.append(Change(TRIGGER, "keep", "edited here; the hooks no longer run it, so it can be removed"))
    changes += block_changes(root, harness, config)
    config_update = config_change(root)
    return changes + ([config_update] if config_update else [])


def forks(root):
    """Skill files that are full copies, not stubs: they don't get updates."""
    paths = [root / ".claude" / "skills" / name / "SKILL.md" for name in SKILLS]
    return [p for p in paths if p.exists() and STUB_MARKER not in p.read_text()]


def release_notes(since, until):
    """The CHANGELOG sections after `since`, up to and including `until`."""
    low, high = parse_version(since), parse_version(until)
    text = (DATA / "CHANGELOG.md").read_text()
    sections = re.split(r"(?m)^(?=## \d+\.\d+\.\d+)", text)
    picked = [s for s in sections if s.startswith("## ") and low < parse_version(s.split()[1]) <= high]
    return "".join(picked).rstrip("\n") + "\n" if picked else ""
