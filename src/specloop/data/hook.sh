#!/bin/sh
# specloop: the git <hook> hook. Runs the installed specloop through tools/specloop.
# Written by `specloop init` and kept current by `specloop update`. Don't edit.
cli="$(git rev-parse --show-toplevel)/tools/specloop"
[ -x "$cli" ] || exit 0  # never block git because specloop isn't set up here
exec "$cli" hook <mode> "$@"
