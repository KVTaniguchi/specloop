#!/bin/sh
#
# Install specloop into a project:  ./install.sh /path/to/project
#
# Copies the CLI, git hooks and skills (spec-sync, spec-init, spec-triage) (in .claude/skills/, which both Claude
# Code and Cursor read), and adds a config and a spec tree template if the
# project doesn't have them yet. Never overwrites an
# existing spec or config. Enabling the hook (core.hooksPath) is left to you,
# because it replaces any hooks already in .git/hooks.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
target=${1:?usage: install.sh /path/to/project}
target=$(cd "$target" && pwd)

git -C "$target" rev-parse --git-dir >/dev/null 2>&1 || { echo "error: $target is not a git repository" >&2; exit 1; }

mkdir -p "$target/tools/githooks" "$target/.claude/skills/spec-sync" "$target/.claude/skills/spec-init" \
    "$target/.claude/skills/spec-triage" "$target/docs"

cp "$here/bin/specloop" "$target/tools/specloop"
chmod +x "$target/tools/specloop"
for hook in specloop-trigger post-commit post-merge post-rewrite commit-msg; do
    cp "$here/hooks/$hook" "$target/tools/githooks/$hook"
    chmod +x "$target/tools/githooks/$hook"
done
cp "$here/skills/spec-sync/SKILL.md" "$target/.claude/skills/spec-sync/SKILL.md"
cp "$here/skills/spec-init/SKILL.md" "$target/.claude/skills/spec-init/SKILL.md"
cp "$here/skills/spec-triage/SKILL.md" "$target/.claude/skills/spec-triage/SKILL.md"

[ -e "$target/specloop.json" ] || cp "$here/templates/specloop.json" "$target/specloop.json"
spec=$(cd "$target" && tools/specloop config spec)
case "$spec" in
    *.md) [ -e "$target/$spec" ] || echo "note: $spec doesn't exist yet; /spec-init will draft it" ;;
    *) if [ ! -e "$target/$spec" ]; then
           mkdir -p "$target/$spec"
           cp "$here/templates/spec/README.md" "$here/templates/spec/feature.md" "$target/$spec/"
       fi ;;
esac

echo "specloop installed into $target"
echo
echo "Next:"
echo "  1. Edit specloop.json (test command, test paths)."
echo "  2. Paste templates/CLAUDE.md into the project's CLAUDE.md (Claude Code) or AGENTS.md (Cursor)."
echo "  3. Run /spec-init in Claude Code or Cursor to draft the spec from the code."
echo "  4. Enable the trigger:  git -C \"$target\" config core.hooksPath tools/githooks"
echo "     Using Cursor?        git -C \"$target\" config specloop.harness cursor"
