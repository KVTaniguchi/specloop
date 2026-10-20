#!/bin/sh
#
# Install specloop into a project:  ./install.sh /path/to/project
#
# Copies the CLI, git hook and Claude Code skills, and adds a config and spec
# template if the project doesn't have them yet. Never overwrites an
# existing spec or config. Enabling the hook (core.hooksPath) is left to you,
# because it replaces any hooks already in .git/hooks.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
target=${1:?usage: install.sh /path/to/project}
target=$(cd "$target" && pwd)

git -C "$target" rev-parse --git-dir >/dev/null 2>&1 || { echo "error: $target is not a git repository" >&2; exit 1; }

mkdir -p "$target/tools/githooks" "$target/.claude/skills/spec-sync" "$target/.claude/skills/spec-init" "$target/docs"

cp "$here/bin/specloop" "$target/tools/specloop"
cp "$here/hooks/post-commit" "$target/tools/githooks/post-commit"
chmod +x "$target/tools/specloop" "$target/tools/githooks/post-commit"
cp "$here/skills/spec-sync/SKILL.md" "$target/.claude/skills/spec-sync/SKILL.md"
cp "$here/skills/spec-init/SKILL.md" "$target/.claude/skills/spec-init/SKILL.md"

[ -e "$target/specloop.json" ] || cp "$here/templates/specloop.json" "$target/specloop.json"
[ -e "$target/docs/SPEC.md" ] || cp "$here/templates/SPEC.md" "$target/docs/SPEC.md"

echo "specloop installed into $target"
echo
echo "Next:"
echo "  1. Edit specloop.json (test command, test paths)."
echo "  2. Paste templates/CLAUDE.md into the project's CLAUDE.md."
echo "  3. Run /spec-init in Claude Code to draft the spec from the code."
echo "  4. Enable the trigger:  git -C \"$target\" config core.hooksPath tools/githooks"
