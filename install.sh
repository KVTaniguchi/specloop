#!/bin/sh
#
# Install specloop from this checkout, without a package manager, and set
# it up in a project:  ./install.sh /path/to/project
#
# Links ~/.local/bin/specloop to this checkout's bin/specloop, so `git pull`
# here updates it, then runs `specloop init` in the project. With Homebrew,
# install with that instead and run `specloop init` yourself.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
target=${1:?usage: install.sh /path/to/project}
bin="$HOME/.local/bin"
link="$bin/specloop"

if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "error: $link already exists and isn't a link; remove it, or install with brew instead" >&2
    exit 1
fi
mkdir -p "$bin"
ln -sfn "$here/bin/specloop" "$link"
echo "linked $link -> $here/bin/specloop"

case ":$PATH:" in
    *":$bin:"*) ;;
    *) echo "note: $bin isn't on your PATH. The project's hooks find specloop there anyway; add it to PATH to run specloop yourself." ;;
esac

exec "$link" init "$target"
