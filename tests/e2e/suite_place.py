"""Feature 32 (user-controlled placement) tests for the kacho E2E suite.

ORIGINAL_REQUEST follow-up 2026-11-02T02:06:28Z asks for:
  * an inline spray usable inside figures with captions,
  * absolute placement (anchor corners/edges, x/y offsets, angle, size),
  * per-page / per-region control (margins/edges, full border frame,
    corners, none), settable globally and per page,
  * spawn-point lists,
  * determinism per seed, validated by the same overlap/edge tests.

Opaque-box: the tests drive the TeX commands named in api_config.py and read
the debug log contract (elem lines plus the `# ... inline spray=` and
`# ... user spawn=` comment lines, explorer_m3_1 §4.9). Expected values come
from that specification, not from the implementation.

Registered by suite.build_registry() through register().
"""

import re

import api_config as api
import harness as H
from harness import Fail

GROUP = "place"
GROUP_DOC = ("User-controlled placement: \\kachoSpawn origins, inline "
             "\\kachospray in figures, regions=/spawn=/motif= per page, "
             "border frame (feature 32)")

PAGES = "place_pages.tex"
INLINE = "place_inline.tex"
# Generous margins on all four sides so every band (incl. the top band below
# the running head) has room for decoration.
GEOM = "left=40mm,right=40mm,top=50mm,bottom=50mm"
MM = H.MM


# ---------------------------------------------------------------------------
# Small builders (all API spellings come from api_config)
# ---------------------------------------------------------------------------
def spawn(**kw):
  return api.SPAWN_CMD % ",".join("%s=%s" % kv for kv in kw.items())


def spray(**kw):
  return api.SPRAY_CMD % ",".join("%s=%s" % kv for kv in kw.items())


def page_cmd(**kw):
  return api.PAGE_CMD % ",".join("%s=%s" % kv for kv in kw.items())


def setup_args(**kw):
  return r"\def\KachoSetupArgs{%s}" % ",".join("%s=%s" % kv
                                               for kv in kw.items())


def hook(name, body):
  return r"\def\%s{%s}" % (name, body)


def defs(*parts):
  return "\n".join(p for p in parts if p)


def regions_kw(value):
  return {api.REGIONS_KEY: value}


def compile_pages(ctx, p1="", p2="", p3="", setup=None, pkg="seed=21",
                  geom=GEOM, cls="", off=False, rep=0):
  d = defs(setup_args(**setup) if setup else "",
           hook("KachoPageOneCmd", p1) if p1 else "",
           hook("KachoPageTwoCmd", p2) if p2 else "",
           hook("KachoPageThreeCmd", p3) if p3 else "")
  return H.compile_doc(ctx, PAGES, pkg_opts=pkg, geom_opts=geom,
                       class_opts=cls, defs=d, off=off, rep=rep)


def compile_inline(ctx, spray_cmd=None, spray_b="", setup=None, pkg="seed=21",
                   geom="", cls="", off=False, rep=0):
  sc = spray_cmd if spray_cmd is not None else spray(
      width=r"0.6\linewidth", height="45mm", seed=7)
  d = defs(setup_args(**setup) if setup else "",
           hook("KachoSprayCmd", sc),
           hook("KachoSprayCmdB", spray_b) if spray_b else "")
  return H.compile_doc(ctx, INLINE, pkg_opts=pkg, geom_opts=geom,
                       class_opts=cls, defs=d, off=off, rep=rep)


NONE = regions_kw("none")


def page_elems(res, page, skip_exempt=False):
  out = []
  for e in H.need_elems(res):
    if e.page != page or re.search(api.OVERLAP_EXEMPT_KIND, e.kind, re.I):
      continue
    if skip_exempt and re.search(api.EDGE_EXEMPT_KIND, e.kind, re.I):
      continue
    out.append(e)
  return out


def need_spawns(res, n=1, page=None):
  H.need_ok(res)
  sp = [s for s in H.user_spawns(res) if page is None or s.page == page]
  if len(sp) < n:
    raise Fail("expected >=%d `# page=.. user spawn=..` log line(s)%s, found "
               "%d (log contract explorer_m3_1 §4.9)" % (
                   n, " on page %d" % page if page else "", len(sp)))
  return sp


def need_drawn(sp):
  bad = [s for s in sp if not re.fullmatch(api.SPAWN_OK_STATUS, s.status)]
  if bad:
    raise Fail("spawn(s) not drawn: %s" % ", ".join(
        "p%d #%d at=%s status=%s" % (s.page, s.index, s.at, s.status)
        for s in bad))


def near_origin(res, s, near_mm=api.SPAWN_NEAR_MM):
  """Elements on the spawn's page within near_mm of its origin."""
  return [e for e in H.need_elems(res) if e.page == s.page and
          H.point_rect_dist(s.origin, e.bbox) <= near_mm * MM]


def need_inline(res, n=1):
  H.need_ok(res)
  boxes = H.inline_boxes(res)
  if len(boxes) < n:
    raise Fail("expected >=%d `# page=.. inline spray=.. box=..` log line(s),"
               " found %d" % (n, len(boxes)))
  return boxes


def check_inline_inside(res):
  """Every inline-kind elem lies inside a logged inline box on its page."""
  boxes = need_inline(res)
  inl = [e for e in H.need_elems(res) if re.search(api.INLINE_KIND, e.kind,
                                                   re.I)]
  if not inl:
    raise Fail("no elem kind with token 'inline' logged (kinds: %s)" % sorted(
        {e.kind for e in res.elems})[:12])
  bad = [e for e in inl if not any(b[0] == e.page and H.bbox_inside(
      e.bbox, b[2]) for b in boxes)]
  if bad:
    raise Fail("%d inline elem(s) outside every inline box: %s" % (
        len(bad), "; ".join("p%d %s %s" % (e.page, e.kind, H._fmt(e.bbox))
                            for e in bad[:4])))
  return len(inl)


def check_inline_box_clear(ctx, res, tol=0.5):
  """The inline box intersects no word box (paragraphs and caption)."""
  boxes = need_inline(res)
  words = H.word_boxes(ctx, res.pdf)
  sizes = H.page_sizes(res.pdf)
  bad = []
  for page, idx, b in boxes:
    ph = sizes[page - 1][1]
    tl = (b[0], ph - b[3], b[2], ph - b[1])  # top-left origin, pt
    for w in words[page - 1]:
      dx, dy = H._inter(tl, w)
      if dx > tol and dy > tol:
        bad.append("spray %d p%d box %s overlaps word %r" % (
            idx, page, H._fmt(b), w[4]))
  if bad:
    raise Fail("; ".join(bad[:4]))


def side_hits(elems, tb):
  hits = {"left": 0, "right": 0, "top": 0, "bottom": 0}
  for e in elems:
    cx, cy = H.center(e.bbox)
    if cx < tb[0]:
      hits["left"] += 1
    if cx > tb[2]:
      hits["right"] += 1
    if cy > tb[3]:
      hits["top"] += 1
    if cy < tb[1]:
      hits["bottom"] += 1
  return hits


def check_four_sides(res, page=1):
  els = page_elems(res, page)
  if not els:
    raise Fail("no elems on page %d" % page)
  hits = side_hits(els, els[0].tb)
  miss = [k for k, v in hits.items() if v == 0]
  if miss:
    raise Fail("frame: no elem centred beyond the text block on side(s) %s "
               "(hits %s)" % (miss, hits))
  return "sides %s" % hits


def pixel_sides(ctx, on, off, page=1):
  """Counts of decoration (diff) pixels left/right/above/below the text
  block, using the textblock from the debug log."""
  els = page_elems(on, page)
  if not els:
    raise Fail("no elems on page %d" % page)
  tb = els[0].tb
  px, scale, ph, _ = H.diff_pixels(ctx, on, off, page, dpi=40)
  r = H.bp_to_px(tb, scale, ph)
  c = {"left": 0, "right": 0, "top": 0, "bottom": 0}
  for x, y in px:
    if x < r[0]:
      c["left"] += 1
    if x > r[2]:
      c["right"] += 1
    if y < r[1]:
      c["top"] += 1
    if y > r[3]:
      c["bottom"] += 1
  return c, len(px)


def in_corner(cx, cy, tb, slack):
  return ((cx < tb[0] + slack or cx > tb[2] - slack) and
          (cy < tb[1] + slack or cy > tb[3] - slack))


def check_safe(ctx, on, off=None, allow_empty=False):
  """Log overlap (inline-aware) + edge + pixel overlap."""
  H.need_ok(on)
  if on.elems or not allow_empty:
    H.check_log_text_overlap(on)
    H.check_log_edge(on)
  elif on.kacho_log is None:
    raise Fail("no debug log written")
  if off is not None:
    H.check_overlap_pixels(ctx, on, off)


def quadrant_ok(at, c, w, h):
  fx, fy = api.ANCHORS[at]
  ok = True
  if fx < 0.5:
    ok &= c[0] < w / 2
  if fx > 0.5:
    ok &= c[0] > w / 2
  if fy < 0.5:
    ok &= c[1] < h / 2
  if fy > 0.5:
    ok &= c[1] > h / 2
  return ok


# Explicit growth angles into the margin band for edge anchors (the default
# angle points at the page centre, i.e. into the text, while 0/90/180/-90 hug
# the 0 bp paper edge outside the 5 mm safe zone); corners use the default.
EDGE_ANGLE = {"tc": -35, "bc": 35, "ml": 65, "mr": 115}


def anchor_cmd(at, **kw):
  if at in EDGE_ANGLE and "angle" not in kw:
    kw["angle"] = EDGE_ANGLE[at]
  kw.setdefault("size", "70mm")
  kw.setdefault("seed", 11)
  return spawn(at=at, **kw)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register(add):
  """add(name, tier, group, fn, quick=False, advisory=False, doc="")."""
  _tier1_inline(add)
  _tier1_spawn(add)
  _tier1_regions(add)
  _tier1_perpage(add)
  _tier1_det(add)
  _tier2(add)
  _tier3(add)
  _tier4(add)


# ----------------------------- tier 1: inline ------------------------------
def _tier1_inline(add):
  def compiles(ctx):
    r = compile_inline(ctx)
    H.need_ok(r)
    return "%d page(s)" % r.pages
  add("t1.place.inline_compiles", "1", GROUP, compiles, quick=True,
      doc="inline spray inside a figure with \\caption compiles")

  def logged(ctx):
    r = compile_inline(ctx)
    boxes = need_inline(r)
    page, _, b = boxes[0]
    w = b[2] - b[0]
    h = b[3] - b[1]
    # requested 0.6\linewidth x 45 mm (geometry default linewidth ~428.4 bp ->
    # 0.6\linewidth ~257 bp; stock article linewidth 345 pt -> ~206 bp)
    tb_w = (r.elems[0].tb[2] - r.elems[0].tb[0]) if r.elems else None
    w_ok = (abs(w - 0.6 * tb_w) <= 8.0) if tb_w else (180 <= w <= 280)
    if not (abs(h - 45 * MM) <= 3.0 and w_ok):
      raise Fail("inline box %.1fx%.1f bp does not match the requested "
                 "0.6\\linewidth x 45mm (~127.6 bp high)" % (w, h))
    return "box p%d %s" % (page, H._fmt(b))
  add("t1.place.inline_logged_box", "1", GROUP, logged, quick=True,
      doc="debug log records the inline box with the requested size")

  def inside(ctx):
    return "%d inline elems inside box" % check_inline_inside(
        compile_inline(ctx))
  add("t1.place.inline_elems_inside_box", "1", GROUP, inside,
      doc="every inline-* elem bbox lies inside its logged box")

  def clear(ctx):
    check_inline_box_clear(ctx, compile_inline(ctx))
  add("t1.place.inline_box_clear_of_text", "1", GROUP, clear,
      doc="inline box intersects no word box (neighbouring lines, caption)")

  def pix(ctx):
    on = compile_inline(ctx)
    off = compile_inline(ctx, off=True)
    H.check_overlap_pixels(ctx, on, off)
  add("t1.place.inline_text_untouched", "1", GROUP, pix, quick=True,
      doc="pixel diff on/off: paragraphs and caption untouched")

  def confined(ctx):
    on = compile_inline(ctx, setup=NONE)
    off = compile_inline(ctx, setup=NONE, off=True)
    boxes = need_inline(on)
    page, _, b = boxes[0]
    px, scale, ph, _ = H.diff_pixels(ctx, on, off, page, dpi=50)
    r = H.bp_to_px(b, scale, ph, pad=2)
    inside_n = sum(1 for p in px if H.in_px_rect(p, r))
    out_n = len(px) - inside_n
    area = max(1.0, (r[2] - r[0]) * (r[3] - r[1]))
    if inside_n < 0.01 * area:
      raise Fail("inline spray paints too little inside its box (%d px of "
                 "%.0f)" % (inside_n, area))
    if out_n > max(10, 0.01 * len(px)):
      raise Fail("%d decoration px outside the inline box (regions=none)" %
                 out_n)
    return "%d px inside, %d outside" % (inside_n, out_n)
  add("t1.place.inline_paint_confined_to_box", "1", GROUP, confined,
      doc="regions=none: all painted pixels are inside the inline box")

  for mot, rx in (("bamboo", api.MOTIF_KINDS["bamboo"]),
                  ("ume", api.MOTIF_KINDS["ume"])):
    def f(ctx, mot=mot, rx=rx):
      r = compile_inline(ctx, spray_cmd=spray(width=r"0.6\linewidth",
                                              height="45mm", seed=7,
                                              **{api.MOTIF_KEY: mot}))
      check_inline_inside(r)
      kinds = {e.kind for e in r.elems
               if re.search(api.INLINE_KIND, e.kind, re.I)}
      if not any(re.search(rx, k, re.I) for k in kinds):
        raise Fail("inline motif=%s: no inline kind matches /%s/: %s" % (
            mot, rx, sorted(kinds)[:10]))
    add("t1.place.inline_motif[%s]" % mot, "1", GROUP, f,
        doc="inline spray honours motif=%s" % mot)


# ----------------------------- tier 1: spawn -------------------------------
CORNERS = ["tl", "tr", "bl", "br"]
EDGES = ["tc", "bc", "ml", "mr"]


def _tier1_spawn(add):
  for at in CORNERS + EDGES:
    def f(ctx, at=at):
      r = compile_pages(ctx, p1=anchor_cmd(at), setup=NONE)
      sp = need_spawns(r, 1, page=1)
      need_drawn(sp)
      s = sp[0]
      w, h = H.page_sizes(r.pdf)[0]
      ax, ay = H.anchor_point(at, w, h)
      if H.point_rect_dist(s.origin, (ax, ay, ax, ay)) > 1.0:
        raise Fail("at=%s: logged origin %s, expected anchor (%.1f, %.1f)" % (
            at, s.origin, ax, ay))
      near = near_origin(r, s)
      if not near:
        raise Fail("at=%s: no elem within %.0f mm of the origin" % (
            at, api.SPAWN_NEAR_MM))
      els = page_elems(r, 1)
      c = H.center(H.union(e.bbox for e in els))
      if not quadrant_ok(at, c, w, h):
        raise Fail("at=%s: decoration centred at (%.0f, %.0f), not on the "
                   "anchor's side of the %.0fx%.0f page" % (at, c[0], c[1], w,
                                                             h))
      return "%d elems, %d near origin" % (len(els), len(near))
    add("t1.place.spawn_anchor[%s]" % at, "1", GROUP, f, quick=at == "br",
        doc="\\kachoSpawn at=%s: logged, drawn near the anchor" % at)

  def long_names(ctx):
    r = compile_pages(ctx, p1=spawn(at=api.ANCHOR_LONG["tr"], seed=3,
                                    size="60mm"), setup=NONE)
    s = need_spawns(r, 1, page=1)[0]
    w, h = H.page_sizes(r.pdf)[0]
    if H.point_rect_dist(s.origin, (w, h, w, h)) > 1.0:
      raise Fail("at=%s: origin %s, expected (%.1f, %.1f)" % (
          api.ANCHOR_LONG["tr"], s.origin, w, h))
  add("t1.place.spawn_long_anchor_name", "1", GROUP, long_names,
      doc="long anchor names (top-right) resolve like the short ones")

  def offsets(ctx):
    r = compile_pages(ctx, p1=defs(spawn(at="bl", dx="30mm", dy="40mm",
                                         seed=4, size="60mm"),
                                   spawn(at="tr", dx="-20mm", dy="-30mm",
                                         seed=5, size="60mm")), setup=NONE)
    sp = sorted(need_spawns(r, 2, page=1), key=lambda s: s.index)
    w, h = H.page_sizes(r.pdf)[0]
    exp = [(api.DX_SIGN * 30 * MM, api.DY_SIGN * 40 * MM),
           (w - api.DX_SIGN * 20 * MM, h - api.DY_SIGN * 30 * MM)]
    for s, (ex, ey) in zip(sp, exp):
      if abs(s.origin[0] - ex) > 1.5 or abs(s.origin[1] - ey) > 1.5:
        raise Fail("spawn %d at=%s: origin %s, expected (%.1f, %.1f) from "
                   "dx/dy" % (s.index, s.at, s.origin, ex, ey))
    for s in sp:
      if not near_origin(r, s):
        raise Fail("spawn %d: nothing drawn near offset origin %s" % (
            s.index, s.origin))
  add("t1.place.spawn_offsets", "1", GROUP, offsets,
      doc="dx/dy offsets move the logged origin and the drawing")

  def from_text(ctx):
    r = compile_pages(ctx, p1=spawn(at="tr", **{"from": "text"}, dx="10mm",
                                    seed=6, size="50mm"), setup=NONE)
    s = need_spawns(r, 1, page=1)[0]
    els = page_elems(r, 1)
    tb = els[0].tb if els else None
    if tb is None:
      raise Fail("nothing drawn for from=text spawn")
    ex = tb[2] + api.DX_SIGN * 10 * MM
    if abs(s.origin[0] - ex) > 2.0:
      raise Fail("from=text at=tr dx=10mm: origin x %.1f, expected text "
                 "block right %.1f + 10mm = %.1f" % (s.origin[0], tb[2], ex))
  add("t1.place.spawn_from_text", "1", GROUP, from_text,
      doc="from=text anchors relative to the text block")

  def angle(ctx):
    a = compile_pages(ctx, p1=spawn(at="bl", dx="15mm", dy="15mm", angle=0,
                                    size="90mm", seed=8), setup=NONE)
    b = compile_pages(ctx, p1=spawn(at="bl", dx="15mm", dy="15mm", angle=90,
                                    size="90mm", seed=8), setup=NONE)
    sa, sb = need_spawns(a, 1)[0], need_spawns(b, 1)[0]
    if abs(sa.angle - 0) > 0.5 or abs(sb.angle - 90) > 0.5:
      raise Fail("logged angles %.1f / %.1f, expected 0 / 90" % (sa.angle,
                                                                   sb.angle))
    ua = H.union(e.bbox for e in page_elems(a, 1))
    ub = H.union(e.bbox for e in page_elems(b, 1))
    if not ua or not ub:
      raise Fail("nothing drawn")
    ra = (ua[2] - ua[0]) / max(1.0, ua[3] - ua[1])
    rb = (ub[2] - ub[0]) / max(1.0, ub[3] - ub[1])
    if not ra > rb:
      raise Fail("angle=0 (w/h %.2f) should be wider than angle=90 (w/h "
                 "%.2f)" % (ra, rb))
    return "w/h %.2f vs %.2f" % (ra, rb)
  add("t1.place.spawn_angle", "1", GROUP, angle,
      doc="angle= is logged and steers growth (0 wide, 90 tall)")

  def size(ctx):
    a = compile_pages(ctx, p1=spawn(at="br", size="40mm", seed=9), setup=NONE)
    b = compile_pages(ctx, p1=spawn(at="br", size="120mm", seed=9),
                      setup=NONE)
    sa, sb = need_spawns(a, 1)[0], need_spawns(b, 1)[0]
    if abs(sa.size - 40 * MM) > 1.5 or abs(sb.size - 120 * MM) > 1.5:
      raise Fail("logged sizes %.1f / %.1f bp, expected %.1f / %.1f" % (
          sa.size, sb.size, 40 * MM, 120 * MM))

    def reach(r, s):
      """Largest axis distance from the origin to any drawn bbox edge."""
      return max([0.0] + [max(abs(e.bbox[0] - s.origin[0]),
                              abs(e.bbox[2] - s.origin[0]),
                              abs(e.bbox[1] - s.origin[1]),
                              abs(e.bbox[3] - s.origin[1]))
                          for e in page_elems(r, 1)])
    ra, rb = reach(a, sa), reach(b, sb)
    if not 0 < ra < rb:
      raise Fail("reach from origin: size=40mm %.0f bp, size=120mm %.0f bp" %
                 (ra, rb))
    if ra > 40 * MM * 1.3 + 15:
      raise Fail("size=40mm drawing reaches %.0f bp from its origin" % ra)
    return "reach %.0f < %.0f bp" % (ra, rb)
  add("t1.place.spawn_size", "1", GROUP, size,
      doc="size= is logged and bounds the drawing's reach")

  for mot in ("bamboo", "maple"):
    def m(ctx, mot=mot):
      r = compile_pages(ctx, p1=spawn(at="bl", size="80mm", seed=12,
                                      **{api.MOTIF_KEY: mot}), setup=NONE)
      need_drawn(need_spawns(r, 1))
      kinds = {e.kind for e in page_elems(r, 1)}
      if not any(re.search(api.MOTIF_KINDS[mot], k, re.I) for k in kinds):
        raise Fail("spawn motif=%s: kinds %s" % (mot, sorted(kinds)[:10]))
    add("t1.place.spawn_motif[%s]" % mot, "1", GROUP, m,
        doc="\\kachoSpawn motif=%s draws that motif" % mot)

  def spawn_list(ctx):
    cmds = defs(*(anchor_cmd(a, seed=20 + i, size="55mm")
                  for i, a in enumerate(("tl", "tr", "br"))))
    r = compile_pages(ctx, p1=cmds, setup=NONE)
    sp = need_spawns(r, 3, page=1)
    need_drawn(sp)
    idx = sorted(s.index for s in sp)
    if idx != [1, 2, 3]:
      raise Fail("spawn indices %s, expected [1, 2, 3]" % idx)
    lonely = [s.at for s in sp if not near_origin(r, s)]
    if lonely:
      raise Fail("no elems near spawn(s) %s" % lonely)
  add("t1.place.spawn_list", "1", GROUP, spawn_list, quick=True,
      doc="three \\kachoSpawn calls on a page give three drawn items")

  def none_keeps_user(ctx):
    r = compile_pages(ctx, p1=anchor_cmd("bl"), setup=NONE)
    s = need_spawns(r, 1)[0]
    far = [e for e in page_elems(r, 1)
           if H.point_rect_dist(s.origin, e.bbox) > 0.45 * max(
               H.page_sizes(r.pdf)[0])]
    if far:
      raise Fail("regions=none + spawn at bl: %d elem(s) far from the spawn "
                 "(layout not suppressed?): %s" % (len(far), far[0].kind))
  add("t1.place.regions_none_keeps_user_items", "1", GROUP, none_keeps_user,
      doc="regions=none suppresses the layout but keeps user spawns")

  def safe(ctx):
    on = compile_pages(ctx, p1=defs(*(anchor_cmd(a) for a in CORNERS + EDGES)))
    off = compile_pages(ctx, p1=defs(*(anchor_cmd(a) for a in CORNERS +
                                       EDGES)), off=True)
    check_safe(ctx, on, off)
  add("t1.place.spawn_all_anchors_safe", "1", GROUP, safe,
      doc="8 spawns + auto layout: no text overlap, 5 mm edge zone kept")


# ----------------------------- tier 1: regions -----------------------------
def _tier1_regions(add):
  def none(ctx):
    r = compile_pages(ctx, setup=NONE)
    H.need_ok(r)
    if r.elems:
      raise Fail("regions=none: %d elems logged" % len(r.elems))
    H.check_no_decor(ctx, r, list(range(1, r.pages + 1)))
  add("t1.place.regions_none", "1", GROUP, none, quick=True,
      doc="regions=none: nothing painted, nothing logged")

  def frame_log(ctx):
    return check_four_sides(compile_pages(ctx, setup=regions_kw("frame")))
  add("t1.place.regions_frame_four_sides", "1", GROUP, frame_log, quick=True,
      doc="regions=frame: elems on all four sides of the text block")

  def frame_pix(ctx):
    on = compile_pages(ctx, setup=regions_kw("frame"))
    off = compile_pages(ctx, setup=regions_kw("frame"), off=True)
    c, n = pixel_sides(ctx, on, off)
    miss = [k for k, v in c.items() if v < 20]
    if miss:
      raise Fail("regions=frame: little paint on side(s) %s (px %s)" % (miss,
                                                                         c))
    check_safe(ctx, on, off)
    return "px %s of %d" % (c, n)
  add("t1.place.regions_frame_pixels", "1", GROUP, frame_pix,
      doc="regions=frame: paint on all four sides, text untouched")

  def corners_log(ctx):
    r = compile_pages(ctx, setup=regions_kw("corners"))
    els = page_elems(r, 1, skip_exempt=True)
    if not els:
      raise Fail("regions=corners: no (non-bleed) elems on page 1")
    tb = els[0].tb
    bad = [e for e in els if not in_corner(*H.center(e.bbox), tb, 10 * MM)]
    if bad:
      raise Fail("%d elem(s) centred outside the corner zones: %s" % (
          len(bad), "; ".join("%s %s" % (e.kind, H._fmt(e.bbox))
                              for e in bad[:4])))
  add("t1.place.regions_corners_log", "1", GROUP, corners_log,
      doc="regions=corners: elems only in the corner zones")

  def corners_pix(ctx):
    on = compile_pages(ctx, setup=regions_kw("corners"))
    off = compile_pages(ctx, setup=regions_kw("corners"), off=True)
    els = page_elems(on, 1)
    if not els:
      raise Fail("nothing drawn")
    tb = els[0].tb
    px, scale, ph, _ = H.diff_pixels(ctx, on, off, 1, dpi=40)
    if not px:
      raise Fail("regions=corners: no paint")
    ok = 0
    for x, y in px:
      bx, by = x / scale, ph - y / scale
      ok += in_corner(bx, by, tb, 10 * MM)
    if ok < 0.85 * len(px):
      raise Fail("only %.0f%% of paint in corner zones" % (100.0 * ok /
                                                           len(px)))
    return "%.0f%% in corners" % (100.0 * ok / len(px))
  add("t1.place.regions_corners_pixels", "1", GROUP, corners_pix,
      doc="regions=corners: >=85% of painted pixels in corner zones")

  for side in ("top", "bottom", "left", "right"):
    def f(ctx, side=side):
      r = compile_pages(ctx, setup=regions_kw(side))
      els = page_elems(r, 1, skip_exempt=True)
      if not els:
        raise Fail("regions=%s: no (non-bleed) elems" % side)
      tb, s = els[0].tb, 5 * MM
      test = {"top": lambda c: c[1] > tb[3] - s,
              "bottom": lambda c: c[1] < tb[1] + s,
              "left": lambda c: c[0] < tb[0] + s,
              "right": lambda c: c[0] > tb[2] - s}[side]
      bad = [e for e in els if not test(H.center(e.bbox))]
      if bad:
        raise Fail("regions=%s: %d elem(s) elsewhere: %s" % (
            side, len(bad), "; ".join("%s %s" % (e.kind, H._fmt(e.bbox))
                                      for e in bad[:3])))
    add("t1.place.regions_side[%s]" % side, "1", GROUP, f,
        quick=side == "top", doc="regions=%s: elems only in that band" % side)

  def regset(ctx):
    r = compile_pages(ctx, setup=regions_kw("{left,top}"))
    els = page_elems(r, 1, skip_exempt=True)
    if not els:
      raise Fail("regions={left,top}: no elems")
    tb, s = els[0].tb, 5 * MM
    bad = [e for e in els if not (H.center(e.bbox)[0] < tb[0] + s or
                                  H.center(e.bbox)[1] > tb[3] - s)]
    if bad:
      raise Fail("%d elem(s) neither left nor top: %s" % (
          len(bad), bad[0].kind))
  add("t1.place.regions_set_left_top", "1", GROUP, regset,
      doc="regions={left,top}: elems only in those bands")

  def border(ctx):
    on = compile_pages(ctx, pkg="seed=21,layout=%s" % api.BORDER_FRAME_LAYOUT)
    off = compile_pages(ctx, pkg="seed=21,layout=%s" %
                        api.BORDER_FRAME_LAYOUT, off=True)
    info = check_four_sides(on)
    check_safe(ctx, on, off)
    return info
  add("t1.place.border_frame_layout", "1", GROUP, border,
      doc="layout=border-frame: vine on all four sides, safe")

  def bad_value(ctx):
    r = compile_pages(ctx, setup=regions_kw("bogus"))
    if raw_tb(r):
      raise Fail("regions=bogus gives a raw Lua traceback, not a kacho "
                 "diagnostic")
    if not H.kacho_diagnostic(r.log):
      raise Fail("regions=bogus: no 'Package kacho Error/Warning' in log")
  add("t1.place.regions_bad_value_diagnostic", "1", GROUP, bad_value,
      doc="regions=bogus: clean Package kacho Error/Warning")


def raw_tb(r):
  return H.raw_lua_traceback(r.log)


# ----------------------------- tier 1: per page ----------------------------
def _tier1_perpage(add):
  def p2_none(ctx):
    r = compile_pages(ctx, p2=page_cmd(**regions_kw("none")))
    H.need_ok(r)
    if any(e.page == 2 for e in r.elems):
      raise Fail("elems logged on page 2 despite regions=none")
    H.check_no_decor(ctx, r, [2])
    H.check_decor(ctx, r, pages=[1, 3], all_pages=True)
  add("t1.place.thispage_regions_none", "1", GROUP, p2_none, quick=True,
      doc="\\kachoThisPage{regions=none}: only page 2 undecorated")

  def p2_frame(ctx):
    return check_four_sides(compile_pages(ctx, p2=page_cmd(
        **regions_kw("frame"))), page=2)
  add("t1.place.thispage_regions_frame", "1", GROUP, p2_frame,
      doc="\\kachoThisPage{regions=frame}: page 2 framed on four sides")

  def global_none_page_auto(ctx):
    r = compile_pages(ctx, setup=NONE, p2=page_cmd(**regions_kw("auto")))
    H.need_ok(r)
    if any(e.page in (1, 3) for e in r.elems):
      raise Fail("global regions=none ignored on pages 1/3")
    if not any(e.page == 2 for e in r.elems):
      raise Fail("per-page regions=auto did not re-enable page 2")
  add("t1.place.thispage_overrides_global", "1", GROUP,
      global_none_page_auto,
      doc="global regions=none + page-2 regions=auto: only page 2 drawn")

  def shorthand(ctx):
    r = compile_pages(ctx, setup=NONE, p2=page_cmd(
        **{api.SPAWN_KEY: "{br@125; tl@-45}"}))
    sp = need_spawns(r, 2, page=2)
    need_drawn(sp)
    w, h = H.page_sizes(r.pdf)[1]
    want = {"br": (w, 0.0), "tl": (0.0, h)}
    for s in sp:
      key = next((k for k in want if H.point_rect_dist(
          s.origin, want[k] * 2) <= 1.0), None)
      if key is None:
        raise Fail("shorthand spawn origin %s is not at br/tl" % (s.origin,))
      if not near_origin(r, s):
        raise Fail("nothing drawn near shorthand spawn %s" % key)
    if any(s.page != 2 for s in H.user_spawns(r)):
      raise Fail("shorthand spawns leaked onto other pages")
  add("t1.place.spawn_shorthand", "1", GROUP, shorthand,
      doc="spawn={br@125; tl@-45} per page: two drawn spawns on page 2")

  for mot, other in (("bamboo", None), ("maple", "ume")):
    def f(ctx, mot=mot, other=other):
      r = compile_pages(ctx, pkg="seed=21,theme=haru",
                        p2=page_cmd(**{api.MOTIF_KEY: mot}))
      kinds = {e.kind for e in page_elems(r, 2)}
      if not any(re.search(api.MOTIF_KINDS[mot], k, re.I) for k in kinds):
        raise Fail("page-2 motif=%s: kinds %s" % (mot, sorted(kinds)[:10]))
      if other and any(re.search(api.MOTIF_KINDS[other], k, re.I)
                       for k in kinds):
        raise Fail("page-2 motif=%s still draws the theme motif %s" % (
            mot, other))
    add("t1.place.thispage_motif[%s]" % mot, "1", GROUP, f,
        doc="\\kachoThisPage{motif=%s} forces page 2's motif" % mot)

  def global_motif(ctx):
    r = compile_pages(ctx, setup={api.MOTIF_KEY: "wisteria"})
    kinds = {e.kind for e in H.need_elems(r)}
    if not any(re.search(api.MOTIF_KINDS["wisteria"], k, re.I)
               for k in kinds):
      raise Fail("\\kachosetup{motif=wisteria}: kinds %s" % sorted(kinds)[:10])
  add("t1.place.setup_motif", "1", GROUP, global_motif,
      doc="\\kachosetup{motif=wisteria} applies to the document")

  def unknown_motif(ctx):
    r = compile_pages(ctx, setup={api.MOTIF_KEY: "dragonfruit"})
    H.need_ok(r)
    if not re.search(r"Package kacho Warning", r.log):
      raise Fail("unknown motif: no 'Package kacho Warning'")
    H.check_decor(ctx, r)
  add("t1.place.unknown_motif_warns", "1", GROUP, unknown_motif,
      doc="unknown motif name: one warning, theme default still drawn")


# ----------------------------- tier 1: determinism -------------------------
def _tier1_det(add):
  def same(ctx):
    a = compile_pages(ctx, p1=anchor_cmd("br", seed=5), rep=1)
    b = compile_pages(ctx, p1=anchor_cmd("br", seed=5), rep=2)
    d = H.renders_equal(ctx, a, b)
    if d:
      raise Fail("same spawn seed renders differently on pages %s" % d)
  add("t1.place.det_spawn_same_seed", "1", GROUP, same, quick=True,
      doc="user spawn: same seed -> identical renders")

  def differ(ctx):
    a = compile_pages(ctx, p1=anchor_cmd("br", seed=5), setup=NONE)
    b = compile_pages(ctx, p1=anchor_cmd("br", seed=6), setup=NONE)
    if 1 not in H.renders_equal(ctx, a, b):
      raise Fail("spawn seed 5 and 6 render identically")
  add("t1.place.det_spawn_seed_differs", "1", GROUP, differ,
      doc="user spawn: different seed -> different drawing")

  def isolated(ctx):
    a = compile_pages(ctx, p1=anchor_cmd("br", seed=5, size="60mm"))
    b = compile_pages(ctx, p1=anchor_cmd("br", seed=6, size="60mm"))
    sa = need_spawns(a, 1)[0]
    px, scale, ph, _ = H.diff_pixels(ctx, a, b, 1, dpi=40)
    reach = (60 * 1.3 + 15) * MM * scale
    ox, oy = sa.origin[0] * scale, (ph - sa.origin[1]) * scale
    far = [p for p in px if ((p[0] - ox) ** 2 + (p[1] - oy) ** 2) ** 0.5 >
           reach]
    if len(far) > max(10, 0.01 * len(px)):
      raise Fail("changing only the spawn seed changed %d px far from the "
                 "spawn (layout not isolated)" % len(far))
    for p in (2, 3):
      if p in H.renders_equal(ctx, a, b):
        raise Fail("changing a page-1 spawn seed changed page %d" % p)
  add("t1.place.det_spawn_seed_isolated", "1", GROUP, isolated,
      doc="spawn seed change only alters pixels within the spawn's reach")

  def inline_same(ctx):
    a = compile_inline(ctx, rep=1)
    b = compile_inline(ctx, rep=2)
    d = H.renders_equal(ctx, a, b)
    if d:
      raise Fail("same inline seed renders differently on pages %s" % d)
  add("t1.place.det_inline_same_seed", "1", GROUP, inline_same,
      doc="inline spray: same seed -> identical renders")

  def inline_isolated(ctx):
    a = compile_inline(ctx, spray_cmd=spray(width=r"0.6\linewidth",
                                            height="45mm", seed=7))
    b = compile_inline(ctx, spray_cmd=spray(width=r"0.6\linewidth",
                                            height="45mm", seed=8))
    page, _, box = need_inline(a)[0]
    px, scale, ph, _ = H.diff_pixels(ctx, a, b, page, dpi=40)
    if not px:
      raise Fail("inline seed 7 vs 8 render identically")
    r = H.bp_to_px(box, scale, ph, pad=2)
    out = [p for p in px if not H.in_px_rect(p, r)]
    if len(out) > max(10, 0.01 * len(px)):
      raise Fail("inline seed change altered %d px outside its box" %
                 len(out))
  add("t1.place.det_inline_seed_isolated", "1", GROUP, inline_isolated,
      doc="inline seed change alters only pixels inside its box")


# ----------------------------- tier 2: boundaries --------------------------
def _scen():
  # name: (kind, kwargs for compile_pages/compile_inline, expect_drawn)
  # expect_drawn: True -> some user item/decoration must be drawn;
  #               None -> optional (no room), safety still required.
  W = r"\linewidth"
  return {
      "spawn-center": ("pages", dict(p1=spawn(at="c", seed=31, size="80mm")),
                       None),
      "spawn-offpaper": ("pages", dict(p1=spawn(at="bl", dx="-30mm",
                                                dy="-30mm", seed=32)), None),
      "spawn-tiny": ("pages", dict(p1=spawn(at="br", size="1mm", seed=33)),
                     None),
      "spawn-huge": ("pages", dict(p1=spawn(at="br", size="500mm", seed=34)),
                     True),
      "spawn-angle-wrap": ("pages", dict(p1=spawn(at="tl", angle=-405,
                                                  seed=35)), True),
      "spawn-into-text": ("pages", dict(p1=spawn(at="ml", angle=0,
                                                 size="200mm", seed=36)),
                          None),
      "spawn-many": ("pages", dict(p1=defs(*(
          [anchor_cmd(a, seed=40 + i) for i, a in enumerate(CORNERS + EDGES)]
          + [spawn(at="bl", dx="15mm", dy="60mm", seed=50),
             spawn(at="tr", dx="-60mm", dy="-10mm", seed=51)]))), True),
      "spawn-a5-landscape": ("pages", dict(p1=anchor_cmd("tr"),
                                           cls="a5paper,landscape",
                                           geom=""), True),
      "spawn-narrow-margins": ("pages", dict(p1=anchor_cmd("br"),
                                             geom="margin=1cm"), None),
      "spawn-twoside-outer": ("pages", dict(
          p1=spawn(at="outer-top", seed=37), p2=spawn(at="outer-top",
                                                      seed=38),
          cls="twoside"), True),
      "inline-tiny": ("inline", dict(spray_cmd=spray(width="10mm",
                                                     height="10mm", seed=3)),
                      None),
      "inline-fullwidth": ("inline", dict(spray_cmd=spray(
          width=W, height="80mm", seed=4)), True),
      "inline-twocolumn": ("inline", dict(cls="twocolumn"), True),
      "inline-minipage": ("inline", dict(spray_cmd=(
          r"\begin{minipage}{0.5\linewidth}" +
          spray(width=W, height="30mm", seed=5) + r"\end{minipage}")), True),
      "inline-multi": ("inline", dict(spray_b=spray(width=r"0.4\linewidth",
                                                    height="25mm",
                                                    seed=9)), True),
      "inline-a5": ("inline", dict(cls="a5paper"), True),
      "inline-from-left": ("inline", dict(spray_cmd=spray(
          width=r"0.7\linewidth", height="40mm", seed=6, **{"from": "left"})),
                           True),
      "frame-a5": ("pages", dict(setup=regions_kw("frame"), cls="a5paper",
                                 geom=""), True),
      "frame-narrow-margins": ("pages", dict(setup=regions_kw("frame"),
                                             geom="margin=1cm"), None),
      "corners-letter": ("pages", dict(setup=regions_kw("corners"),
                                       cls="letterpaper"), True),
      "border-frame-landscape": ("pages", dict(
          pkg="seed=21,layout=%s" % api.BORDER_FRAME_LAYOUT,
          cls="a4paper,landscape", geom=""), True),
      "none-with-user-items": ("inline", dict(
          setup=NONE, spray_b=spray(width=r"0.4\linewidth", height="25mm",
                                    seed=9)), True),
  }


def _tier2(add):
  for name, (kind, kw, expect) in _scen().items():
    fn = compile_pages if kind == "pages" else compile_inline

    def res(ctx, off=False, fn=fn, kw=kw):
      return fn(ctx, off=off, **kw)

    def t_compile(ctx, res=res, kind=kind, expect=expect):
      r = res(ctx)
      H.need_ok(r)
      if kind == "inline":
        need_inline(r)
      elif expect and not H.user_spawns(r) and not r.elems:
        raise Fail("nothing drawn or logged")
      return "%d page(s), %d elems" % (r.pages, len(r.elems))
    add("t2.place.%s.compile" % name, "2", GROUP, t_compile,
        quick=name in ("spawn-many", "inline-twocolumn"),
        doc="%s: compiles, user item logged" % name)

    def t_log(ctx, res=res, expect=expect, kind=kind):
      r = res(ctx)
      check_safe(ctx, r, allow_empty=expect is None)
      if kind == "inline" and r.elems and any(
          re.search(api.INLINE_KIND, e.kind, re.I) for e in r.elems):
        check_inline_inside(r)
    add("t2.place.%s.safe_log" % name, "2", GROUP, t_log,
        doc="%s: elems off text (inline inside box), 5 mm edge" % name)

    def t_pix(ctx, res=res):
      H.check_overlap_pixels(ctx, res(ctx), res(ctx, off=True))
    add("t2.place.%s.overlap_pixel" % name, "2", GROUP, t_pix,
        doc="%s: word boxes untouched (on vs off)" % name)

  def outer(ctx):
    r = compile_pages(ctx, p1=spawn(at="outer-top", seed=37),
                      p2=spawn(at="outer-top", seed=38), cls="twoside")
    sp = {s.page: s for s in need_spawns(r, 2)}
    if 1 not in sp or 2 not in sp:
      raise Fail("spawns logged on pages %s, expected 1 and 2" % sorted(sp))
    w = H.page_sizes(r.pdf)[0][0]
    if not (sp[1].origin[0] > w / 2 and sp[2].origin[0] < w / 2):
      raise Fail("at=outer-top: origin x p1=%.0f (want right), p2=%.0f "
                 "(want left)" % (sp[1].origin[0], sp[2].origin[0]))
  add("t2.place.spawn-twoside-outer.parity", "2", GROUP, outer,
      doc="twoside at=outer-top resolves right on odd, left on even pages")

  def bad_anchor(ctx):
    r = compile_pages(ctx, p1=spawn(at="nowhere", seed=1))
    if raw_tb(r):
      raise Fail("at=nowhere gives a raw Lua traceback")
    if not H.kacho_diagnostic(r.log):
      raise Fail("at=nowhere: no 'Package kacho Error/Warning'")
  add("t2.place.bad-anchor.diagnostic", "2", GROUP, bad_anchor,
      doc="at=nowhere: clean kacho diagnostic, no Lua traceback")

  def bad_size(ctx):
    r = compile_inline(ctx, spray_cmd=spray(width="0pt", height="0pt",
                                            seed=1))
    if raw_tb(r):
      raise Fail("zero-size inline spray gives a raw Lua traceback")
    if r.ok:
      check_safe(ctx, r, allow_empty=True)
  add("t2.place.inline-zero-size.no_crash", "2", GROUP, bad_size,
      doc="0pt x 0pt inline spray: no crash; nothing unsafe drawn")

  def special(ctx):
    r = compile_inline(ctx, spray_cmd=spray(width=r"0.5\linewidth",
                                            height="30mm", seed=2),
                       pkg="seed=4294967295")
    H.need_ok(r)
    check_inline_inside(r)
  add("t2.place.inline-seed-max.compile", "2", GROUP, special,
      doc="inline spray with document seed 2^32-1 compiles, stays in box")


# ----------------------------- tier 3: pairwise ----------------------------
def _tier3(add):
  import suite  # pylint: disable=g-import-not-at-top
  regions = ["auto", "corners", "frame", "none", "{left,top}"]
  users = ["none", "spawn", "inline", "both"]
  papers = ["a4paper", "a5paper", "letterpaper"]
  palettes = list(api.PALETTES)
  rows = suite.pairwise([regions, users, papers, palettes])
  for n, (reg, usr, pap, pal) in enumerate(rows):
    def f(ctx, reg=reg, usr=usr, pap=pap, pal=pal, n=n):
      pkg = "seed=%d,palette=%s" % (600 + n, pal)
      setup = regions_kw(reg)
      sb = spray(width=r"0.5\linewidth", height="30mm", seed=n + 1)
      sp = anchor_cmd("br", seed=n + 1, size="50mm")
      kw = dict(setup=setup, pkg=pkg, cls=pap)
      if usr in ("inline", "both"):
        # inline fixture; spawn (if any) issued with the second spray
        kw["spray_cmd"] = sb
        if usr == "both":
          kw["spray_b"] = sp
        on = compile_inline(ctx, **kw)
        off = compile_inline(ctx, off=True, **kw)
      else:
        if usr == "spawn":
          kw["p1"] = sp
        on = compile_pages(ctx, **kw)
        off = compile_pages(ctx, off=True, **kw)
      H.need_ok(on)
      if reg == "none" and usr == "none":
        if on.elems:
          raise Fail("regions=none, no user items: %d elems" % len(on.elems))
        H.check_no_decor(ctx, on, list(range(1, on.pages + 1)))
      else:
        check_safe(ctx, on, allow_empty=True)
      if usr in ("inline", "both"):
        check_inline_inside(on)
      if usr in ("spawn", "both"):
        need_drawn(need_spawns(on, 1))
      H.check_overlap_pixels(ctx, on, off)
    add("t3.place.pair[%s,%s,%s,%s]" % (reg, usr, pap.replace("paper", ""),
                                        pal), "3", GROUP, f, quick=n < 1,
        doc="pairwise regions x user items x paper x palette: safe")


# ----------------------------- tier 4: realistic ---------------------------
def _tier4(add):
  essay = defs(hook("KachoRegionsCmd", api.SETUP_CMD % (
      "%s={right,bottom}" % api.REGIONS_KEY)),
               hook("KachoSprayCmd", spray(width=r"0.55\linewidth",
                                           height="50mm", seed=17,
                                           **{api.MOTIF_KEY: "ume"})))
  contents = hook("KachoFrameCmd", page_cmd(**regions_kw("frame")))
  poster = defs(hook("KachoPosterSetup", api.SETUP_CMD % (
      "%s=none" % api.REGIONS_KEY)),
                hook("KachoPosterSpawns", defs(*(
                    spawn(at=a, seed=70 + i, size="45mm")
                    for i, a in enumerate(CORNERS)))))
  docs = [("essay", "t4_place_essay.tex", essay),
          ("contents-frame", "t4_place_contents.tex", contents),
          ("poster-spawns", "t4_place_poster.tex", poster)]
  for name, fx, d in docs:
    def res(ctx, off=False, fx=fx, d=d):
      return H.compile_doc(ctx, fx, pkg_opts="seed=23", defs=d, off=off)

    def t_compile(ctx, res=res):
      r = res(ctx)
      H.need_ok(r)
      return "%d page(s)" % r.pages
    add("t4.place.%s.compile" % name, "4", GROUP, t_compile, quick=True,
        doc="%s: compiles" % name)

    def t_pix(ctx, res=res):
      H.check_overlap_pixels(ctx, res(ctx), res(ctx, off=True))
    add("t4.place.%s.overlap_pixel" % name, "4", GROUP, t_pix,
        doc="%s: text untouched" % name)

    def t_log(ctx, res=res):
      check_safe(ctx, res(ctx))
    add("t4.place.%s.log_text_edge" % name, "4", GROUP, t_log,
        doc="%s: elems off text (inline in box), 5 mm edge" % name)

    def t_feature(ctx, res=res, name=name):
      r = res(ctx)
      if name == "essay":
        check_inline_inside(r)
        check_inline_box_clear(ctx, r)
        tb_els = [e for e in page_elems(r, 1, skip_exempt=True)
                  if not re.search(api.INLINE_KIND, e.kind, re.I)]
        if tb_els:
          tb = tb_els[0].tb
          bad = [e for e in tb_els if not (H.center(e.bbox)[0] > tb[2] - 5 *
                                           MM or H.center(e.bbox)[1] <
                                           tb[1] + 5 * MM)]
          if bad:
            raise Fail("regions={right,bottom}: elem %s elsewhere" %
                       bad[0].kind)
      elif name == "contents-frame":
        return check_four_sides(r, page=1)
      else:
        sp = need_spawns(r, 4)
        need_drawn(sp)
        lonely = [s.at for s in sp if not near_origin(r, s)]
        if lonely:
          raise Fail("nothing drawn near spawn(s) %s" % lonely)
    add("t4.place.%s.feature" % name, "4", GROUP, t_feature,
        doc="%s: the placement feature it showcases works" % name)
