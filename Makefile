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
# kacho: build all example documents with LuaLaTeX.
#
#   make              build every examples/*.tex into build/*.pdf
#   make view         open the PDFs ($VIEWER, macOS open, xdg-open); headless:
#                     render PNG previews into build/png/ and print their paths
#   make render       render every page to build/png/<doc>-<page>.png (DPI=110)
#   make test         unit tests (texlua) + end-to-end suite (if present)
#   make unit         unit tests only
#   make e2e          tests/e2e/run.sh ; make e2e-quick : tests/e2e/run.sh --quick
#   make clean        remove build/
#
# Clone into a path without spaces (TEXINPUTS/LUAINPUTS cannot hold spaces).
SHELL := /bin/bash

# Use TinyTeX when installed in ~/.TinyTeX (prepended so it wins); otherwise
# whatever lualatex is on PATH (TeX Live 2023+).
TINYTEX_BIN := $(firstword $(wildcard $(HOME)/.TinyTeX/bin/x86_64-linux $(HOME)/.TinyTeX/bin/*))
ifneq ($(TINYTEX_BIN),)
export PATH := $(TINYTEX_BIN):$(PATH)
endif
# kpathsea search paths: our tex/ directory first, then the defaults (trailing :)
export TEXINPUTS := $(CURDIR)/tex//:
export LUAINPUTS := $(CURDIR)/tex//:
# reproducible PDFs (no timestamps/IDs that change between builds)
export SOURCE_DATE_EPOCH ?= 1767225600
export FORCE_SOURCE_DATE := 1

LUALATEX   ?= lualatex
LATEXFLAGS ?= -interaction=nonstopmode -halt-on-error -file-line-error
BUILD      := build
DPI        ?= 110
EXAMPLES   := $(sort $(wildcard examples/*.tex))
PDFS       := $(patsubst examples/%.tex,$(BUILD)/%.pdf,$(EXAMPLES))
ANIM_EXAMPLES := $(sort $(wildcard examples/animated/*.tex))
ANIM_PDFS     := $(patsubst examples/animated/%.tex,$(BUILD)/%.pdf,$(ANIM_EXAMPLES))
# make owns the dependency on every package file (latexmk misses required Lua modules)
PKG        := $(wildcard tex/*.sty tex/*.lua)

.PHONY: all view render site test unit e2e e2e-quick clean check-tools animated view-animated animated-frames
all: $(PDFS)

check-tools:
	@command -v $(LUALATEX) >/dev/null || { echo "error: lualatex not found. Install TeX Live 2023+ (or TinyTeX in ~/.TinyTeX)." >&2; exit 1; }

# Up to 3 passes; rerun only when LaTeX asks for it. Always run from the
# project root (never from another directory).
$(BUILD)/%.pdf: examples/%.tex $(PKG) | check-tools
	@mkdir -p $(BUILD)
	@for i in 1 2 3; do \
	  echo "lualatex $< (pass $$i)"; \
	  $(LUALATEX) $(LATEXFLAGS) -output-directory=$(BUILD) $< >$(BUILD)/$*.stdout 2>&1 \
	    || { tail -n 40 $(BUILD)/$*.log >&2; echo "FAILED: $< (see $(BUILD)/$*.log)" >&2; rm -f $@; exit 1; }; \
	  grep -qE 'Rerun to get|Label\(s\) may have changed|Please rerun' $(BUILD)/$*.log || break; \
	done
	@grep -E '^Package kacho Warning:' $(BUILD)/$*.log >&2 || true
	@echo "built $@"

$(BUILD)/%.pdf: examples/animated/%.tex $(PKG) | check-tools
	@mkdir -p $(BUILD)
	@kpsewhich animate.sty >/dev/null || { echo "error: animate.sty not found. Install texlive-latex-extra or run: tlmgr install animate media9 ocgx2 pdfbase" >&2; exit 1; }
	@for i in 1 2 3; do \
	  echo "lualatex $< (pass $$i)"; \
	  $(LUALATEX) $(LATEXFLAGS) -output-directory=$(BUILD) $< >$(BUILD)/$*.stdout 2>&1 \
	    || { tail -n 40 $(BUILD)/$*.log >&2; echo "FAILED: $< (see $(BUILD)/$*.log)" >&2; rm -f $@; exit 1; }; \
	  grep -qE 'Rerun to get|Label\(s\) may have changed|Please rerun|finalize animations' $(BUILD)/$*.log || break; \
	done
	@echo "built $@"

animated: $(ANIM_PDFS)

view-animated: animated
	@DPI=$(DPI) scripts/view.sh $(ANIM_PDFS)

animated-frames: $(PKG) $(ANIM_EXAMPLES) | check-tools
	@mkdir -p $(BUILD) $(BUILD)/png
	@$(LUALATEX) $(LATEXFLAGS) -output-directory=$(BUILD) -jobname=kacho-animated-frames '\def\kachoAnimFrames{1}\input{examples/animated/kacho-animated.tex}' >$(BUILD)/kacho-animated-frames.stdout 2>&1 \
	  || { tail -n 40 $(BUILD)/kacho-animated-frames.log >&2; exit 1; }
	@rm -f $(BUILD)/png/kacho-animated-frame-*.png
	@pdftoppm -r 150 -png $(BUILD)/kacho-animated-frames.pdf $(BUILD)/png/kacho-animated-frame
	@echo "rendered frames in $(BUILD)/png/kacho-animated-frame-*.png"

render: all
	@scripts/render.sh $(DPI) $(PDFS)

view: all
	@DPI=$(DPI) scripts/view.sh $(PDFS)

site: all animated animated-frames
	@scripts/build_site.sh $(BUILD)

unit:
	texlua tests/unit/run.lua

e2e:
	@if [ -x tests/e2e/run.sh ]; then tests/e2e/run.sh; else echo "tests/e2e/run.sh not present; skipping"; fi

e2e-quick:
	@if [ -x tests/e2e/run.sh ]; then tests/e2e/run.sh --quick; else echo "tests/e2e/run.sh not present; skipping"; fi

test: unit e2e

clean:
	rm -rf $(BUILD)
