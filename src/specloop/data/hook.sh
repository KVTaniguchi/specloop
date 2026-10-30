#!/bin/sh
# specloop: the git <hook> hook. Runs the installed specloop through tools/specloop.
# Written by `specloop init` and kept current by `specloop update`. Don't edit.
exec "$(git rev-parse --show-toplevel)/tools/specloop" hook <mode> "$@"
