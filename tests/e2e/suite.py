"""Test registry for the kacho E2E suite.

Each test is a function taking the run Ctx and raising harness.Fail on
failure (returning an optional info string on success). Tests are grouped
into feature groups (see TEST_INFRA.md) and tiers:

  tier 1  — per-feature tests (incl. acceptance checks: build, view,
            no-images, overlap, edge, determinism, ...)
  tier 2  — boundary scenarios (paper sizes, margins, columns, lengths, ...)
  tier 3  — pairwise combinations palette x theme x layout x paper
  tier 4  — realistic documents
  adv     — advisory heuristics (reported as WARN, never fail the run)
"""

import dataclasses
import glob
import os
import re
import shutil
import threading

import api_config as api
import harness as H
from harness import Fail
import suite_anim
import suite_license
import suite_place


@dataclasses.dataclass
class Test:
  name: str
  tier: str  # "1", "2", "3", "4", "adv"
  group: str
  fn: object
  quick: bool = False
  advisory: bool = False
  doc: str = ""


GROUPS = {
    "build": "Compile command / clean-checkout build of examples (R2, AC Build)",
    "view": "View & render commands, headless (R2, AC Build)",
    "noimg": "Procedural only: no image files, no \\includegraphics, no image XObjects (AC Procedural)",
    "overlap": "No decoration over body text: pixel diff + debug-log bbox (AC Visual)",
    "edge": "No motif clipped at page edge: 5 mm safe zone (AC Visual)",
    "det": "Seeded RNG determinism & per-page stream isolation (feature 4)",
    "palette": "Palettes sumi / hanga (feature 8)",
    "theme": "Seasonal themes haru/natsu/aki/fuyu/shochikubai (feature 25)",
    "layout": "Layout variants corner-spray/margin-column/header-garland/footer-ground/scattered-petals (feature 23)",
    "control": "Options & per-page control: off, debug, density, \\kachosetup, \\kachoOff/On, \\kachoThisPage (features 2,3)",
    "title": "Title / showcase pages: kakejiku \\kachoTitlePage, shikishi opener (feature 24)",
    "motif": "Motif library: flora, birds, seal, scenery present & sane (features 12-22)",
    "docs": "README / LICENSE / NOTICE / Algorithms & References attribution (features 27, 33, AC Licensing)",
    "place": suite_place.GROUP_DOC,
    "license": suite_license.GROUP_DOC,
    "animated": suite_anim.GROUP_DOC,
}

TESTS = []


def test(name, tier, group, quick=False, advisory=False):
  def deco(fn):
    TESTS.append(Test(name, tier, group, fn, quick, advisory,
                      (fn.__doc__ or "").strip().splitlines()[0]
                      if fn.__doc__ else ""))
    return fn
  return deco


def add(name, tier, group, fn, quick=False, advisory=False, doc=""):
  TESTS.append(Test(name, tier, group, fn, quick, advisory, doc))


BASE = "base_article.tex"
TITLE_DEFS = r"\def\KachoTitleCmd{%s}" % api.TITLE_PAGE_CMD
OPENER_DEFS = r"\def\KachoOpenerCmd{%s}" % api.SHIKISHI_CMD


def C(ctx, fixture=BASE, **kw):
  return H.compile_doc(ctx, fixture, **kw)


def on_off(ctx, fixture=BASE, pkg_opts="", class_opts="", geom_opts="",
           defs=""):
  on = C(ctx, fixture, pkg_opts=pkg_opts, class_opts=class_opts,
         geom_opts=geom_opts, defs=defs)
  off = C(ctx, fixture, pkg_opts=pkg_opts, class_opts=class_opts,
          geom_opts=geom_opts, defs=defs, off=True)
  return on, off


def read(path):
  with open(path, encoding="utf-8", errors="replace") as f:
    return f.read()


def strip_tex_comments(src):
  return "\n".join(re.sub(r"(?<!\\)%.*", "", l) for l in src.splitlines())


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".eps", ".pdf", ".webp",
             ".tif", ".tiff", ".bmp", ".ps", ".jp2", ".avif", ".heic")
SKIP_DIRS = {"build", ".agents", ".git", "__pycache__"}


def repo_files(ctx, sub=""):
  root = os.path.join(ctx.repo, sub)
  out = []
  for r, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    out += [os.path.join(r, f) for f in files]
  return out


# ===========================================================================
# Group: build
# ===========================================================================
@test("t1.build.clean_checkout_make", "1", "build", quick=True)
def _(ctx):
  """`make` succeeds in a clean copy of the repo (no TinyTeX on PATH)."""
  co = H.need_checkout(ctx)
  return "built in %s" % co.dir


@test("t1.build.no_tex_errors", "1", "build", quick=True)
def _(ctx):
  """No '!' error lines in make output or any example log."""
  co = H.need_checkout(ctx)
  errs = H.tex_errors(co.output)
  for s, lg in co.logs.items():
    errs += ["%s: %s" % (s, e) for e in H.tex_errors(lg)]
  if errs:
    raise Fail("%d TeX error(s): %s" % (len(errs), errs[0]))


@test("t1.build.examples_present", "1", "build", quick=True)
def _(ctx):
  """examples/ has >=3 documents incl. showcase, gallery and article."""
  stems = H.example_stems(ctx)
  missing = [k for k in ("showcase", "gallery", "article")
             if not any(k in s for s in stems)]
  if len(stems) < 3 or missing:
    raise Fail("examples found: %s; missing kinds: %s" % (stems, missing))


@test("t1.build.makefile_targets", "1", "build")
def _(ctx):
  """Makefile defines all, view, render, test, clean (make -n succeeds)."""
  mk = os.path.join(ctx.repo, "Makefile")
  if not os.path.exists(mk):
    raise Fail("no Makefile")
  bad = []
  for t in ("all", "view", "render", "test", "clean"):
    rc, out = H.run(["make", "-n", t], cwd=ctx.repo, env=ctx.plain_env(),
                    timeout=60)
    if rc != 0:
      bad.append("%s (%s)" % (t, out.strip().splitlines()[-1:]))
  if bad:
    raise Fail("make -n failed for: %s" % ", ".join(bad))


@test("t1.build.clean_then_rebuild", "1", "build")
def _(ctx):
  """`make clean` removes PDFs, and a second `make` rebuilds them."""
  co, d = H.private_copy(ctx, "clean")
  rc, out = H.run(["make", "clean"], cwd=d, env=ctx.plain_env(), timeout=300)
  if rc != 0:
    raise Fail("make clean rc=%d: %s" % (rc, out[-300:]))
  left = glob.glob(os.path.join(d, "build", "**", "*.pdf"), recursive=True)
  left += glob.glob(os.path.join(d, "examples", "*.pdf"))
  if left:
    raise Fail("PDFs remain after make clean: %s" % left[:3])
  rc, out = H.run(["make"], cwd=d, env=ctx.plain_env(), timeout=2400)
  if rc != 0:
    raise Fail("rebuild after clean failed rc=%d" % rc)
  for s in co.examples:
    if not (os.path.exists(os.path.join(d, "build", s + ".pdf")) or
            H.find_file(d, s + ".pdf")):
      raise Fail("rebuild did not produce %s.pdf" % s)


def _register_example_tests(ctx_repo):
  stems = sorted(os.path.splitext(os.path.basename(p))[0] for p in
                 glob.glob(os.path.join(ctx_repo, "examples", "*.tex")))
  if not stems:
    stems = ["<none>"]
  for i, s in enumerate(stems):
    q = i == 0

    def mk_pdf(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples/*.tex in repository")
        co = H.need_checkout(ctx)
        p = co.pdfs.get(s)
        if not p:
          raise Fail("make produced no PDF for examples/%s.tex" % s)
        n = len(H.page_sizes(p))
        if n < 1:
          raise Fail("PDF unreadable / zero pages: %s" % p)
        return "%d page(s)" % n
      return f
    add("t1.build.example_pdf[%s]" % s, "1", "build", mk_pdf(), quick=True,
        doc="make builds a valid PDF for this example")

    def mk_qq(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        co = H.need_checkout(ctx)
        p = co.pdfs.get(s)
        if not p:
          raise Fail("no PDF")
        q, qq = H.qQ_balance(p)
        if q != qq:
          raise Fail("unbalanced graphics state: %d q vs %d Q" % (q, qq))
        return "%d q/Q pairs" % q
      return f
    add("t1.build.qQ_balanced[%s]" % s, "1", "build", mk_qq(),
        doc="PDF content streams have balanced q/Q")

    def mk_noimg(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        co = H.need_checkout(ctx)
        p = co.pdfs.get(s)
        if not p:
          raise Fail("no PDF")
        rows = H.pdf_images(p)
        if rows:
          raise Fail("%d image(s) embedded: %s" % (len(rows), rows[0]))
      return f
    add("t1.noimg.pdf_no_images[%s]" % s, "1", "noimg", mk_noimg(), quick=q,
        doc="example PDF contains no raster image XObjects")

    def mk_pix(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        on = H.compile_example(ctx, s)
        off = H.compile_example(ctx, s, off=True)
        H.check_overlap_pixels(ctx, on, off, max_pages=40)
      return f
    add("t1.overlap.pixel[%s]" % s, "1", "overlap", mk_pix(), quick=q,
        doc="decoration leaves body-text word boxes untouched (on vs off)")

    def mk_logov(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        H.check_log_text_overlap(H.compile_example(ctx, s))
      return f
    add("t1.overlap.log[%s]" % s, "1", "overlap", mk_logov(), quick=q,
        doc="debug-log elem bboxes do not intersect the text block")

    def mk_edge(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        H.check_log_edge(H.compile_example(ctx, s))
      return f
    add("t1.edge.log[%s]" % s, "1", "edge", mk_edge(), quick=q,
        doc="debug-log elem bboxes keep 5 mm from the paper edge")

    def mk_ring(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        co = H.need_checkout(ctx)
        p = co.pdfs.get(s)
        if not p:
          raise Fail("no PDF")
        marks = H.edge_ring_marks(ctx, p)
        hot = {pg: c for pg, (c, t) in marks.items() if c > 0.03 * t}
        if hot:
          raise Fail("pages with ink in outer 2 mm ring (>3%% of ring): %s" %
                     ", ".join("p%d:%d px" % kv for kv in sorted(hot.items())))
      return f
    add("adv.edge.ring[%s]" % s, "adv", "edge", mk_ring(), advisory=True,
        doc="little ink in the outermost 2 mm ring (only deliberate trunks)")

    def mk_band(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        co = H.need_checkout(ctx)
        p = co.pdfs.get(s)
        if not p:
          raise Fail("no PDF")
        hits = {}
        for pg, img in enumerate(H.render(ctx, p, 72, gray=True), 1):
          n = H.banding_lines(img)
          if n:
            hits[pg] = n
        if hits:
          raise Fail("possible banding lines: %s" % ", ".join(
              "p%d:%d" % kv for kv in sorted(hits.items())))
      return f
    add("adv.wash.banding[%s]" % s, "adv", "overlap", mk_band(),
        advisory=True, doc="no long straight iso-step lines in washes")

    def mk_buf(s=s):
      def f(ctx):
        if s == "<none>":
          raise Fail("no examples")
        H.check_log_text_overlap(H.compile_example(ctx, s),
                                 buffer_bp=3.5 * H.MM)
      return f
    add("adv.overlap.buffer4mm[%s]" % s, "adv", "overlap", mk_buf(),
        advisory=True, doc="elems keep ~4 mm buffer from text block")

  # determinism on the first example
  def ex_det(ctx):
    if stems[0] == "<none>":
      raise Fail("no examples")
    a = H.compile_example(ctx, stems[0], rep=1)
    b = H.compile_example(ctx, stems[0], rep=2)
    diff = H.renders_equal(ctx, a, b)
    if diff:
      raise Fail("two builds of %s render differently on pages %s" % (
          stems[0], diff[:6]))
  add("t1.det.example_reproducible", "1", "det", ex_det,
      doc="building the first example twice gives identical renders")

  # motif presence over union of example debug logs
  def kinds_all(ctx):
    kinds = set()
    for s in stems:
      if s == "<none>":
        continue
      r = H.compile_example(ctx, s)
      if r.ok:
        kinds |= {e.kind for e in r.elems}
    return kinds

  for mname, rx in api.MOTIF_KINDS.items():
    def mk(rx=rx, mname=mname):
      def f(ctx):
        if stems[0] == "<none>":
          raise Fail("no examples")
        kinds = kinds_all(ctx)
        if not kinds:
          raise Fail("no debug-log elems from any example")
        hit = sorted(k for k in kinds if re.search(rx, k, re.I))
        if not hit:
          raise Fail("no elem kind matching /%s/ in examples; kinds seen: %s"
                     % (rx, sorted(kinds)[:20]))
        return ", ".join(hit[:5])
      return f
    add("t1.motif.present[%s]" % mname, "1", "motif", mk(),
        quick=mname == "ume", doc="examples draw the %s motif" % mname)

  def bonus(ctx):
    kinds = kinds_all(ctx)
    found = [n for n, rx in api.BONUS_FLORA.items()
             if any(re.search(rx, k, re.I) for k in kinds)]
    if len(found) < 2:
      raise Fail("need >=2 bonus flora of %s; found %s" % (
          list(api.BONUS_FLORA), found))
    return ", ".join(found)
  add("t1.motif.bonus_flora", "1", "motif", bonus,
      doc=">=2 of osmanthus/narcissus/chrysanthemum/pine/camellia")

  def birds_perched(ctx):
    bad, n = [], 0
    for s in stems:
      if s == "<none>":
        raise Fail("no examples")
      r = H.compile_example(ctx, s)
      H.need_elems(r)
      for e in r.elems:
        if re.search(api.MOTIF_KINDS["bird"], e.kind, re.I):
          n += 1
          branches = [b for b in r.elems if b.page == e.page and b is not e
                      and re.search(api.BRANCH_KIND, b.kind, re.I) and
                      not re.search(api.MOTIF_KINDS["bird"], b.kind, re.I)]
          if not any(min(H._inter(e.bbox, b.bbox)) >= 0 for b in branches):
            bad.append("%s p%d %s" % (s, e.page, e.kind))
    if n == 0:
      raise Fail("no bird elems in examples")
    if bad:
      raise Fail("bird(s) not touching any branch bbox: %s" % bad[:4])
  add("t1.motif.birds_perched", "1", "motif", birds_perched,
      doc="every bird bbox touches a branch bbox on its page (no floating)")

  def seal_size(ctx):
    bad = []
    for s in stems:
      r = H.compile_example(ctx, s)
      H.need_elems(r)
      sizes = H.page_sizes(r.pdf)
      per_page = {}
      for e in r.elems:
        if re.search(api.MOTIF_KINDS["seal"], e.kind, re.I):
          per_page[e.page] = per_page.get(e.page, 0) + 1
          ph = sizes[e.page - 1][1]
          hgt = e.bbox[3] - e.bbox[1]
          if not ph / 80 <= hgt <= ph / 10:
            bad.append("%s p%d seal h=%.1f (page h %.0f)" % (s, e.page, hgt,
                                                             ph))
      bad += ["%s p%d has %d seals" % (s, p, c) for p, c in per_page.items()
              if c > 2]
    if bad:
      raise Fail("; ".join(bad[:5]))
  add("adv.motif.seal_size", "adv", "motif", seal_size, advisory=True,
      doc="seal ~1/30 page height, <=2 per page (survey_2 §4.5 rule 6)")


# ===========================================================================
# Group: view
# ===========================================================================
def _make_view(ctx, env, tag):
  """Runs `make view` in a private copy; returns (copy_dir, rc, output)."""
  _, d = H.private_copy(ctx, "view-" + tag)
  rc, out = H.run(["make", "view"], cwd=d, env=env, timeout=600)
  return d, rc, out


def _paths_in(text, root):
  found = []
  for m in re.finditer(r"([\w./~+-]+\.(?:pdf|png))", text):
    p = m.group(1)
    cand = p if os.path.isabs(p) else os.path.join(root, p)
    if os.path.exists(cand):
      found.append(cand)
  return found


@test("t1.view.headless_make_view", "1", "view", quick=True)
def _(ctx):
  """`make view` exits 0 with no DISPLAY and no VIEWER (headless fallback)."""
  _, rc, out = _make_view(ctx, ctx.plain_env(), "headless")
  if rc != 0:
    raise Fail("make view rc=%d: %s" % (rc, out.strip()[-300:]))


@test("t1.view.prints_existing_path", "1", "view")
def _(ctx):
  """headless `make view` reports an existing PDF or PNG path."""
  d, rc, out = _make_view(ctx, ctx.plain_env(), "paths")
  if not _paths_in(out, d):
    raise Fail("no existing .pdf/.png path in output: %s" % out.strip()[-300:])


@test("t1.view.viewer_env_respected", "1", "view")
def _(ctx):
  """With VIEWER=<cmd>, `make view` invokes it on an existing PDF."""
  rec = os.path.join(ctx.run_dir, "viewer_calls.txt")
  sh = os.path.join(ctx.run_dir, "fakeviewer.sh")
  with open(sh, "w") as f:
    f.write("#!/bin/sh\nfor a in \"$@\"; do echo \"$PWD|$a\" >> %s; done\n"
            "exit 0\n" % rec)
  os.chmod(sh, 0o755)
  if os.path.exists(rec):
    os.remove(rec)
  env = ctx.plain_env()
  env["VIEWER"] = sh
  _, rc, out = _make_view(ctx, env, "viewer")
  if rc != 0:
    raise Fail("make view (VIEWER set) rc=%d: %s" % (rc, out[-300:]))
  if not os.path.exists(rec):
    raise Fail("VIEWER was not invoked; output: %s" % out.strip()[-200:])
  ok = False
  for line in read(rec).splitlines():
    cwd, a = line.split("|", 1)
    p = a if os.path.isabs(a) else os.path.join(cwd, a)
    if a.endswith(".pdf") and os.path.exists(p):
      ok = True
  if not ok:
    raise Fail("VIEWER not called with an existing PDF: %s" % read(rec)[:200])


def _render_out(ctx):
  def _do():
    co, d = H.private_copy(ctx, "render")
    before = set(glob.glob(os.path.join(d, "**", "*.png"), recursive=True))
    rc, out = H.run(["make", "render"], cwd=d, env=ctx.plain_env(),
                    timeout=1200)
    pngs = sorted(set(glob.glob(os.path.join(d, "**", "*.png"),
                                recursive=True)) - before)
    return co, rc, out, pngs
  return ctx.memo(("render_out",), _do)


@test("t1.view.make_render_png_per_page", "1", "view", quick=True)
def _(ctx):
  """`make render` writes at least one PNG per page of every example PDF."""
  co, rc, out, pngs = _render_out(ctx)
  if rc != 0:
    raise Fail("make render rc=%d: %s" % (rc, out.strip()[-300:]))
  pages = sum(len(H.page_sizes(p)) for p in co.pdfs.values() if p)
  if len(pngs) < pages:
    raise Fail("%d PNGs for %d pages" % (len(pngs), pages))
  return "%d PNGs / %d pages" % (len(pngs), pages)


@test("t1.view.render_pngs_valid", "1", "view")
def _(ctx):
  """rendered PNGs are valid, non-trivial PNG files."""
  co, rc, out, pngs = _render_out(ctx)
  if rc != 0 or not pngs:
    raise Fail("make render produced no PNGs (rc=%d)" % rc)
  for p in pngs:
    with open(p, "rb") as f:
      head = f.read(8)
    if head != b"\x89PNG\r\n\x1a\n" or os.path.getsize(p) < 1000:
      raise Fail("invalid/tiny PNG: %s" % p)


@test("t1.view.scripts_present", "1", "view")
def _(ctx):
  """scripts/view.sh and scripts/render.sh exist and are executable."""
  bad = [s for s in ("scripts/view.sh", "scripts/render.sh")
         if not os.access(os.path.join(ctx.repo, s), os.X_OK)]
  if bad:
    raise Fail("missing or not executable: %s" % bad)


# ===========================================================================
# Group: noimg
# ===========================================================================
@test("t1.noimg.no_image_files_in_tree", "1", "noimg", quick=True)
def _(ctx):
  """No image files anywhere in the repo (outside build/, .agents, .git)."""
  bad = [os.path.relpath(f, ctx.repo) for f in repo_files(ctx)
         if f.lower().endswith(IMAGE_EXT)]
  if bad:
    raise Fail("image files present: %s" % bad[:10])


@test("t1.noimg.no_image_files_tracked", "1", "noimg")
def _(ctx):
  """No image files tracked by git (any directory)."""
  if not os.path.isdir(os.path.join(ctx.repo, ".git")):
    return "no git repository yet (tree scan covers this)"
  rc, out = H.run(["git", "ls-files"], cwd=ctx.repo, timeout=60)
  if rc != 0:
    raise Fail("git ls-files failed: %s" % out[-200:])
  bad = [l for l in out.splitlines() if l.lower().endswith(IMAGE_EXT)]
  if bad:
    raise Fail("tracked image files: %s" % bad[:10])


def _grep_tex_dir(ctx, sub, pattern):
  hits = []
  for f in repo_files(ctx, sub):
    if f.endswith((".tex", ".sty", ".cls", ".dtx", ".ltx")):
      src = strip_tex_comments(read(f))
    elif f.endswith(".lua"):
      src = re.sub(r"--.*", "", read(f))
    else:
      continue
    for m in re.finditer(pattern, src):
      hits.append("%s: %s" % (os.path.relpath(f, ctx.repo), m.group(0)))
  return hits


IMG_CMDS = (r"\\includegraphics|\\pdfximage|\\saveimageresource|"
            r"\\useimageresource|\\includepdf|\\pgfimage|\\epsfig|"
            r"\\pgfdeclareimage")


@test("t1.noimg.no_includegraphics_tex", "1", "noimg", quick=True)
def _(ctx):
  """tex/ uses no image-inclusion commands."""
  if not os.path.isdir(os.path.join(ctx.repo, "tex")):
    raise Fail("tex/ directory missing")
  hits = _grep_tex_dir(ctx, "tex", IMG_CMDS)
  if hits:
    raise Fail("; ".join(hits[:5]))


@test("t1.noimg.no_includegraphics_examples", "1", "noimg")
def _(ctx):
  """examples/ uses no image-inclusion commands."""
  if not os.path.isdir(os.path.join(ctx.repo, "examples")):
    raise Fail("examples/ directory missing")
  hits = _grep_tex_dir(ctx, "examples", IMG_CMDS)
  if hits:
    raise Fail("; ".join(hits[:5]))


@test("t1.noimg.no_lua_image_api", "1", "noimg")
def _(ctx):
  """Lua modules do not use LuaTeX image APIs (img.new/scan/write...)."""
  if not glob.glob(os.path.join(ctx.repo, "tex", "*.lua")):
    raise Fail("no tex/*.lua modules")
  hits = _grep_tex_dir(ctx, "tex", r"\bimg\s*\.\s*(new|scan|write|"
                       r"immediatewrite|node|copy)\b|pdf\.immediateobj\s*\("
                       r"[^)]*file")
  if hits:
    raise Fail("; ".join(hits[:5]))


@test("t1.noimg.fixtures_have_no_images", "1", "noimg")
def _(ctx):
  """(suite self-check) test fixtures include no images."""
  hits = []
  for f in glob.glob(os.path.join(H.FIXTURES, "*")):
    if f.lower().endswith(IMAGE_EXT):
      hits.append(f)
    elif f.endswith(".tex") and re.search(IMG_CMDS,
                                          strip_tex_comments(read(f))):
      hits.append(f)
  if hits:
    raise Fail("fixtures with images: %s" % hits)


@test("t1.noimg.fixture_pdf_no_images", "1", "noimg")
def _(ctx):
  """A decorated fixture PDF contains no image XObjects."""
  r = C(ctx)
  H.need_ok(r)
  rows = H.pdf_images(r.pdf)
  if rows:
    raise Fail("%d image(s): %s" % (len(rows), rows[0]))


# ===========================================================================
# Group: overlap / edge on fixtures
# ===========================================================================
@test("t1.overlap.pixel.base", "1", "overlap", quick=True)
def _(ctx):
  """Base article: word boxes identical with decoration on vs off."""
  on, off = on_off(ctx)
  H.check_overlap_pixels(ctx, on, off)


@test("t1.overlap.log.base", "1", "overlap", quick=True)
def _(ctx):
  """Base article: no elem bbox intersects the text block."""
  H.check_log_text_overlap(C(ctx))


@test("t1.overlap.text_layout_unchanged", "1", "overlap")
def _(ctx):
  """Loading kacho does not move any word (vs. document without kacho)."""
  on = C(ctx)
  ref = C(ctx, defs=r"\def\KachoNoPackage{}")
  H.need_ok(on)
  H.need_ok(ref)
  H.check_words_same(ctx, on, ref)


for _seed in (1, 2, 3, 4, 5):
  def _mk_edge(seed=_seed):
    def f(ctx):
      r = C(ctx, pkg_opts="seed=%d" % seed)
      H.check_log_edge(r)
      H.check_log_text_overlap(r)
    return f
  add("t1.edge.seed_sweep[%d]" % _seed, "1", "edge", _mk_edge(),
      quick=_seed == 1,
      doc="seed %d: elems inside 5 mm safe zone and off the text block" %
      _seed)


@test("t1.edge.log.base", "1", "edge", quick=True)
def _(ctx):
  """Base article: elem bboxes keep 5 mm from the paper edge."""
  H.check_log_edge(C(ctx))


@test("t1.edge.twoside_mirrored", "1", "edge")
def _(ctx):
  """Two-sided book: safe zone respected on both odd and even pages."""
  r = C(ctx, "twoside_book.tex")
  H.check_log_edge(r)
  pages = {e.page % 2 for e in H.need_elems(r)}
  if pages != {0, 1}:
    raise Fail("decoration only on %s pages" % (
        "odd" if pages == {1} else "even"))


# ===========================================================================
# Group: det
# ===========================================================================
@test("t1.det.same_seed_identical", "1", "det", quick=True)
def _(ctx):
  """Same seed compiled twice -> byte-identical page rasters."""
  a = C(ctx, pkg_opts="seed=42", rep=1)
  b = C(ctx, pkg_opts="seed=42", rep=2)
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


@test("t1.det.different_seed_differs", "1", "det", quick=True)
def _(ctx):
  """Different seeds -> different decoration."""
  a = C(ctx, pkg_opts="seed=1")
  b = C(ctx, pkg_opts="seed=2")
  if not H.renders_equal(ctx, a, b):
    raise Fail("seed=1 and seed=2 render identically")


@test("t1.det.default_seed_deterministic", "1", "det")
def _(ctx):
  """No seed option -> still reproducible across runs."""
  a = C(ctx, rep=1)
  b = C(ctx, rep=2)
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


@test("t1.det.pages_vary", "1", "det")
def _(ctx):
  """Per-page streams: decoration differs between pages (bbox sets differ)."""
  r = C(ctx, pkg_opts="seed=7")
  els = H.need_elems(r)
  by = {}
  for e in els:
    by.setdefault(e.page, []).append((e.kind, tuple(round(v, 1)
                                                    for v in e.bbox)))
  sets = [tuple(sorted(v)) for _, v in sorted(by.items())]
  if len(sets) < 2:
    raise Fail("decoration on fewer than 2 pages: %s" % sorted(by))
  if len(set(sets)) == 1:
    raise Fail("all pages have identical decoration")


@test("t1.det.thispage_isolated", "1", "det")
def _(ctx):
  """\\kachoThisPage on p2 leaves p1 and p3 pixel-identical (forked streams)."""
  a = C(ctx, "thispage.tex", pkg_opts="seed=5")
  b = C(ctx, "thispage.tex", pkg_opts="seed=5",
        defs=r"\def\KachoNoThisPage{}")
  d = H.renders_equal(ctx, a, b)
  if any(not isinstance(x, int) for x in d):
    raise Fail(str(d))
  if 1 in d or 3 in d:
    raise Fail("pages other than p2 changed: %s" % d)


@test("t1.det.env_seed_overrides_option", "1", "det")
def _(ctx):
  """KACHO_SEED env takes precedence over the seed= package option."""
  a = C(ctx, pkg_opts="seed=1", env={api.SEED_ENV: "77"})
  b = C(ctx, pkg_opts="seed=77")
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("KACHO_SEED=77 over seed=1 differs from seed=77 on pages %s"
               % d)


@test("t1.det.seed_option_vs_setup", "1", "det")
def _(ctx):
  """seed via \\kachosetup equals seed via package option."""
  a = C(ctx, pkg_opts="seed=99")
  b = C(ctx, defs=r"\def\KachoSetupArgs{seed=99}")
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


# ===========================================================================
# Group: palette
# ===========================================================================
def _decor_px(ctx, res, pages=None):
  H.need_ok(res)
  sizes = H.page_sizes(res.pdf)
  words = H.word_boxes(ctx, res.pdf)
  imgs = H.render(ctx, res.pdf, H.DECOR_DPI)
  px = []
  for p in (pages or range(1, len(imgs) + 1)):
    px += H.decoration_pixels(imgs[p - 1], words[p - 1], sizes[p - 1][0])
  return px


for _pal in api.PALETTES:
  def _mk(pal=_pal):
    def f(ctx):
      H.check_decor(ctx, C(ctx, pkg_opts="palette=%s,seed=11" % pal))
    return f
  add("t1.palette.decor[%s]" % _pal, "1", "palette", _mk(), quick=True,
      doc="palette=%s compiles and draws decoration" % _pal)

  def _mk2(pal=_pal):
    def f(ctx):
      px = _decor_px(ctx, C(ctx, pkg_opts="palette=%s,seed=11" % pal))
      if not px:
        raise Fail("no decoration pixels")
      pure = [c for c in px if max(c) >= 245 and min(c) <= 25 and
              H.saturation(c) > 0.9]
      if len(pure) > 0.01 * len(px):
        raise Fail("%d/%d decoration pixels are pure saturated RGB, e.g. %s"
                   % (len(pure), len(px), pure[0]))
    return f
  add("t1.palette.no_pure_rgb[%s]" % _pal, "1", "palette", _mk2(),
      doc="palette=%s avoids pure saturated RGB (survey_2 §4.6)" % _pal)


@test("t1.palette.sumi_vs_hanga_differ", "1", "palette")
def _(ctx):
  """palette=sumi and palette=hanga render differently (same seed)."""
  a = C(ctx, pkg_opts="palette=sumi,seed=11")
  b = C(ctx, pkg_opts="palette=hanga,seed=11")
  if not H.renders_equal(ctx, a, b):
    raise Fail("palettes render identically")


@test("t1.palette.sumi_less_saturated", "1", "palette")
def _(ctx):
  """Ink-wash sumi decoration is less saturated on average than hanga."""
  sa = _decor_px(ctx, C(ctx, pkg_opts="palette=sumi,seed=11"))
  sb = _decor_px(ctx, C(ctx, pkg_opts="palette=hanga,seed=11"))
  if not sa or not sb:
    raise Fail("no decoration pixels (sumi %d, hanga %d)" % (len(sa),
                                                             len(sb)))
  ma = sum(map(H.saturation, sa)) / len(sa)
  mb = sum(map(H.saturation, sb)) / len(sb)
  if not ma < mb:
    raise Fail("mean saturation sumi %.3f >= hanga %.3f" % (ma, mb))
  return "sumi %.3f < hanga %.3f" % (ma, mb)


@test("t1.palette.setup_equals_option", "1", "palette")
def _(ctx):
  """palette via \\kachosetup equals palette via package option."""
  a = C(ctx, pkg_opts="palette=hanga,seed=11")
  b = C(ctx, pkg_opts="seed=11", defs=r"\def\KachoSetupArgs{palette=hanga}")
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


# ===========================================================================
# Group: theme
# ===========================================================================
for _th in api.THEMES:
  def _mk(th=_th):
    def f(ctx):
      r = C(ctx, pkg_opts="theme=%s,seed=21" % th)
      H.check_decor(ctx, r)
      H.check_log_text_overlap(r)
    return f
  add("t1.theme.decor[%s]" % _th, "1", "theme", _mk(), quick=_th == "haru",
      doc="theme=%s compiles, decorates, stays off text" % _th)


@test("t1.theme.distinct", "1", "theme")
def _(ctx):
  """All themes render pairwise differently (same seed)."""
  rs = {t: C(ctx, pkg_opts="theme=%s,seed=21" % t) for t in api.THEMES}
  same = []
  ts = list(rs)
  for i in range(len(ts)):
    for j in range(i + 1, len(ts)):
      if not H.renders_equal(ctx, rs[ts[i]], rs[ts[j]]):
        same.append("%s=%s" % (ts[i], ts[j]))
  if same:
    raise Fail("identical renders: %s" % same)


@test("t1.theme.setup_equals_option", "1", "theme")
def _(ctx):
  """theme via \\kachosetup equals theme via package option."""
  a = C(ctx, pkg_opts="theme=aki,seed=21")
  b = C(ctx, pkg_opts="seed=21", defs=r"\def\KachoSetupArgs{theme=aki}")
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


@test("t1.theme.seasonal_motifs", "1", "theme")
def _(ctx):
  """Themes draw their seasonal flora (haru: sakura/ume; aki: maple...)."""
  expect = {"haru": "sakura|cherry|ume|plum|wisteria|orchid",
            "natsu": "iris|bamboo|ayame",
            "aki": "maple|momiji|chrysanth|kiku|osmanthus",
            "fuyu": "ume|plum|pine|bamboo|narcissus|camellia",
            "shochikubai": "pine|matsu"}
  bad = []
  for th, rx in expect.items():
    r = C(ctx, pkg_opts="theme=%s,seed=21" % th)
    kinds = {e.kind for e in H.need_elems(r)}
    if not any(re.search(rx, k, re.I) for k in kinds):
      bad.append("%s: none of /%s/ in %s" % (th, rx, sorted(kinds)[:8]))
  if bad:
    raise Fail("; ".join(bad))


# ===========================================================================
# Group: layout
# ===========================================================================
def _min_frac(layout):
  """scattered-petals is a deliberately low-key layout (survey_2 §4.5): a few
  petals; require only a trace of decoration."""
  return 0.0002 if layout == "scattered-petals" else H.DECOR_MIN_FRAC


for _ly in api.LAYOUTS:
  def _mk(ly=_ly):
    def f(ctx):
      r = C(ctx, pkg_opts="layout=%s,seed=31" % ly)
      H.check_decor(ctx, r, min_frac=_min_frac(ly))
      H.check_log_text_overlap(r)
      H.check_log_edge(r)
    return f
  add("t1.layout.decor[%s]" % _ly, "1", "layout", _mk(),
      quick=_ly == "corner-spray",
      doc="layout=%s compiles, decorates, respects text & edge" % _ly)


@test("t1.layout.distinct", "1", "layout")
def _(ctx):
  """All layouts render pairwise differently (same seed)."""
  rs = {l: C(ctx, pkg_opts="layout=%s,seed=31" % l) for l in api.LAYOUTS}
  same = []
  ls = list(rs)
  for i in range(len(ls)):
    for j in range(i + 1, len(ls)):
      if not H.renders_equal(ctx, rs[ls[i]], rs[ls[j]]):
        same.append("%s=%s" % (ls[i], ls[j]))
  if same:
    raise Fail("identical renders: %s" % same)


def _centers(ctx, layout):
  r = C(ctx, pkg_opts="layout=%s,seed=31" % layout)
  els = [e for e in H.need_elems(r)
         if not re.search(api.OVERLAP_EXEMPT_KIND, e.kind, re.I)]
  if not els:
    raise Fail("no decoration elems")
  return [((e.bbox[0] + e.bbox[2]) / 2, (e.bbox[1] + e.bbox[3]) / 2, e.tb)
          for e in els]


def _frac(items, pred):
  return sum(1 for it in items if pred(*it)) / float(len(items))


@test("t1.layout.header_garland_on_top", "1", "layout")
def _(ctx):
  """header-garland: >=80% of elem centres lie above the text block."""
  f = _frac(_centers(ctx, "header-garland"), lambda x, y, tb: y >= tb[3])
  if f < 0.8:
    raise Fail("only %.0f%% of elems above text block" % (100 * f))


@test("t1.layout.footer_ground_at_bottom", "1", "layout")
def _(ctx):
  """footer-ground: >=80% of elem centres lie in the lower half of page."""
  f = _frac(_centers(ctx, "footer-ground"),
            lambda x, y, tb: y <= (tb[1] + tb[3]) / 2)
  if f < 0.8:
    raise Fail("only %.0f%% of elems in lower half" % (100 * f))


@test("t1.layout.margin_column_in_margin", "1", "layout")
def _(ctx):
  """margin-column: >=80% of elem centres lie beside the text block."""
  f = _frac(_centers(ctx, "margin-column"),
            lambda x, y, tb: x <= tb[0] or x >= tb[2])
  if f < 0.8:
    raise Fail("only %.0f%% of elems in side margins" % (100 * f))


@test("t1.layout.scattered_is_light", "1", "layout")
def _(ctx):
  """scattered-petals covers less area than corner-spray (low-key)."""
  a = sum(H.page_decor_fracs(ctx, C(ctx, pkg_opts=
                                    "layout=scattered-petals,seed=31"))
          .values())
  b = sum(H.page_decor_fracs(ctx, C(ctx, pkg_opts=
                                    "layout=corner-spray,seed=31")).values())
  if not 0 < a < b:
    raise Fail("scattered %.4f vs corner-spray %.4f" % (a, b))


# ===========================================================================
# Group: control
# ===========================================================================
@test("t1.control.off_renders_like_no_package", "1", "control", quick=True)
def _(ctx):
  """`off` option: render identical to the document without kacho."""
  off = C(ctx, off=True)
  ref = C(ctx, defs=r"\def\KachoNoPackage{}")
  d = H.renders_equal(ctx, off, ref, dpi=50)
  if d:
    raise Fail("off differs from no-package render on pages %s" % d)


@test("t1.control.off_option_equals_env", "1", "control")
def _(ctx):
  """`\\usepackage[off]{kacho}` renders like KACHO_OFF=1 (no decoration)."""
  a = C(ctx, off="option")
  b = C(ctx, off="env")
  d = H.renders_equal(ctx, a, b, dpi=50)
  if d:
    raise Fail("off option differs from KACHO_OFF on pages %s" % d)


@test("t1.control.off_logs_no_elems", "1", "control")
def _(ctx):
  """`off` option: debug log has no elem lines."""
  off = C(ctx, off=True)
  H.need_ok(off)
  if off.elems:
    raise Fail("%d elems logged with off" % len(off.elems))


@test("t1.control.decorated_by_default", "1", "control", quick=True)
def _(ctx):
  """Plain \\usepackage{kacho} decorates the page (default options)."""
  H.check_decor(ctx, C(ctx))


@test("t1.control.kachoOff_page", "1", "control")
def _(ctx):
  """\\kachoOff disables decoration of page 2."""
  r = C(ctx, "control_pages.tex", pkg_opts="seed=3")
  H.check_no_decor(ctx, r, [2])
  if any(e.page == 2 for e in r.elems):
    raise Fail("debug log has elems on page 2")


@test("t1.control.kachoOn_page", "1", "control")
def _(ctx):
  """\\kachoOn re-enables decoration on page 3 (and p1 decorated)."""
  r = C(ctx, "control_pages.tex", pkg_opts="seed=3")
  H.check_decor(ctx, r, pages=[1, 3], all_pages=True)


@test("t1.control.thispage_changes_page", "1", "control")
def _(ctx):
  """\\kachoThisPage{layout=header-garland} changes page 2's decoration."""
  a = C(ctx, "thispage.tex", pkg_opts="seed=5,layout=corner-spray")
  b = C(ctx, "thispage.tex", pkg_opts="seed=5,layout=corner-spray",
        defs=r"\def\KachoNoThisPage{}")
  d = H.renders_equal(ctx, a, b)
  if 2 not in d:
    raise Fail("page 2 unchanged by \\kachoThisPage (diff pages: %s)" % d)


@test("t1.control.density_monotonic", "1", "control")
def _(ctx):
  """density=0.2 covers less area than density=1."""
  lo = sum(H.page_decor_fracs(ctx, C(ctx, pkg_opts=
                                     "density=0.2,seed=8")).values())
  hi = sum(H.page_decor_fracs(ctx, C(ctx, pkg_opts=
                                     "density=1,seed=8")).values())
  if not lo < hi:
    raise Fail("density 0.2 -> %.4f, 1.0 -> %.4f" % (lo, hi))
  return "%.4f < %.4f" % (lo, hi)


@test("t1.control.density_setup_equals_option", "1", "control")
def _(ctx):
  """density via \\kachosetup equals density via package option."""
  a = C(ctx, pkg_opts="density=0.4,seed=8")
  b = C(ctx, pkg_opts="seed=8", defs=r"\def\KachoSetupArgs{density=0.4}")
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("renders differ on pages %s" % d)


@test("t1.control.debug_option_writes_log", "1", "control")
def _(ctx):
  """`debug` package option (without env) writes <job>.kacho.log."""
  r = C(ctx, pkg_opts="debug", debug=False)
  H.need_elems(r)


@test("t1.control.debug_log_format", "1", "control", quick=True)
def _(ctx):
  """debug log lines parse; bboxes ordered/finite; textblock inside page."""
  H.check_log_format(C(ctx))


@test("t1.control.debug_does_not_alter_render", "1", "control")
def _(ctx):
  """Rendering is identical with and without debug logging."""
  a = C(ctx, pkg_opts="seed=4", debug=True)
  b = C(ctx, pkg_opts="seed=4", debug=False)
  d = H.renders_equal(ctx, a, b)
  if d:
    raise Fail("debug changes rendering on pages %s" % d)


# ===========================================================================
# Group: title
# ===========================================================================
def _title(ctx, off=False):
  return C(ctx, "title_page.tex", pkg_opts="seed=13", defs=TITLE_DEFS,
           off=off)


@test("t1.title.compiles", "1", "title", quick=True)
def _(ctx):
  """\\kachoTitlePage compiles."""
  H.need_ok(_title(ctx))


@test("t1.title.decorated", "1", "title")
def _(ctx):
  """Title page carries decoration."""
  H.check_decor(ctx, _title(ctx), pages=[1], min_frac=0.01)


@test("t1.title.text_present", "1", "title")
def _(ctx):
  """Title text is typeset as real (extractable) text."""
  r = _title(ctx)
  H.need_ok(r)
  t = H.pdf_text(r.pdf)
  if api.TITLE_TEXT not in re.sub(r"\s+", " ", t):
    raise Fail("%r not found in PDF text" % api.TITLE_TEXT)


@test("t1.title.edge_safe", "1", "title")
def _(ctx):
  """Title page motifs respect the 5 mm safe zone."""
  H.check_log_edge(_title(ctx))


@test("t1.title.text_not_overpainted", "1", "title")
def _(ctx):
  """Title/body text pixels are not painted over (on vs off)."""
  on, off = _title(ctx), _title(ctx, off=True)
  H.check_overlap_pixels(ctx, on, off)


@test("t1.title.body_pages_decorated", "1", "title")
def _(ctx):
  """Body pages after the title page are decorated and stay off text."""
  r = _title(ctx)
  H.check_decor(ctx, r, pages=list(range(2, max(3, r.pages + 1))))
  H.check_log_text_overlap(r)


@test("t1.title.shikishi_opener", "1", "title")
def _(ctx):
  """Shikishi chapter opener compiles and decorates its page."""
  r = C(ctx, "chapter_opener.tex", pkg_opts="seed=17", defs=OPENER_DEFS)
  H.check_decor(ctx, r, pages=[1])
  H.check_log_edge(r)


# ===========================================================================
# Group: docs
# ===========================================================================
def _readme(ctx):
  p = os.path.join(ctx.repo, "README.md")
  if not os.path.exists(p):
    raise Fail("README.md missing")
  return read(p)


def _notice(ctx):
  for n in ("NOTICE.md", "NOTICE", "THIRD_PARTY.md", "NOTICE.txt"):
    p = os.path.join(ctx.repo, n)
    if os.path.exists(p):
      return read(p)
  raise Fail("NOTICE(.md) missing")


@test("t1.docs.readme_compile_cmd", "1", "docs", quick=True)
def _(ctx):
  """README documents the compile command (`make`)."""
  if not re.search(r"(^|\s|`)make(\s|`|$)", _readme(ctx), re.M):
    raise Fail("README does not mention `make`")


@test("t1.docs.readme_view_cmd", "1", "docs")
def _(ctx):
  """README documents the view command (`make view`)."""
  if "make view" not in _readme(ctx):
    raise Fail("README does not mention `make view`")


@test("t1.docs.readme_options", "1", "docs")
def _(ctx):
  """README documents the options seed/palette/theme/layout/density."""
  t = _readme(ctx)
  miss = [o for o in ("seed", "palette", "theme", "layout", "density")
          if o not in t]
  if miss:
    raise Fail("options not documented: %s" % miss)


@test("t1.docs.license_apache2", "1", "docs", quick=True)
def _(ctx):
  """LICENSE uses Apache License 2.0 with Copyright 2026 Allen Jue."""
  p = os.path.join(ctx.repo, "LICENSE")
  if not os.path.exists(p):
    raise Fail("LICENSE missing")
  t = read(p)
  miss = [k for k in api.LICENSE_MARKERS + [api.COPYRIGHT_LINE] if k not in t]
  if miss:
    raise Fail("LICENSE missing Apache-2.0 / markers: %s" % miss)


@test("t1.docs.apache_headers", "1", "docs", quick=True)
def _(ctx):
  """Own source files in tex/kacho*.lua and tex/kacho.sty carry Apache-2.0 header."""
  files = sorted(glob.glob(os.path.join(ctx.repo, "tex", "kacho*.lua")) +
                 glob.glob(os.path.join(ctx.repo, "tex", "kacho*.sty")))
  if not files:
    raise Fail("no tex/kacho*.lua or tex/kacho.sty files found")
  bad = []
  for f in files:
    head = read(f)[:api.HEADER_SCAN_CHARS]
    if api.COPYRIGHT_LINE not in head or not re.search(api.APACHE_HEADER_RE,
                                                       head):
      bad.append(os.path.relpath(f, ctx.repo))
  if bad:
    raise Fail("missing Apache-2.0 header in: %s" % bad)
  return "%d file(s)" % len(files)


@test("t1.docs.notice_attribution", "1", "docs")
def _(ctx):
  """NOTICE attributes florilegium (c) Kevin Raymond with MIT terms."""
  t = _notice(ctx)
  miss = [k for k in ("florilegium", "Kevin Raymond",
                      "Permission is hereby granted") if k not in t]
  if miss:
    raise Fail("NOTICE lacks: %s" % miss)


@test("t1.docs.readme_credits", "1", "docs")
def _(ctx):
  """README credits florilegium."""
  if "florilegium" not in _readme(ctx).lower():
    raise Fail("README does not credit florilegium")


@test("t1.docs.adapted_files_attributed", "1", "docs")
def _(ctx):
  """Source files mentioning florilegium carry an MIT/attribution header."""
  bad = []
  files = [f for f in repo_files(ctx, "tex")] if os.path.isdir(
      os.path.join(ctx.repo, "tex")) else []
  if not files:
    raise Fail("tex/ missing")
  for f in files:
    t = read(f)
    if "florilegium" in t.lower():
      head = t[:api.HEADER_SCAN_CHARS]
      if (re.search(r"no\b[^.\n;]*\b(copied|florilegium)\b[^.\n;]*\b(florilegium|copied)",
                    head, re.I)
          and not re.search(r"adapted\s+(?:from|via)\s+florilegium", head, re.I)):
        continue
      if not ("MIT" in head and ("Kevin Raymond" in head or
                                 "NOTICE" in head.upper())):
        bad.append(os.path.relpath(f, ctx.repo))
  if bad:
    raise Fail("adapted files without attribution header: %s" % bad)


@test("t1.docs.readme_algorithms", "1", "docs", quick=True)
def _(ctx):
  """README has 'Algorithms & References' citing core sources and every ALGORITHMS module."""
  t = _readme(ctx)
  if not re.search(api.README_ALGO_HEADING, t, re.M | re.I):
    raise Fail("README missing 'Algorithms & References' section")
  checks = [
      ("space colonization / Runions", r"space\s+coloni[sz]ation|Runions"),
      ("pipe model / Shinozaki / da Vinci", r"pipe\s+model|Shinozaki|da\s+Vinci"),
      ("Prusinkiewicz / L-systems", r"Prusinkiewicz|L-system"),
      ("Wong 1998", r"Wong"),
      ("florilegium", r"florilegium"),
      ("tikz-flora", r"tikz-flora"),
      ("adapted from / inspired by", r"adapted\s+from|inspired\s+by"),
  ]
  miss = [label for label, rx in checks if not re.search(rx, t, re.I)]
  if miss:
    raise Fail("README Algorithms & References missing: %s" % miss)
  lua_files = sorted(glob.glob(os.path.join(ctx.repo, "tex", "kacho*.lua")))
  unlisted = []
  for f in lua_files:
    if api.ALGO_BLOCK_MARKER in read(f):
      base = os.path.basename(f)
      stem = os.path.splitext(base)[0]
      if base not in t and stem not in t:
        unlisted.append(base)
  if unlisted:
    raise Fail("tex/kacho*.lua with %s not referenced in README: %s" % (
        api.ALGO_BLOCK_MARKER, unlisted))


@test("t1.docs.no_build_outputs_committed", "1", "docs")
def _(ctx):
  """.gitignore ignores build/ and LaTeX aux files."""
  p = os.path.join(ctx.repo, ".gitignore")
  if not os.path.exists(p):
    raise Fail(".gitignore missing")
  t = read(p)
  miss = [k for k in ("build", ".aux", ".log") if k not in t]
  if miss:
    raise Fail(".gitignore lacks %s" % miss)


# ===========================================================================
# Tier 2: boundary scenarios
# ===========================================================================
# name: (fixture, class_opts, geom_opts, pkg_opts, expect_decor, defs, quick)
# expect_decor: True  -> decoration required, debug-log checks required;
#               None  -> decoration optional (e.g. 1 cm margins leave no room
#                        once the 5 mm edge zone and 4 mm text buffer are
#                        removed); debug-log checks apply to whatever is drawn.
SCENARIOS = {
    "a4": (BASE, "a4paper", "", "seed=51", True, "", True),
    "a5": (BASE, "a5paper", "", "seed=51", True, "", True),
    "letter": (BASE, "letterpaper", "", "seed=51", True, "", False),
    "b5": (BASE, "b5paper", "", "seed=51", True, "", False),
    "a4-landscape": (BASE, "a4paper,landscape", "", "seed=51", True, "",
                     False),
    "a5-landscape": (BASE, "a5paper,landscape", "", "seed=51", True, "",
                     False),
    "letter-landscape": (BASE, "letterpaper,landscape", "", "seed=51", True,
                         "", False),
    "narrow-margins": (BASE, "a4paper", "margin=1cm", "seed=51", None, "",
                       True),
    "wide-margins": (BASE, "a4paper", "margin=5cm", "seed=51", True, "",
                     False),
    "twocolumn": (BASE, "twocolumn", "", "seed=51", True, "", False),
    "twoside-book": ("twoside_book.tex", "", "", "seed=51", True, "", False),
    "report": ("report_class.tex", "", "", "seed=51", True, "", False),
    "fancy-headers": ("fancy_headers.tex", "", "", "seed=51", True, "",
                      False),
    "multicol": ("multicol_doc.tex", "", "", "seed=51", True, "", False),
    "single-page": ("single_page.tex", "", "", "seed=51", True, "", True),
    "blank-page": ("blank_page.tex", "", "", "seed=51", True, "", False),
    "long-50pp": ("long_doc.tex", "", "", "seed=51", True, "", False),
    "title-only": ("title_only.tex", "", "", "seed=51", True, TITLE_DEFS,
                   False),
    "density-0": (BASE, "", "", "density=0,seed=51", None, "", False),
    "density-1": (BASE, "", "", "density=1,seed=51", True, "", False),
    "seed-0": (BASE, "", "", "seed=0", True, "", False),
    "seed-max": (BASE, "", "", "seed=4294967295", True, "", False),
    "special-chars": ("special_chars.tex", "", "", "seed=51", True, "",
                      False),
    "12pt-large": (BASE, "12pt", "", "seed=51", True, "", False),
}


def _scenario_tests():
  for name, (fx, cls, geo, pkg, expect, defs, q) in SCENARIOS.items():
    def res(ctx, off=False, fx=fx, cls=cls, geo=geo, pkg=pkg, defs=defs):
      return C(ctx, fx, pkg_opts=pkg, class_opts=cls, geom_opts=geo,
               defs=defs, off=off)

    def t_compile(ctx, res=res, name=name):
      r = res(ctx)
      H.need_ok(r)
      if name == "long-50pp" and r.pages < 50:
        raise Fail("only %d pages (fixture should give >=50)" % r.pages)
      return "%d page(s), %.1fs" % (r.pages, r.seconds)
    add("t2.%s.compile" % name, "2", "build", t_compile, quick=q,
        doc="%s: compiles without errors" % name)

    if expect is not None:
      def t_decor(ctx, res=res):
        H.check_decor(ctx, res(ctx))
      add("t2.%s.decor" % name, "2", "layout", t_decor, quick=q,
          doc="%s: decoration drawn" % name)

    if fx not in ("blank_page.tex",):
      def t_pix(ctx, res=res):
        H.check_overlap_pixels(ctx, res(ctx), res(ctx, off=True))
      add("t2.%s.overlap_pixel" % name, "2", "overlap", t_pix, quick=q,
          doc="%s: no pixels changed inside word boxes" % name)

    def t_lt(ctx, res=res, expect=expect):  # pylint: disable=function-redefined
      r = res(ctx)
      H.need_ok(r)
      if expect is None and not r.elems:
        # Nothing logged: then nothing may be drawn either.
        H.check_no_decor(ctx, r, list(range(1, r.pages + 1)), max_frac=0.002)
        return "nothing drawn"
      H.check_log_text_overlap(r)
    add("t2.%s.overlap_log" % name, "2", "overlap", t_lt, quick=q,
        doc="%s: no elem bbox intersects the text block" % name)

    def t_le(ctx, res=res, expect=expect):
      r = res(ctx)
      H.need_ok(r)
      if expect is None and not r.elems:
        # Nothing logged: then nothing may be drawn either.
        H.check_no_decor(ctx, r, list(range(1, r.pages + 1)), max_frac=0.002)
        return "nothing drawn"
      H.check_log_edge(r)
    add("t2.%s.edge_log" % name, "2", "edge", t_le, quick=q,
        doc="%s: elems inside 5 mm safe zone" % name)

  # Special boundary scenarios with custom expectations.
  def empty(ctx):
    r = C(ctx, "empty_body.tex")
    H.need_ok(r, allow_no_pdf=True)
  add("t2.empty-body.compile", "2", "build", empty, quick=True,
      doc="empty document body: no error (no pages)")

  def all_off(ctx):
    r = C(ctx, "all_off.tex")
    H.need_ok(r)
    H.check_no_decor(ctx, r, list(range(1, r.pages + 1)))
  add("t2.all-off.no_decor", "2", "control", all_off,
      doc="\\kachoOff at start: no page decorated")

  def narrow_small(ctx):
    r = C(ctx, BASE, class_opts="a5paper", geom_opts="margin=1cm",
          pkg_opts="seed=52")
    H.need_ok(r)
    if r.kacho_log is None:
      raise Fail("no debug log written")
    if r.elems:
      H.check_log_text_overlap(r)
      H.check_log_edge(r)
    H.check_overlap_pixels(ctx, r, C(ctx, BASE, class_opts="a5paper",
                                     geom_opts="margin=1cm",
                                     pkg_opts="seed=52", off=True))
  add("t2.a5-narrow-margins.safe", "2", "overlap", narrow_small,
      doc="a5 + 1 cm margins: compiles; any decoration avoids text & edge")

  def long_every(ctx):
    r = C(ctx, "long_doc.tex", pkg_opts="seed=51")
    H.need_elems(r)
    pages = {e.page for e in r.elems}
    if len(pages) < r.pages // 2:
      raise Fail("only %d of %d pages decorated" % (len(pages), r.pages))
  add("t2.long-50pp.most_pages_decorated", "2", "layout", long_every,
      doc="long doc: at least half the pages carry decoration")

  def landscape_tb(ctx):
    r = C(ctx, BASE, class_opts="a4paper,landscape", pkg_opts="seed=51")
    els = H.need_elems(r)
    w, h = H.page_sizes(r.pdf)[0]
    if not w > h:
      raise Fail("page not landscape (%.0fx%.0f)" % (w, h))
    t = els[0].tb
    if t[2] > w or t[3] > h:
      raise Fail("textblock %s exceeds landscape page" % (t,))
  add("t2.a4-landscape.textblock_geometry", "2", "control", landscape_tb,
      doc="landscape: debug textblock reflects the rotated page")


# ===========================================================================
# Tier 3: pairwise palette x theme x layout x paper
# ===========================================================================
def pairwise(factors):
  """Greedy all-pairs covering array. factors: list of value lists."""
  import itertools
  uncovered = set()
  k = len(factors)
  for i, j in itertools.combinations(range(k), 2):
    for a in factors[i]:
      for b in factors[j]:
        uncovered.add((i, a, j, b))
  rows = []
  allrows = list(itertools.product(*factors))
  while uncovered:
    best, bestn = None, -1
    for r in allrows:
      n = sum(1 for i, j in itertools.combinations(range(k), 2)
              if (i, r[i], j, r[j]) in uncovered)
      if n > bestn:
        best, bestn = r, n
    rows.append(best)
    for i, j in itertools.combinations(range(k), 2):
      uncovered.discard((i, best[i], j, best[j]))
  return rows


def _pairwise_tests():
  combos = pairwise([api.PALETTES, api.THEMES, api.LAYOUTS, api.PAPERS])
  for n, (pal, th, ly, pap) in enumerate(combos):
    def f(ctx, pal=pal, th=th, ly=ly, pap=pap, n=n):
      opts = "palette=%s,theme=%s,layout=%s,seed=%d" % (pal, th, ly, 300 + n)
      on = C(ctx, BASE, pkg_opts=opts, class_opts=pap)
      H.check_decor(ctx, on, min_frac=_min_frac(ly))
      H.check_log_text_overlap(on)
      H.check_log_edge(on)
      off = C(ctx, BASE, pkg_opts=opts, class_opts=pap, off=True)
      H.check_overlap_pixels(ctx, on, off)
    add("t3.pair[%s,%s,%s,%s]" % (pal, th, ly, pap.replace("paper", "")),
        "3", "layout", f, quick=n < 2,
        doc="pairwise combo: decorates, no overlap, safe edges")


# ===========================================================================
# Tier 4: realistic documents
# ===========================================================================
T4 = [
    ("letter", "t4_letter.tex", ""),
    ("article", "t4_article.tex", ""),
    ("report-twoside-a5", "t4_report_twoside.tex", ""),
    ("poems", "t4_poems.tex", ""),
    ("conference-twocolumn", "t4_conference.tex", ""),
    ("menu-a5-landscape", "t4_menu.tex", ""),
    ("invitation", "t4_invitation.tex", TITLE_DEFS),
    ("koma-scrartcl", "t4_koma.tex", ""),
]


def _t4_tests():
  for i, (name, fx, defs) in enumerate(T4):
    def res(ctx, off=False, fx=fx, defs=defs):
      return C(ctx, fx, defs=defs, off=off)

    def t_compile(ctx, res=res):
      r = res(ctx)
      H.need_ok(r)
      return "%d page(s)" % r.pages
    add("t4.%s.compile" % name, "4", "build", t_compile, quick=i < 2,
        doc="%s: compiles" % name)

    def t_decor(ctx, res=res):
      H.check_decor(ctx, res(ctx))
    add("t4.%s.decor" % name, "4", "layout", t_decor, quick=i < 2,
        doc="%s: decorated" % name)

    def t_pix(ctx, res=res):
      H.check_overlap_pixels(ctx, res(ctx), res(ctx, off=True))
    add("t4.%s.overlap_pixel" % name, "4", "overlap", t_pix, quick=i < 2,
        doc="%s: text untouched by decoration" % name)

    def t_log(ctx, res=res):
      r = res(ctx)
      H.check_log_text_overlap(r)
      H.check_log_edge(r)
    add("t4.%s.log_text_edge" % name, "4", "edge", t_log, quick=i < 2,
        doc="%s: elems off text block and inside safe zone" % name)


def build_registry(repo):
  del TESTS[len(_STATIC):]
  _register_example_tests(repo)
  _scenario_tests()
  _pairwise_tests()
  _t4_tests()
  suite_place.register(add)
  suite_license.register(add, repo)
  suite_anim.register(add, repo)
  return list(TESTS)


_STATIC = list(TESTS)
