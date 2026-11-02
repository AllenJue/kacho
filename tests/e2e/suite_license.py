"""Feature 33 (licensing) and README algorithm-reference consistency tests.

Sources (authoritative):
  * Apache License 2.0 for the project's own code, standard Apache header in
    source files, florilegium-derived (MIT, Kevin Raymond) portions keep their
    MIT notices in file headers + NOTICE credits.
  * README section "Algorithms & References"; an e2e/doc check that every
    algorithm module has a corresponding README entry.

Registered by suite.build_registry() through register(add, repo).
"""

import glob
import os
import re

import api_config as api
import harness as H
from harness import Fail

GROUP = "license"
GROUP_DOC = ("Licensing (Apache-2.0 headers, florilegium MIT "
             "notices, NOTICE) and README Algorithms & References (feature 33)")


def _read(path):
  with open(path, encoding="utf-8", errors="replace") as f:
    return f.read()


def own_sources(repo, category):
  out = []
  for pat in api.OWN_SOURCE_GLOBS[category]:
    for p in sorted(glob.glob(os.path.join(repo, pat))):
      if os.path.isfile(p) and "__pycache__" not in p:
        out.append(p)
  return out


def notice_text(repo):
  for n in api.NOTICE_FILES:
    p = os.path.join(repo, n)
    if os.path.exists(p):
      return n, _read(p)
  raise Fail("no NOTICE file (looked for %s)" % ", ".join(api.NOTICE_FILES))


def readme_algo_section(repo):
  p = os.path.join(repo, "README.md")
  if not os.path.exists(p):
    raise Fail("README.md missing")
  text = _read(p)
  m = re.search(api.README_ALGO_HEADING, text, re.M | re.I)
  if not m:
    raise Fail("README has no '## Algorithms & References' section")
  level = len(re.match(r"#+", m.group(0)).group(0))
  rest = text[m.end():]
  nxt = re.search(r"^#{1,%d}\s" % level, rest, re.M)
  return rest[:nxt.start()] if nxt else rest


def algo_block(path):
  """Text of the `ALGORITHMS & REFERENCES:` comment block of a source file
  (comment prefix stripped), or None when the file has no such block."""
  lines = _read(path).splitlines()
  for i, line in enumerate(lines):
    if api.ALGO_BLOCK_MARKER in line:
      out = []
      for l in lines[i + 1:]:
        m = re.match(r"^\s*(--+|%+|#+)(.*)$", l)
        if not m or not m.group(2).strip():
          break
        out.append(m.group(2).strip())
      return " ".join(out)
  return None


_KNOWN_AUTHORS = re.compile(
    r"\b(Runions|Shinozaki|Prusinkiewicz|Wong|Curtis|Ottosson|Raymond|Ettinger)\b")


def citations(block):
  """Known primary algorithm author surnames cited in an ALGORITHMS block."""
  seen, out = set(), []
  for m in _KNOWN_AUTHORS.finditer(block or ""):
    k = m.group(1)
    if k not in seen:
      seen.add(k)
      out.append(k)
  return out


def is_florilegium_adapted(text):
  if "florilegium" not in text.lower():
    return False
  head = text[:api.HEADER_SCAN_CHARS]
  if (re.search(r"no\b[^.\n;]*\b(copied|florilegium)\b[^.\n;]*\b(florilegium|copied)",
                head, re.I)
      and not re.search(r"adapted\s+(?:from|via)\s+florilegium", head, re.I)):
    return False
  return True


def algo_modules(repo):
  mods = []
  for p in sorted(glob.glob(os.path.join(repo, "tex", "kacho*.lua"))):
    if algo_block(p) is not None:
      mods.append(p)
  return mods


def register(add, repo):
  def lic_apache(ctx):
    p = os.path.join(ctx.repo, "LICENSE")
    if not os.path.exists(p):
      raise Fail("LICENSE missing")
    t = _read(p)
    miss = [k for k in api.LICENSE_MARKERS + [api.COPYRIGHT_LINE]
            if k not in t]
    if miss:
      raise Fail("LICENSE missing %s markers: %s" % (api.LICENSE_ID, miss))
  add("t1.license.license_apache2", "1", GROUP, lic_apache, quick=True,
      doc="LICENSE uses Apache License 2.0 with Copyright 2026")

  def lic_copyright(ctx):
    p = os.path.join(ctx.repo, "LICENSE")
    if not os.path.exists(p):
      raise Fail("LICENSE missing")
    if api.COPYRIGHT_LINE not in _read(p):
      raise Fail("LICENSE lacks %r" % api.COPYRIGHT_LINE)
  add("t1.license.license_copyright", "1", GROUP, lic_copyright,
      doc="LICENSE carries 'Copyright 2026'")

  for cat in api.OWN_SOURCE_GLOBS:
    def hdr(ctx, cat=cat):
      files = own_sources(ctx.repo, cat)
      if not files:
        raise Fail("no files for %s (%s)" % (cat, api.OWN_SOURCE_GLOBS[cat]))
      bad = []
      for f in files:
        head = _read(f)[:api.HEADER_SCAN_CHARS]
        why = []
        if api.COPYRIGHT_LINE not in head:
          why.append("no '%s'" % api.COPYRIGHT_LINE)
        if not re.search(api.APACHE_HEADER_RE, head):
          why.append("no Apache-2.0 notice")
        if why:
          bad.append("%s (%s)" % (os.path.relpath(f, ctx.repo),
                                  ", ".join(why)))
      if bad:
        raise Fail("%d/%d file(s) without the Apache-2.0 header: %s" % (
            len(bad), len(files), "; ".join(bad[:6])))
      return "%d file(s)" % len(files)
    add("t1.license.apache_header[%s]" % cat, "1", GROUP, hdr,
        quick=cat == "tex-lua",
        doc="every %s source starts with the Apache-2.0 header" % cat)

  def keep_mit(ctx):
    files = [f for cat in ("tex-sty", "tex-lua") for f in
             own_sources(ctx.repo, cat)]
    adapted = [f for f in files if is_florilegium_adapted(_read(f))]
    bad = []
    for f in adapted:
      head = _read(f)[:api.HEADER_SCAN_CHARS]
      if not ("MIT" in head and ("Kevin Raymond" in head or
                                 "NOTICE" in head.upper())):
        bad.append(os.path.basename(f))
    if bad:
      raise Fail("florilegium-mentioning files missing MIT attribution: %s" %
                 bad[:5])
    return "%d adapted file(s) keep the MIT attribution" % len(adapted)
  add("t1.license.adapted_files_keep_mit", "1", GROUP, keep_mit, quick=True,
      doc="tex/ files mentioning florilegium retain their MIT attribution")

  def no_stale(ctx):
    bad = []
    for cat in api.OWN_SOURCE_GLOBS:
      for f in own_sources(ctx.repo, cat):
        if re.search(r"License:\s*MIT\b", _read(f)[:api.HEADER_SCAN_CHARS]):
          bad.append(os.path.relpath(f, ctx.repo))
    if bad:
      raise Fail("own sources still declare 'License: MIT': %s" % bad)
  add("t1.license.no_stale_mit_project_claim", "1", GROUP, no_stale,
      doc="no own source still declares the project 'License: MIT'")

  def notice(ctx):
    name, t = notice_text(ctx.repo)
    miss = [k for k in ["florilegium", "Kevin Raymond"] +
            api.MIT_NOTICE_MARKERS if k not in t]
    if miss:
      raise Fail("%s lacks %s" % (name, miss))
  add("t1.license.notice_florilegium_mit", "1", GROUP, notice, quick=True,
      doc="NOTICE credits florilegium (MIT, Kevin Raymond) with its text")

  def notice_files(ctx):
    name, t = notice_text(ctx.repo)
    files = [f for f in own_sources(ctx.repo, "tex-lua")
             if re.search(api.ADAPTED_RE, _read(f), re.I)]
    miss = [os.path.basename(f) for f in files
            if os.path.splitext(os.path.basename(f))[0] not in t]
    if miss:
      raise Fail("%s does not name adapted file(s) %s" % (name, miss))
    return "%d adapted file(s) named" % len(files)
  add("t1.license.notice_names_adapted_files", "1", GROUP, notice_files,
      doc="NOTICE lists every florilegium-adapted Lua source file")

  def readme_section(ctx):
    sec = readme_algo_section(ctx.repo)
    if len(sec.strip()) < 200:
      raise Fail("Algorithms & References section is nearly empty (%d chars)"
                 % len(sec.strip()))
    checks = [
        ("space colonization / Runions", r"space\s+coloni[sz]ation|Runions"),
        ("pipe model / Shinozaki / da Vinci", r"pipe\s+model|Shinozaki|da\s+Vinci"),
        ("Prusinkiewicz / L-systems", r"Prusinkiewicz|L-system"),
        ("Wong 1998", r"Wong"),
        ("florilegium", r"florilegium"),
        ("tikz-flora", r"tikz-flora"),
        ("adapted from / inspired by", r"adapted\s+from|inspired\s+by"),
    ]
    full = _read(os.path.join(ctx.repo, "README.md"))
    miss = [label for label, rx in checks
            if not (re.search(rx, sec, re.I) or re.search(rx, full, re.I))]
    if miss:
      raise Fail("README Algorithms & References missing: %s" % miss)
    unlisted = []
    for p in algo_modules(ctx.repo):
      base = os.path.basename(p)
      stem = os.path.splitext(base)[0]
      if base not in full and stem not in full:
        unlisted.append(base)
    if unlisted:
      raise Fail("tex/kacho*.lua with %s not referenced in README: %s" % (
          api.ALGO_BLOCK_MARKER, unlisted))
  add("t1.license.readme_algorithms_section", "1", GROUP, readme_section,
      quick=True, doc="README has a complete 'Algorithms & References' "
      "section with core citations and adapted/inspired notes")

  def readme_files_exist(ctx):
    sec = readme_algo_section(ctx.repo)
    refs = sorted(set(re.findall(r"\b(kacho[\w-]*\.(?:lua|sty))\b", sec)))
    if not refs:
      raise Fail("Algorithms section names no implementing file "
                 "(kacho-*.lua)")
    miss = [r for r in refs if not os.path.exists(
        os.path.join(ctx.repo, "tex", r))]
    if miss:
      raise Fail("Algorithms section cites missing file(s): %s" % miss)
    return ", ".join(refs)
  add("t1.license.readme_algorithms_files_exist", "1", GROUP,
      readme_files_exist,
      doc="files named in the Algorithms section exist under tex/")

  for mod_file in api.ALGO_REQUIRED_MODULES:
    stem = os.path.splitext(mod_file)[0]

    def mod(ctx, stem=stem, mod_file=mod_file):
      p = os.path.join(ctx.repo, "tex", mod_file)
      if not os.path.exists(p):
        raise Fail("module %s missing under tex/" % mod_file)
      blk = algo_block(p)
      if blk is None:
        raise Fail("%s has no '%s' header block" % (
            mod_file, api.ALGO_BLOCK_MARKER))
      sec = readme_algo_section(ctx.repo)
      full = _read(os.path.join(ctx.repo, "README.md"))
      problems = []
      if stem not in sec and stem not in full:
        problems.append("module %s not named" % stem)
      for author in citations(blk):
        if author not in sec and author not in full:
          problems.append("citation %s missing" % author)
      if problems:
        raise Fail("README Algorithms section vs %s header: %s" % (
            mod_file, "; ".join(problems[:6])))
      return "%d citation(s)" % len(citations(blk))
    add("t1.license.algorithms_documented[%s]" % stem, "1", GROUP, mod,
        quick=stem == "kacho-growth",
        doc="README lists %s and every citation in its ALGORITHMS block" %
        stem)
