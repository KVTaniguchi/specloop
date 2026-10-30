"""
The files specloop keeps in a project: thin ones that defer to the
installed version. `specloop init` and `specloop update` write them; nothing
else does.
"""

from pathlib import Path

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
