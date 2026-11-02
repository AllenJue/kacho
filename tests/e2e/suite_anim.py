"""Feature 31 (optional animated demo) tests for the kacho E2E suite.

Source: ORIGINAL_REQUEST follow-up 2026-11-02T00:13:20Z / PROJECT.md feature
31: a separate examples/animated/ document using the `animate` package with
Lua-generated frames, its own `make animated` + `make view-animated`, README
lists viewers that play it, frames reviewed visually; must not break the
static build; no embedded images (R1).

The group is OPTIONAL: while api.ANIM_DIR does not exist the tests are
registered as advisory (WARN, never failing the run). Once the directory
exists they become blocking tier-1 tests.
"""

import glob
import os
import re

import api_config as api
import harness as H
from harness import Fail

GROUP = "animated"
GROUP_DOC = ("Optional animated demo: make animated, animate widgets, Form "
             "XObjects, no images, reproducibility, frames-as-pages safety "
             "(feature 31; advisory until examples/animated exists)")


def anim_sources(repo):
  return sorted(glob.glob(os.path.join(repo, api.ANIM_DIR, "*.tex")))


def _need_present(ctx):
  if not os.path.isdir(os.path.join(ctx.repo, api.ANIM_DIR)):
    raise Fail("optional feature not present: %s/ does not exist" %
               api.ANIM_DIR)
  if not anim_sources(ctx.repo):
    raise Fail("no .tex document in %s/" % api.ANIM_DIR)


def make_animated(ctx):
  """Runs `make animated` once in a private copy; returns (rc, out, pdfs)."""
  def _do():
    _need_present(ctx)
    _, d = H.private_copy(ctx, "animated")
    before = set(glob.glob(os.path.join(d, "**", "*.pdf"), recursive=True))
    rc, out = H.run(["make", api.ANIM_MAKE_TARGET], cwd=d,
                    env=ctx.plain_env(), timeout=2400)
    after = set(glob.glob(os.path.join(d, "**", "*.pdf"), recursive=True))
    stems = {os.path.splitext(os.path.basename(p))[0]
             for p in anim_sources(ctx.repo)}
    pdfs = sorted(p for p in after - before
                  if os.path.splitext(os.path.basename(p))[0] in stems)
    return rc, out, pdfs
  return ctx.memo(("make_animated",), _do)


def need_anim_pdfs(ctx):
  rc, out, pdfs = make_animated(ctx)
  if rc != 0:
    raise Fail("make %s rc=%d: %s" % (api.ANIM_MAKE_TARGET, rc,
                                      out.strip()[-300:]))
  if not pdfs:
    raise Fail("make %s produced no PDF named after %s/*.tex" % (
        api.ANIM_MAKE_TARGET, api.ANIM_DIR))
  return pdfs


def register(add, repo):
  present = os.path.isdir(os.path.join(repo, api.ANIM_DIR))
  tier = "1" if present else "adv"
  adv = not present
  pre = "t1" if present else "adv"

  def build(ctx):
    pdfs = need_anim_pdfs(ctx)
    return ", ".join("%s: %d page(s)" % (os.path.basename(p),
                                         len(H.page_sizes(p))) for p in pdfs)
  add("%s.animated.make_animated" % pre, tier, GROUP, build, advisory=adv,
      quick=present, doc="`make animated` builds the animated demo PDF(s)")

  def form_xobjs(ctx):
    bad = []
    counts = []
    for p in need_anim_pdfs(ctx):
      data = H.pdf_all_bytes(p)
      n = len(re.findall(rb"/Subtype\s*/Form\b", data))
      counts.append("%s: %d" % (os.path.basename(p), n))
      if n < 2:
        bad.append("%s (%d /Subtype /Form)" % (os.path.basename(p), n))
    if bad:
      raise Fail("animated PDF lacks multiple /Subtype /Form frame XObjects: "
                 "%s" % "; ".join(bad))
    return ", ".join(counts)
  add("%s.animated.form_xobjects" % pre, tier, GROUP, form_xobjs,
      advisory=adv,
      doc="animated PDF contains multiple /Subtype /Form XObjects (frames)")

  def widgets(ctx):
    bad = []
    for p in need_anim_pdfs(ctx):
      data = H.pdf_all_bytes(p)
      has = [m.decode() for m in api.ANIM_PDF_MARKERS if re.search(m, data)]
      if b"/JavaScript" not in data or len(has) < 2:
        bad.append("%s (markers found: %s)" % (os.path.basename(p), has))
    if bad:
      raise Fail("no animate-package animation structure (JavaScript + "
                 "/AA or OCGs): %s" % "; ".join(bad))
  add("%s.animated.pdf_has_animation" % pre, tier, GROUP, widgets,
      advisory=adv,
      doc="animated PDF carries animate widgets (JavaScript + /AA or OCG)")

  def noimg(ctx):
    for p in need_anim_pdfs(ctx):
      rows = H.pdf_images(p)
      if rows:
        raise Fail("%s embeds %d image(s): %s" % (os.path.basename(p),
                                                  len(rows), rows[0]))
  add("%s.animated.no_image_xobjects" % pre, tier, GROUP, noimg, advisory=adv,
      doc="animated PDF contains no image XObjects (frames are vector)")

  def repro(ctx):
    _need_present(ctx)
    for src in anim_sources(ctx.repo):
      a = H.compile_doc(ctx, src, rep=1, timeout=2400,
                        extra_texinputs=[os.path.dirname(src) + "//"],
                        tag="anim-rep1-" + os.path.basename(src)[:-4])
      b = H.compile_doc(ctx, src, rep=2, timeout=2400,
                        extra_texinputs=[os.path.dirname(src) + "//"],
                        tag="anim-rep2-" + os.path.basename(src)[:-4])
      diff = H.renders_equal(ctx, a, b)
      if diff:
        raise Fail("%s not reproducible with SOURCE_DATE_EPOCH on pages %s" %
                   (os.path.basename(src), diff))
  add("%s.animated.reproducible" % pre, tier, GROUP, repro, advisory=adv,
      doc="animated PDF is reproducible across builds with SOURCE_DATE_EPOCH")

  def frames(ctx):
    _need_present(ctx)
    out = []
    for src in anim_sources(ctx.repo):
      r = H.compile_doc(ctx, src, env=api.ANIM_FRAMES_ENV,
                        defs=r"\def\kachoAnimFrames{1}\def\framespages{1}",
                        timeout=2400,
                        extra_texinputs=[os.path.dirname(src) + "//"],
                        tag="anim-frames-" + os.path.basename(src)[:-4])
      H.need_ok(r)
      if r.elems:
        H.check_log_text_overlap(r)
        H.check_log_edge(r)
      out.append("%s: %d page(s)" % (os.path.basename(src), r.pages))
    return ", ".join(out)
  add("%s.animated.frames_debug_safe" % pre, tier, GROUP, frames,
      advisory=adv,
      doc="frames-as-pages debug build compiles and passes overlap/edge")

  def view_target(ctx):
    _need_present(ctx)
    rc, out = H.run(["make", "-n", api.ANIM_VIEW_TARGET], cwd=ctx.repo,
                    env=ctx.plain_env(), timeout=60)
    if rc != 0:
      raise Fail("make -n %s rc=%d: %s" % (api.ANIM_VIEW_TARGET, rc,
                                           out.strip()[-200:]))
  add("%s.animated.view_target" % pre, tier, GROUP, view_target, advisory=adv,
      doc="Makefile defines `make view-animated`")

  def readme(ctx):
    _need_present(ctx)
    p = os.path.join(ctx.repo, "README.md")
    if not os.path.exists(p):
      raise Fail("README.md missing")
    t = open(p, encoding="utf-8", errors="replace").read()
    miss = []
    if "make %s" % api.ANIM_MAKE_TARGET not in t:
      miss.append("`make %s`" % api.ANIM_MAKE_TARGET)
    if not re.search(api.ANIM_VIEWERS, t):
      miss.append("a viewer that plays animations (%s)" % api.ANIM_VIEWERS)
    if miss:
      raise Fail("README lacks %s" % ", ".join(miss))
  add("%s.animated.readme_viewers" % pre, tier, GROUP, readme, advisory=adv,
      doc="README documents `make animated` and which viewers play it")

  def static_ok(ctx):
    _need_present(ctx)
    co = H.need_checkout(ctx)
    bad = [s for s in co.examples if co.pdfs.get(s) is None]
    if bad:
      raise Fail("static `make` lost example PDFs: %s" % bad)
    if any(os.path.dirname(p).endswith(api.ANIM_DIR) for p in
           glob.glob(os.path.join(co.dir, "examples", "*.tex"))):
      raise Fail("animated sources leak into the static examples glob")
  add("%s.animated.static_build_unaffected" % pre, tier, GROUP, static_ok,
      advisory=adv, doc="static `make` still builds every example")
