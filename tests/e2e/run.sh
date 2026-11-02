#!/usr/bin/env bash
# kacho E2E suite entry point. See tests/e2e/kacho_e2e.py --help.
# Exit status 0 iff all selected blocking tests pass.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"
exec python3 -B "$HERE/kacho_e2e.py" "$@"
