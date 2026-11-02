#!/usr/bin/env bash
# Copyright 2026 Allen Jue
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# view.sh file.pdf... : open PDFs with $VIEWER, macOS `open`, or xdg-open.
# Headless (no reachable display): render PNG previews and print PDF + PNG paths.
set -u
if [ $# -lt 1 ]; then echo "usage: $0 file.pdf..." >&2; exit 2; fi
here="$(cd "$(dirname "$0")" && pwd)"
abspath() { echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; }
headless() {
  echo "No display available: rendering PNG previews instead." >&2
  "$here/render.sh" "${DPI:-110}" "$@" || return 1
  for f in "$@"; do echo "PDF: $(abspath "$f")"; done
}
if [ -n "${VIEWER:-}" ]; then
  vbin="${VIEWER%% *}"
  if command -v "$vbin" >/dev/null 2>&1; then
    ok=1
    for f in "$@"; do
      $VIEWER "$f" >/dev/null 2>&1 &
      pid=$!
      sleep 0.05
      if ! kill -0 "$pid" 2>/dev/null; then
        wait "$pid" || ok=0
      fi
    done
    if [ $ok = 1 ]; then
      for f in "$@"; do echo "opened $(abspath "$f") with $VIEWER"; done
      exit 0
    fi
  fi
  echo "warning: VIEWER='$VIEWER' not found or failed; falling back to headless preview." >&2
fi
case "$(uname -s)" in
  Darwin) open "$@" && { for f in "$@"; do echo "opened $(abspath "$f")"; done; exit 0; } ;;
  MINGW*|MSYS*|CYGWIN*) for f in "$@"; do start "" "$f"; done; exit 0 ;;
esac
display_ok() {
  [ -n "${WAYLAND_DISPLAY:-}" ] && return 0
  [ -n "${DISPLAY:-}" ] || return 1
  # xdg-open returns 0 even when no X server is reachable: probe the server.
  if command -v xdpyinfo >/dev/null; then timeout 5 xdpyinfo >/dev/null 2>&1; else return 0; fi
}
if display_ok && command -v xdg-open >/dev/null; then
  ok=1
  for f in "$@"; do xdg-open "$f" >/dev/null 2>&1 || ok=0; done
  if [ $ok = 1 ]; then for f in "$@"; do echo "opened $(abspath "$f")"; done; exit 0; fi
fi
headless "$@"
