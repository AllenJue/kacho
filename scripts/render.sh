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
# render.sh DPI file.pdf... -> build/png/<name>-<page>.png (one PNG per page)
# pdftoppm pads page numbers once a document has >= 10 pages (-01.png); glob, don't construct names.
set -euo pipefail
if [ $# -lt 2 ]; then echo "usage: $0 DPI file.pdf..." >&2; exit 2; fi
dpi=$1; shift
command -v pdftoppm >/dev/null || { echo "error: pdftoppm (poppler-utils) not found" >&2; exit 1; }
out=build/png
mkdir -p "$out"
for f in "$@"; do
  [ -f "$f" ] || { echo "error: $f not found" >&2; exit 1; }
  name=$(basename "$f" .pdf)
  rm -f "$out/$name"-*.png
  pdftoppm -r "$dpi" -png "$f" "$out/$name"
  n=$(ls "$out/$name"-*.png | wc -l)
  echo "$f -> $n page(s) in $out/$name-*.png"
  for p in "$out/$name"-*.png; do echo "  $(cd "$(dirname "$p")" && pwd)/$(basename "$p")"; done
done
