"""API-dependent constants for the kacho E2E suite.

Everything the suite assumes about the *user-facing* TeX API and about the
`debug` log vocabulary lives here, so that aligning the suite with
`tex/API.md` (written by milestone M1/M3) is a one-file change.

Source of truth: PROJECT.md "Interface Contracts" and survey_2 §4.4-4.6.
"""

# ---------------------------------------------------------------------------
# Package options (PROJECT.md "TeX user API").
# ---------------------------------------------------------------------------
PALETTES = ["sumi", "hanga"]
THEMES = ["haru", "natsu", "aki", "fuyu", "shochikubai"]
# survey_2 §4.5 layout variants usable on body pages.
LAYOUTS = [
    "corner-spray",
    "margin-column",
    "header-garland",
    "footer-ground",
    "scattered-petals",
]
PAPERS = ["a4paper", "a5paper", "letterpaper", "b5paper"]

# Title page command. The key=value form is deliberately chosen so that it
# works whether \kachoTitlePage takes key=value pairs or a plain title text:
# in the latter case the words "Spring Garden" are still typeset.
TITLE_TEXT = "Spring Garden"
TITLE_PAGE_CMD = (
    r"\kachoTitlePage{title={Spring Garden}, subtitle={A Kacho Test}, "
    r"author={E2E Suite}}"
)
# Chapter opener (shikishi) — survey_2 §4.5. Selected per page.
SHIKISHI_CMD = r"\kachoThisPage{layout=shikishi}"

# ---------------------------------------------------------------------------
# Debug log (PROJECT.md "Testing hook").
#   page=<n> elem=<kind> bbox=<x0> <y0> <x1> <y1> textblock=<x0> <y0> <x1> <y1>
# in bp, origin bottom-left. Written to <jobname>.kacho.log when the `debug`
# option is given or KACHO_DEBUG=1 is set in the environment.
# ---------------------------------------------------------------------------
DEBUG_ENV = {"KACHO_DEBUG": "1"}
OFF_ENV = {"KACHO_OFF": "1"}
SEED_ENV = "KACHO_SEED"
DEBUG_LOG_SUFFIX = ".kacho.log"

# Element kinds exempt from the "no intersection with the text block" check
# (PROJECT.md debug-log conventions: kind `ground` is a paper tint; M3 §4.9.6:
# `inline` spray elements are checked against their inline box and word boxes).
# Matched as a dash/underscore/colon/dot-separated token of the kind string.
OVERLAP_EXEMPT_KIND = r"(^|[-_:.])(ground|inline)($|[-_:.])"

# Element kinds exempt from the 5 mm edge safe-zone check (PROJECT.md
# debug-log conventions: `trunk`, `culm`, `stem`, `vine` may run off the paper
# edge; `ground` is a paper tint).
EDGE_EXEMPT_KIND = r"(^|[-_:.])(trunk|culm|stem|vine|ground)($|[-_:.])"

EDGE_SAFE_MM = 5.0

# Motif vocabulary expected in debug-log element kinds (case-insensitive
# regex search on the kind string). PROJECT.md features 12-22.
MOTIF_KINDS = {
    "ume": r"ume|plum",
    "sakura": r"sakura|cherry",
    "bamboo": r"bamboo|take|culm",
    "orchid": r"orchid|(^|[^a-z])ran([^a-z]|$)",
    "maple": r"maple|momiji",
    "wisteria": r"wisteria|raceme",
    "iris": r"iris|ayame|shobu|kakitsubata",
    "bird": r"bird|uguisu|robin|sparrow|suzume|swallow|tsubame",
    "seal": r"seal|hanko|inkan",
    "rock": r"rock|stone|ishi",
    "fuji": r"fuji(?!-?vine)|mountain",
    "kasumi_bokashi": r"kasumi|mist|bokashi|sky",
}
BONUS_FLORA = {
    "osmanthus": r"osmanthus|kinmokusei",
    "narcissus": r"narcissus|suisen",
    "chrysanthemum": r"chrysanthemum|kiku",
    "pine": r"pine|matsu",
    "camellia": r"camellia|tsubaki",
}
BRANCH_KIND = r"branch|twig|trunk|bough|ume|plum|sakura|cherry|camellia|maple"

# ---------------------------------------------------------------------------
# Feature 32: user-controlled placement (ORIGINAL_REQUEST follow-up 02:06Z).
# Proposed API: explorer_m3_1 handoff §4.9. Re-check every name below when
# tex/API.md documents the M3 placement API; tests only use these constants.
# ---------------------------------------------------------------------------
# Absolute spawn origin. Keys: at, from (page|text|safe), dx, dy, angle (deg,
# 0 = +x/right, 90 = up), size (dim), motif, seed. Several calls on one page
# form a spawn-point list.
SPAWN_CMD = r"\kachoSpawn{%s}"
# Inline spray occupying a real box in the text flow (usable in figures).
# Keys: width, height, motif, seed, from, density.
SPRAY_CMD = r"\kachospray[%s]"
PAGE_CMD = r"\kachoThisPage{%s}"
SETUP_CMD = r"\kachosetup{%s}"
# Per-page / global keys.
REGIONS_KEY = "regions"   # auto | {left,right,top,bottom,outer,inner} |
                          # corners | frame | none
SPAWN_KEY = "spawn"       # shorthand list: {br@125; tl+20mm-0mm@-70}
MOTIF_KEY = "motif"       # motif=<name> or motif={ume,uguisu}
BORDER_FRAME_LAYOUT = "border-frame"
# Anchor names -> (fx, fy) fraction of the reference box (from=page: the
# paper; origin bottom-left, bp).
ANCHORS = {
    "tl": (0.0, 1.0), "tc": (0.5, 1.0), "tr": (1.0, 1.0),
    "ml": (0.0, 0.5), "mr": (1.0, 0.5),
    "bl": (0.0, 0.0), "bc": (0.5, 0.0), "br": (1.0, 0.0),
}
# Long anchor names must be accepted too (explorer_m3_1 §4.9).
ANCHOR_LONG = {"tl": "top-left", "tr": "top-right", "bl": "bottom-left",
               "br": "bottom-right"}
# Offsets: dx > 0 moves right, dy > 0 moves up (PDF convention).
DX_SIGN, DY_SIGN = 1, 1
# Debug-log comment lines (agreed with M3; '#' lines carry extra info).
#   # page=1 inline spray=1 box=x0 y0 x1 y1
#   # page=1 user spawn=1 at=br origin=595.28 0.00 angle=125.0 size=320.0 drawn
_N = r"(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
LOG_INLINE_RE = (r"#\s*page=(\d+)\s+inline\s+spray=(\d+)\s+box=" +
                 r"\s+".join([_N] * 4))
LOG_SPAWN_RE = (r"#\s*page=(\d+)\s+user\s+spawn=(\d+)\s+at=(\S+)\s+origin=" +
                _N + r"\s+" + _N + r"\s+angle=" + _N + r"\s+size=" + _N +
                r"\s+(\w+)")
SPAWN_OK_STATUS = r"drawn|partial"
# Inline spray element kinds carry this token; they are exempt from the
# text-block check only while inside a logged inline box.
INLINE_KIND = r"(^|[-_:.])inline($|[-_:.])"
# A drawn spawn must have an element within this distance of its origin.
SPAWN_NEAR_MM = 40.0

# ---------------------------------------------------------------------------
# Feature 33: licensing (ORIGINAL_REQUEST follow-up 02:06Z).
# ---------------------------------------------------------------------------
LICENSE_ID = "Apache-2.0"
LICENSE_MARKERS = ["Apache License", "Version 2.0"]
COPYRIGHT_LINE = "Copyright 2026"
# Standard Apache-2.0 source header (either long form or SPDX).
APACHE_HEADER_RE = (r"Licensed under the Apache License, Version 2\.0|"
                    r"SPDX-License-Identifier:\s*Apache-2\.0")
HEADER_SCAN_CHARS = 4000
# Own source files that must carry the header (glob patterns, repo-relative).
OWN_SOURCE_GLOBS = {
    "tex-sty": ["tex/kacho*.sty"],
    "tex-lua": ["tex/kacho*.lua"],
}
MIT_NOTICE_MARKERS = ["Permission is hereby granted",
                      "Kevin Raymond"]
ADAPTED_RE = r"adapted\s+from\s+(the\s+)?florilegium"
NOTICE_FILES = ["NOTICE", "NOTICE.md", "NOTICE.txt", "THIRD_PARTY.md"]
README_ALGO_HEADING = r"^#{1,6}\s*Algorithms\s*(?:&|and|&amp;)\s*References"
ALGO_BLOCK_MARKER = "ALGORITHMS & REFERENCES"
ALGO_REQUIRED_MODULES = (
    "kacho-growth.lua",
    "kacho-flora.lua",
    "kacho-fauna.lua",
    "kacho-scenery.lua",
    "kacho-seal.lua",
    "kacho-wash.lua",
)

# ---------------------------------------------------------------------------
# Feature 31: optional animated demo (follow-up 00:13Z). Blocking only when
# ANIM_DIR exists; advisory (WARN) otherwise.
# ---------------------------------------------------------------------------
ANIM_DIR = "examples/animated"
ANIM_MAKE_TARGET = "animated"
ANIM_VIEW_TARGET = "view-animated"
# Environment switch for the frames-as-pages debug build (each animation
# frame typeset as its own page, so the overlap/edge checks can run).
ANIM_FRAMES_ENV = {"KACHO_ANIM_FRAMES": "1"}
ANIM_PDF_MARKERS = [rb"/JavaScript", rb"/AA\b", rb"/OCProperties", rb"/OCG\b"]
ANIM_VIEWERS = r"Acrobat|Okular|PDF-XChange|Foxit"
