#!/bin/sh
# specloop shim: runs the specloop installed on this machine.
# Written by `specloop init` and kept current by `specloop update`. Don't edit.
#
# Git GUIs run hooks with a short PATH that often leaves out Homebrew and
# pipx, so after PATH this looks where those install.
here=$(cd -P "$(dirname "$0")" && pwd)
IFS=:
for dir in $PATH /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
    [ -n "$dir" ] && [ -f "$dir/specloop" ] && [ -x "$dir/specloop" ] || continue
    [ "$(cd -P "$dir" 2>/dev/null && pwd)" = "$here" ] && continue  # this shim, if tools/ is on PATH
    unset IFS
    exec "$dir/specloop" "$@"
done
unset IFS

install="brew install KVTaniguchi/tap/specloop, or pipx install specloop"
if [ "$1" = hook ]; then
    # Never fail a commit, merge or rebase because specloop isn't installed.
    echo "specloop: not installed ($install); skipping" >&2
    exit 0
fi
echo "specloop: not installed ($install)" >&2
exit 127
