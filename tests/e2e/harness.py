"""Core machinery for the kacho E2E suite (python3 stdlib only).

Provides:
  * Ctx            — run configuration (repo root, scratch dir, env).
  * compile_doc()  — memoised, thread-safe LuaLaTeX compile of a fixture with
                     injected package/class/geometry options.
  * checkout()     — memoised clean-checkout copy + `make` build.
  * PDF helpers    — page sizes, word boxes (pdftotext -bbox), images list,
                     q/Q balance, rendering to PPM/PGM via pdftoppm.
  * Checks         — decoration presence, pixel overlap, debug-log overlap /
                     edge safe zone, banding heuristic.
All checks raise Fail(msg) on failure.
"""

import dataclasses
import glob
import hashlib
import math
import os
import re
import shutil
import subprocess
import threading
import time
import zlib

import api_config as api

TINYTEX_BIN = os.path.expanduser("~/.TinyTeX/bin/x86_64-linux")
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
MM = 72.0 / 25.4  # bp per mm


class Fail(Exception):
  """A test assertion failure (message is shown in the report)."""


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
class Ctx:
  """Global run context; one instance per run."""

  def __init__(self, repo, run_dir, keep=False, verbose=False):
    self.repo = os.path.abspath(repo)
    self.run_dir = run_dir
    self.keep = keep
    self.verbose = verbose
    os.makedirs(run_dir, exist_ok=True)
    self._locks = {}
    self._cache = {}
    self._glock = threading.Lock()

  # -- memoisation -----------------------------------------------------------
  def memo(self, key, fn):
    with self._glock:
      lock = self._locks.setdefault(key, threading.Lock())
    with lock:
      if key not in self._cache:
        try:
          self._cache[key] = ("ok", fn())
        except Exception as e:  # pylint: disable=broad-except
          self._cache[key] = ("err", e)
      kind, val = self._cache[key]
    if kind == "err":
      raise val
    return val

  def tex_env(self, debug=True, extra_texinputs=()):
    env = dict(os.environ)
    env["PATH"] = TINYTEX_BIN + os.pathsep + env.get("PATH", "")
    tin = [os.path.join(self.repo, "tex") + "//", FIXTURES + "//"]
    tin += list(extra_texinputs)
    env["TEXINPUTS"] = os.pathsep.join(tin) + os.pathsep
    env["LUAINPUTS"] = os.path.join(self.repo, "tex") + "//" + os.pathsep
    env["SOURCE_DATE_EPOCH"] = "1700000000"
    env["FORCE_SOURCE_DATE"] = "1"
    for k in ("KACHO_DEBUG", "KACHO_OFF", "KACHO_SEED"):
      env.pop(k, None)
    if debug:
      env.update(api.DEBUG_ENV)
    return env

  def plain_env(self):
    """Environment for running the documented commands (no TinyTeX on PATH,
    no display) — the Makefile must set up the toolchain itself."""
    env = dict(os.environ)
    path = [p for p in env.get("PATH", "").split(os.pathsep)
            if ".TinyTeX" not in p]
    env["PATH"] = os.pathsep.join(path)
    for k in ("DISPLAY", "WAYLAND_DISPLAY", "VIEWER", "TEXINPUTS",
              "LUAINPUTS", "KACHO_DEBUG", "KACHO_OFF", "KACHO_SEED",
              "BROWSER"):
      env.pop(k, None)
    return env


def run(cmd, cwd=None, env=None, timeout=600):
  """Runs a command, returns (rc, combined_output). rc=-9 on timeout."""
  try:
    p = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       stdin=subprocess.DEVNULL, shell=isinstance(cmd, str))
    return p.returncode, p.stdout.decode("utf-8", "replace")
  except subprocess.TimeoutExpired as e:
    out = (e.stdout or b"").decode("utf-8", "replace")
    return -9, out + "\n[TIMEOUT after %ss]" % timeout


def slug(s):
  return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:60] or "doc"


# ---------------------------------------------------------------------------
# Debug log parsing
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class Elem:
  page: int
  kind: str
  bbox: tuple
  tb: tuple


_NUM = r"(-?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
_ELEM_RE = re.compile(
    r"page=(\d+)\s+elem=(\S+)\s+bbox=" + r"\s+".join([_NUM] * 4) +
    r"\s+textblock=" + r"\s+".join([_NUM] * 4))


def parse_kacho_log(text):
  """Returns (elems, bad_lines)."""
  elems, bad = [], []
  for line in text.splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
      continue
    m = _ELEM_RE.search(line)
    if not m:
      bad.append(line)
      continue
    g = m.groups()
    nums = tuple(float(x) for x in g[2:])
    elems.append(Elem(int(g[0]), g[1], nums[0:4], nums[4:8]))
  return elems, bad


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class Compiled:
  ok: bool
  rc: int
  pdf: str
  log: str
  errors: list
  msg: str
  workdir: str
  kacho_log: str = None  # raw text or None if missing
  elems: list = dataclasses.field(default_factory=list)
  bad_log_lines: list = dataclasses.field(default_factory=list)
  pages: int = 0
  seconds: float = 0.0


def tex_errors(log_text):
  """'! ...' error lines with one line of context."""
  lines = log_text.splitlines()
  errs = []
  for i, l in enumerate(lines):
    if l.startswith("!"):
      ctx = " | ".join(x.strip() for x in lines[i:i + 3] if x.strip())
      errs.append(ctx[:300])
  return errs


def doc_class(path):
  with open(path, encoding="utf-8") as f:
    src = f.read()
  m = re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]+)\}", src)
  return m.group(2).strip() if m else "article"


def compile_doc(ctx, fixture, pkg_opts="", class_opts="", geom_opts="",
                defs="", off=False, debug=True, rep=0, timeout=900,
                extra_texinputs=(), tag=None, env=None):
  """Compiles `fixture` (name in fixtures/ or absolute path). Memoised on all
  parameters; `rep` forces an independent recompile (determinism tests).

  off: False | True/"env" (KACHO_OFF=1, the agreed override) | "option"
  (inject the `off` package option). env: extra environment variables.
  """
  if off is True:
    off = "env"
  envt = tuple(sorted((env or {}).items()))
  key = ("compile", fixture, pkg_opts, class_opts, geom_opts, defs, off,
         debug, rep, tuple(extra_texinputs), envt)
  return ctx.memo(key, lambda: _compile(ctx, key, fixture, pkg_opts,
                                        class_opts, geom_opts, defs, off,
                                        debug, timeout, extra_texinputs, tag,
                                        dict(envt)))


def _compile(ctx, key, fixture, pkg_opts, class_opts, geom_opts, defs, off,
             debug, timeout, extra_texinputs, tag, extra_env):
  path = fixture if os.path.isabs(fixture) else os.path.join(FIXTURES, fixture)
  if not os.path.exists(path):
    raise Fail("fixture not found: %s" % path)
  h = hashlib.sha1(repr(key).encode()).hexdigest()[:8]
  name = slug((tag or os.path.splitext(os.path.basename(path))[0]) +
              ("-off" if off else ""))
  job = "%s-%s" % (name, h)
  wd = os.path.join(ctx.run_dir, "compile", job)
  if os.path.isdir(wd):
    shutil.rmtree(wd)
  os.makedirs(wd)
  opts = [o for o in [pkg_opts.strip(" ,"), "off" if off == "option" else ""]
          if o]
  lines = []
  if opts:
    lines.append(r"\PassOptionsToPackage{%s}{kacho}" % ",".join(opts))
  if class_opts:
    lines.append(r"\PassOptionsToClass{%s}{%s}" % (class_opts,
                                                    doc_class(path)))
  if geom_opts:
    lines.append(r"\PassOptionsToPackage{%s}{geometry}" % geom_opts)
  if defs:
    lines.append(defs)
  lines.append(r"\input{%s}" % path)
  with open(os.path.join(wd, job + ".tex"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
  env = ctx.tex_env(debug=debug, extra_texinputs=list(extra_texinputs) +
                    [os.path.dirname(path) + "//"])
  if off == "env":
    env["KACHO_OFF"] = "1"
  env.update(extra_env)
  t0 = time.time()
  rc, out, log = 0, "", ""
  for _ in range(3):
    rc, out = run(["lualatex", "-interaction=nonstopmode", "-halt-on-error",
                   job + ".tex"], cwd=wd, env=env, timeout=timeout)
    logf = os.path.join(wd, job + ".log")
    log = open(logf, encoding="utf-8", errors="replace").read() if (
        os.path.exists(logf)) else out
    if rc != 0 or not re.search(r"Rerun to get|Label\(s\) may have changed|"
                                r"rerunfilecheck.*Rerun|animate Warning.*Rerun|"
                                r"finalize animations", log):
      break
  pdf = os.path.join(wd, job + ".pdf")
  errs = tex_errors(log)
  ok = rc == 0 and os.path.exists(pdf) and not errs
  if ok:
    msg = "ok"
  elif errs:
    msg = errs[0]
  elif rc == -9:
    msg = "timeout"
  elif rc != 0:
    msg = "lualatex rc=%d: %s" % (rc, out.strip().splitlines()[-1:] or "")
  else:
    msg = "no PDF produced"
  res = Compiled(ok, rc, pdf if os.path.exists(pdf) else None, log, errs, msg,
                 wd, seconds=time.time() - t0)
  klog = None
  for cand in [os.path.join(wd, job + api.DEBUG_LOG_SUFFIX)] + glob.glob(
      os.path.join(wd, "*" + api.DEBUG_LOG_SUFFIX)):
    if os.path.exists(cand):
      klog = open(cand, encoding="utf-8", errors="replace").read()
      break
  res.kacho_log = klog
  if klog is not None:
    res.elems, res.bad_log_lines = parse_kacho_log(klog)
  if res.pdf:
    res.pages = len(page_sizes(res.pdf))
  return res


def need_ok(res, allow_no_pdf=False):
  if allow_no_pdf and res.rc == 0 and not res.errors:
    return
  if not res.ok:
    raise Fail("compile failed: %s" % res.msg)


# ---------------------------------------------------------------------------
# Clean checkout + make
# ---------------------------------------------------------------------------
EXCLUDE_DIRS = {"build", ".agents", ".git", "out", "__pycache__", "_minted"}
EXCLUDE_EXT = (".pdf", ".aux", ".log", ".fls", ".fdb_latexmk", ".synctex.gz",
               ".out", ".toc", ".xdv", ".png", ".ppm", ".pgm")


def copy_clean(src, dst):
  for root, dirs, files in os.walk(src):
    rel = os.path.relpath(root, src)
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    os.makedirs(os.path.join(dst, rel), exist_ok=True)
    for fn in files:
      if fn.endswith(EXCLUDE_EXT) or fn.endswith(api.DEBUG_LOG_SUFFIX):
        continue
      shutil.copy2(os.path.join(root, fn), os.path.join(dst, rel, fn))


@dataclasses.dataclass
class Checkout:
  dir: str
  rc: int
  output: str
  examples: list  # stems
  pdfs: dict  # stem -> pdf path or None
  logs: dict  # stem -> log text ('' if missing)


def find_file(root, name):
  for r, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in (".git", ".agents")]
    if name in files:
      return os.path.join(r, name)
  return None


def checkout(ctx):
  return ctx.memo(("checkout",), lambda: _checkout(ctx))


def _checkout(ctx):
  d = os.path.join(ctx.run_dir, "checkout")
  if os.path.isdir(d):
    shutil.rmtree(d)
  copy_clean(ctx.repo, d)
  if not os.path.exists(os.path.join(d, "Makefile")):
    raise Fail("no Makefile in repository root")
  rc, out = run(["make"], cwd=d, env=ctx.plain_env(), timeout=2400)
  stems = sorted(os.path.splitext(os.path.basename(p))[0]
                 for p in glob.glob(os.path.join(d, "examples", "*.tex")))
  pdfs, logs = {}, {}
  for s in stems:
    p = os.path.join(d, "build", s + ".pdf")
    if not os.path.exists(p):
      p = find_file(d, s + ".pdf")
    pdfs[s] = p
    lg = None
    if p:
      cand = os.path.splitext(p)[0] + ".log"
      lg = cand if os.path.exists(cand) else find_file(d, s + ".log")
    logs[s] = open(lg, encoding="utf-8", errors="replace").read() if lg else ""
  return Checkout(d, rc, out, stems, pdfs, logs)


def need_checkout(ctx):
  co = checkout(ctx)
  if co.rc != 0:
    tail = "\n".join(co.output.strip().splitlines()[-4:])
    raise Fail("`make` failed (rc=%d) in clean checkout: %s" % (co.rc, tail))
  return co


_COPY_LOCK = threading.Lock()
_COPY_SEQ = [0]


def private_copy(ctx, tag):
  """Returns (checkout, dir): a fresh, private copy of the built checkout.

  Every test that runs a documented command which writes into the tree
  (`make view`, `make render`, `make clean`, `make animated`) works in its
  own copy, so concurrent tests never share a build directory (the shared
  checkout itself is never written after `make`). Fixes the race where
  `_render_out` copied the checkout while `make view` wrote PNGs into it.
  """
  co = need_checkout(ctx)
  with _COPY_LOCK:
    _COPY_SEQ[0] += 1
    n = _COPY_SEQ[0]
  d = os.path.join(ctx.run_dir, "copies", "%s-%03d" % (slug(tag), n))
  if os.path.isdir(d):
    shutil.rmtree(d)
  shutil.copytree(co.dir, d, symlinks=True)
  return co, d


def example_stems(ctx):
  return sorted(os.path.splitext(os.path.basename(p))[0]
                for p in glob.glob(os.path.join(ctx.repo, "examples", "*.tex")))


def compile_example(ctx, stem, off=False, debug=True, rep=0):
  """Compiles a repository example with the suite's own command (so that
  `off` and KACHO_DEBUG can be injected)."""
  src = os.path.join(ctx.repo, "examples", stem + ".tex")
  if not os.path.exists(src):
    raise Fail("example missing: %s" % src)
  return compile_doc(ctx, src, off=off, debug=debug, rep=rep,
                     extra_texinputs=[os.path.join(ctx.repo, "examples") +
                                      "//"], tag="ex-" + stem, timeout=1800)


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------
def page_sizes(pdf):
  rc, out = run(["pdfinfo", "-f", "1", "-l", "100000", pdf], timeout=120)
  if rc != 0:
    return []
  return [(float(a), float(b)) for a, b in
          re.findall(r"Page\s+\d+\s+size:\s+([\d.]+)\s+x\s+([\d.]+)", out)]


def pdf_images(pdf):
  rc, out = run(["pdfimages", "-list", pdf], timeout=300)
  if rc != 0:
    raise Fail("pdfimages failed: %s" % out[-200:])
  rows = [l for l in out.splitlines()[2:] if l.strip()]
  return rows


_WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)"'
                      r' yMax="([\d.]+)">(.*?)</word>')


def word_boxes(ctx, pdf):
  """List (per page) of [(x0,y0,x1,y1,text)] in pt, origin top-left."""
  def _do():
    out_html = pdf + ".bbox.html"
    rc, out = run(["pdftotext", "-bbox", pdf, out_html], timeout=300)
    if rc != 0:
      raise Fail("pdftotext failed: %s" % out[-200:])
    html = open(out_html, encoding="utf-8", errors="replace").read()
    pages = []
    for chunk in html.split("<page ")[1:]:
      pages.append([(float(a), float(b), float(c), float(d), t)
                    for a, b, c, d, t in _WORD_RE.findall(chunk)])
    return pages
  return ctx.memo(("words", pdf), _do)


def pdf_text(pdf):
  rc, out = run(["pdftotext", "-layout", pdf, "-"], timeout=300)
  return out if rc == 0 else ""


def qQ_balance(pdf):
  """Returns (q_count, Q_count) over content-like Flate streams."""
  data = open(pdf, "rb").read()
  q = qq = 0
  for m in re.finditer(rb"<<(.*?)>>\s*stream\r?\n", data, re.S):
    d = m.group(1)
    if re.search(rb"/Subtype\s*/(Image|Type1C|CIDFontType0C|OpenType)|"
                 rb"/Type\s*/(XRef|ObjStm|Metadata)|/Length[123]\b", d):
      continue
    start = m.end()
    end = data.find(b"endstream", start)
    raw = data[start:end]
    if b"/FlateDecode" in d:
      try:
        raw = zlib.decompressobj().decompress(raw)
      except zlib.error:
        continue
    elif b"/Filter" in d:
      continue
    raw = re.sub(rb"\((?:\\.|[^\\)])*\)", b" ", raw)  # drop literal strings
    q += len(re.findall(rb"(?:^|(?<=[\s\]\)>}]))q(?=[\s\[\(</]|$)", raw))
    qq += len(re.findall(rb"(?:^|(?<=[\s\]\)>}]))Q(?=[\s\[\(</]|$)", raw))
  return q, qq


# ---------------------------------------------------------------------------
# Raster helpers
# ---------------------------------------------------------------------------
class Img:
  """Simple RGB (3 bytes/px) or gray (1 byte/px) raster."""

  def __init__(self, w, h, ch, data):
    self.w, self.h, self.ch, self.data = w, h, ch, data

  def row(self, y):
    n = self.w * self.ch
    return self.data[y * n:(y + 1) * n]


def _read_pnm(path):
  data = open(path, "rb").read()
  toks, i = [], 0
  while len(toks) < 4:
    while data[i:i + 1].isspace():
      i += 1
    if data[i:i + 1] == b"#":
      while data[i:i + 1] not in (b"\n", b""):
        i += 1
      continue
    j = i
    while not data[j:j + 1].isspace():
      j += 1
    toks.append(data[i:j])
    i = j
  i += 1
  magic, w, h = toks[0], int(toks[1]), int(toks[2])
  ch = 3 if magic == b"P6" else 1
  return Img(w, h, ch, data[i:i + w * h * ch])


def render(ctx, pdf, dpi, gray=False, first=None, last=None):
  """Renders pages; returns list of Img (index 0 = first rendered page)."""
  def _do():
    tagd = "r%d%s_%s_%s" % (dpi, "g" if gray else "", first, last)
    outdir = pdf + "." + tagd
    os.makedirs(outdir, exist_ok=True)
    cmd = ["pdftoppm", "-r", str(dpi)]
    if gray:
      cmd.append("-gray")
    if first:
      cmd += ["-f", str(first)]
    if last:
      cmd += ["-l", str(last)]
    cmd += [pdf, os.path.join(outdir, "p")]
    rc, out = run(cmd, timeout=900)
    if rc != 0:
      raise Fail("pdftoppm failed: %s" % out[-200:])
    files = glob.glob(os.path.join(outdir, "p-*.p[pg]m"))
    files.sort(key=lambda f: int(re.search(r"-(\d+)\.p[pg]m$", f).group(1)))
    return [_read_pnm(f) for f in files]
  return ctx.memo(("render", pdf, dpi, gray, first, last), _do)


def render_page(ctx, pdf, page, dpi, gray=False):
  return render(ctx, pdf, dpi, gray, page, page)[0]


def mode_color(img, step=5):
  counts = {}
  d, ch = img.data, img.ch
  n = img.w * img.h
  for i in range(0, n, step):
    o = i * ch
    k = bytes(b >> 3 for b in d[o:o + ch])
    counts[k] = counts.get(k, 0) + 1
  best = max(counts, key=counts.get)
  return tuple((b << 3) + 4 for b in best)


def _box_px(box, scale, w, h, pad=0):
  x0, y0, x1, y1 = box[:4]
  return (max(0, int(math.floor(x0 * scale)) - pad),
          max(0, int(math.floor(y0 * scale)) - pad),
          min(w, int(math.ceil(x1 * scale)) + pad),
          min(h, int(math.ceil(y1 * scale)) + pad))


def decoration_fraction(img, words, page_w_pt, thresh=20):
  """Fraction of page pixels that differ from the dominant paper colour by
  more than `thresh`, excluding word boxes (padded)."""
  scale = img.w / page_w_pt
  mode = mode_color(img)
  ch = img.ch
  excl = [[] for _ in range(img.h)]
  for wb in words:
    x0, y0, x1, y1 = _box_px(wb, scale, img.w, img.h, pad=2)
    for y in range(y0, y1):
      excl[y].append((x0, x1))
  cnt = 0
  for y in range(img.h):
    row = img.row(y)
    ivs = excl[y]
    for x in range(img.w):
      o = x * ch
      if ch == 3:
        dv = max(abs(row[o] - mode[0]), abs(row[o + 1] - mode[1]),
                 abs(row[o + 2] - mode[2]))
      else:
        dv = abs(row[o] - mode[0])
      if dv > thresh:
        if ivs and any(a <= x < b for a, b in ivs):
          continue
        cnt += 1
  return cnt / float(img.w * img.h)


def decoration_pixels(img, words, page_w_pt, thresh=20):
  """List of (r,g,b) decoration pixels (sampled), same masking as above."""
  scale = img.w / page_w_pt
  mode = mode_color(img)
  excl = [[] for _ in range(img.h)]
  for wb in words:
    x0, y0, x1, y1 = _box_px(wb, scale, img.w, img.h, pad=2)
    for y in range(y0, y1):
      excl[y].append((x0, x1))
  px = []
  for y in range(0, img.h, 2):
    row = img.row(y)
    for x in range(0, img.w, 2):
      o = x * 3
      c = (row[o], row[o + 1], row[o + 2])
      if max(abs(c[0] - mode[0]), abs(c[1] - mode[1]),
             abs(c[2] - mode[2])) > thresh:
        if excl[y] and any(a <= x < b for a, b in excl[y]):
          continue
        px.append(c)
  return px


def saturation(c):
  mx, mn = max(c), min(c)
  return 0.0 if mx == 0 else (mx - mn) / float(mx)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
DECOR_DPI = 40
DECOR_MIN_FRAC = 0.001


def page_decor_fracs(ctx, res, pages=None):
  need_ok(res)
  sizes = page_sizes(res.pdf)
  words = word_boxes(ctx, res.pdf)
  imgs = render(ctx, res.pdf, DECOR_DPI)
  pages = pages or list(range(1, len(imgs) + 1))
  out = {}
  for p in pages:
    if p > len(imgs):
      continue
    out[p] = decoration_fraction(imgs[p - 1], words[p - 1] if p <= len(words)
                                 else [], sizes[p - 1][0])
  return out


def check_decor(ctx, res, pages=None, min_frac=DECOR_MIN_FRAC, all_pages=False):
  fr = page_decor_fracs(ctx, res, pages)
  hits = [p for p, f in fr.items() if f >= min_frac]
  summary = ", ".join("p%d=%.4f" % (p, f) for p, f in sorted(fr.items())[:8])
  if all_pages and len(hits) != len(fr):
    raise Fail("pages without decoration: %s (fractions %s)" % (
        sorted(set(fr) - set(hits)), summary))
  if not hits:
    raise Fail("no decoration pixels outside text (fraction < %.3f): %s" % (
        min_frac, summary))
  return fr


def check_no_decor(ctx, res, pages, max_frac=0.0005):
  fr = page_decor_fracs(ctx, res, pages)
  bad = {p: f for p, f in fr.items() if f > max_frac}
  if bad:
    raise Fail("unexpected decoration on pages %s" % (
        ", ".join("p%d=%.4f" % kv for kv in sorted(bad.items()))))


def renders_equal(ctx, a, b, dpi=40, pages=None):
  """Returns list of page numbers whose rasters differ (or page-count diff)."""
  need_ok(a)
  need_ok(b)
  ia, ib = render(ctx, a.pdf, dpi), render(ctx, b.pdf, dpi)
  if len(ia) != len(ib):
    return ["page-count %d vs %d" % (len(ia), len(ib))]
  idx = pages or range(1, len(ia) + 1)
  return [p for p in idx if ia[p - 1].data != ib[p - 1].data]


def check_words_same(ctx, on, off, tol=0.6):
  wa, wb = word_boxes(ctx, on.pdf), word_boxes(ctx, off.pdf)
  if len(wa) != len(wb):
    raise Fail("page count differs with decoration on/off: %d vs %d" % (
        len(wa), len(wb)))
  for p, (la, lb) in enumerate(zip(wa, wb), 1):
    if len(la) != len(lb):
      raise Fail("page %d: word count differs on/off (%d vs %d): decoration "
                 "changes typesetting" % (p, len(la), len(lb)))
    for a, b in zip(la, lb):
      if a[4] != b[4] or max(abs(a[i] - b[i]) for i in range(4)) > tol:
        raise Fail("page %d: word %r moved/changed on vs off (%s vs %s)" % (
            p, b[4], a[:4], b[:4]))


OVERLAP_DPI = 72


def check_overlap_pixels(ctx, on, off, pages=None, max_pages=12):
  """Decoration must not alter pixels inside body-text word boxes.

  Model: with decoration, a word-box pixel must equal the undecorated pixel
  multiplied by a (locally uniform) paper tint m (estimated as the median
  of decorated pixels where the undecorated page is white). Allowed tint
  covers a paper colour wash; anything non-uniform (strokes, petals, wash
  edges) inside a word box fails.
  """
  need_ok(on)
  need_ok(off)
  check_words_same(ctx, on, off)
  words = word_boxes(ctx, off.pdf)
  sizes = page_sizes(off.pdf)
  n = len(words)
  if pages is None:
    pages = list(range(1, n + 1))
    if len(pages) > max_pages:
      step = max(1, n // (max_pages - 3))
      pages = sorted(set([1, 2, 3, n] + list(range(1, n + 1, step))))
  bad_boxes = []
  checked = 0
  for p in pages:
    io = render_page(ctx, off.pdf, p, OVERLAP_DPI)
    idc = render_page(ctx, on.pdf, p, OVERLAP_DPI)
    if (io.w, io.h) != (idc.w, idc.h):
      raise Fail("page %d raster size differs on/off" % p)
    scale = io.w / sizes[p - 1][0]
    for wb in words[p - 1]:
      x0, y0, x1, y1 = _box_px(wb, scale, io.w, io.h)
      if x1 <= x0 or y1 <= y0:
        continue
      checked += 1
      rs, re_ = x0 * 3, x1 * 3
      if all(io.row(y)[rs:re_] == idc.row(y)[rs:re_] for y in range(y0, y1)):
        continue
      white = [[], [], []]
      for y in range(y0, y1):
        ro, rd = io.row(y), idc.row(y)
        for o in range(rs, re_, 3):
          if ro[o] >= 250 and ro[o + 1] >= 250 and ro[o + 2] >= 250:
            for c in range(3):
              white[c].append(rd[o + c])
      if white[0]:
        m = [sorted(v)[len(v) // 2] for v in white]
      else:
        m = [255, 255, 255]
      bad = 0
      for y in range(y0, y1):
        ro, rd = io.row(y), idc.row(y)
        for o in range(rs, re_, 3):
          for c in range(3):
            if abs(rd[o + c] - ro[o + c] * m[c] / 255.0) > 48:
              bad += 1
              break
      area = (x1 - x0) * (y1 - y0)
      if bad > max(4, 0.03 * area):
        bad_boxes.append((p, wb[4], bad, area))
  if bad_boxes:
    desc = "; ".join("p%d %r (%d/%d px)" % b for b in bad_boxes[:6])
    raise Fail("%d word box(es) altered by decoration: %s" % (len(bad_boxes),
                                                               desc))
  if checked == 0:
    raise Fail("no text found to check (pdftotext returned no words)")


def need_elems(res):
  need_ok(res)
  if res.kacho_log is None:
    raise Fail("no debug log <jobname>%s written (KACHO_DEBUG=1)" %
               api.DEBUG_LOG_SUFFIX)
  if res.bad_log_lines:
    raise Fail("debug log has %d malformed line(s), e.g. %r" % (
        len(res.bad_log_lines), res.bad_log_lines[0][:120]))
  if not res.elems:
    raise Fail("debug log contains no elem lines")
  return res.elems


def _inter(a, b):
  return (min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1]))


def check_log_text_overlap(res, buffer_bp=0.0, tol=0.5):
  elems = need_elems(res)
  boxes = inline_boxes(res)
  bad = []
  for e in elems:
    if re.search(api.INLINE_KIND, e.kind, re.I):
      if any(b[0] == e.page and bbox_inside(e.bbox, b[2]) for b in boxes):
        continue  # user-placed inline spray inside its logged box
    elif re.search(api.OVERLAP_EXEMPT_KIND, e.kind, re.I):
      continue
    tb = (e.tb[0] - buffer_bp, e.tb[1] - buffer_bp, e.tb[2] + buffer_bp,
          e.tb[3] + buffer_bp)
    dx, dy = _inter(e.bbox, tb)
    if dx > tol and dy > tol:
      bad.append(e)
  if bad:
    raise Fail("%d elem bbox(es) intersect the text block%s: %s" % (
        len(bad), " (+%.1fmm buffer)" % (buffer_bp / MM) if buffer_bp else "",
        "; ".join("p%d %s %s tb=%s" % (e.page, e.kind, _fmt(e.bbox),
                                       _fmt(e.tb)) for e in bad[:5])))


def _fmt(b):
  return "(%s)" % " ".join("%.1f" % v for v in b)


def check_log_edge(res, safe_mm=api.EDGE_SAFE_MM, tol=0.25):
  elems = need_elems(res)
  sizes = page_sizes(res.pdf)
  s = safe_mm * MM - tol
  bad = []
  for e in elems:
    if re.search(api.EDGE_EXEMPT_KIND, e.kind, re.I):
      continue
    if not 1 <= e.page <= len(sizes):
      bad.append((e, "page out of range"))
      continue
    w, h = sizes[e.page - 1]
    x0, y0, x1, y1 = e.bbox
    if x0 < s or y0 < s or x1 > w - s or y1 > h - s:
      bad.append((e, "within %.0fmm of edge (page %.0fx%.0f)" % (safe_mm, w,
                                                                 h)))
  if bad:
    raise Fail("%d elem(s) violate the edge safe zone: %s" % (
        len(bad), "; ".join("p%d %s %s %s" % (e.page, e.kind, _fmt(e.bbox), m)
                            for e, m in bad[:5])))


def check_log_format(res):
  elems = need_elems(res)
  sizes = page_sizes(res.pdf)
  for e in elems:
    vals = e.bbox + e.tb
    if any(math.isnan(v) or math.isinf(v) for v in vals):
      raise Fail("non-finite number in %s" % e)
    if not (e.bbox[0] <= e.bbox[2] and e.bbox[1] <= e.bbox[3]):
      raise Fail("bbox not ordered x0<=x1,y0<=y1: %s" % e)
    if not 1 <= e.page <= len(sizes):
      raise Fail("page %d out of range 1..%d" % (e.page, len(sizes)))
    w, h = sizes[e.page - 1]
    t = e.tb
    if not (0 <= t[0] < t[2] <= w + 0.5 and 0 <= t[1] < t[3] <= h + 0.5):
      raise Fail("textblock %s not inside page %.1fx%.1f" % (_fmt(t), w, h))


def edge_ring_marks(ctx, pdf, ring_mm=2.0, dpi=50, thresh=40):
  """Advisory: per page, count of ring pixels deviating from paper colour."""
  out = {}
  for p, img in enumerate(render(ctx, pdf, dpi), 1):
    mode = mode_color(img)
    r = max(1, int(round(ring_mm / 25.4 * dpi)))
    cnt = tot = 0
    for y in range(img.h):
      row = img.row(y)
      xs = range(img.w) if (y < r or y >= img.h - r) else (
          list(range(r)) + list(range(img.w - r, img.w)))
      for x in xs:
        o = x * img.ch
        tot += 1
        if max(abs(row[o + c] - mode[c]) for c in range(img.ch)) > thresh:
          cnt += 1
    out[p] = (cnt, tot)
  return out


def banding_lines(img, min_run=30):
  """Advisory heuristic: count long straight iso-step lines (digital banding)
  in smooth non-paper regions of a gray raster. Returns count of lines."""
  w, h, d = img.w, img.h, img.data
  mode = mode_color(img)[0]

  def scan(get, n_lines, n_len):
    lines = 0
    prev = {}
    for i in range(n_lines):
      cur = {}
      line = get(i)
      for j in range(1, n_len - 2):
        a, b, c, e = line[j - 1], line[j], line[j + 1], line[j + 2]
        st = c - b
        if 2 <= abs(st) <= 12 and abs(b - a) <= 1 and abs(e - c) <= 1 and (
            abs(b - mode) > 3):
          run_ = max(prev.get(j, 0), prev.get(j - 1, 0), prev.get(j + 1, 0))
          cur[j] = run_ + 1
          if cur[j] == min_run:
            lines += 1
      prev = cur
    return lines

  rows = lambda y: d[y * w:(y + 1) * w]
  cols = lambda x: d[x::w]
  return scan(rows, h, w) + scan(cols, w, h)


# ---------------------------------------------------------------------------
# Feature 32 (user placement) helpers: '#' debug-log lines, geometry, diffs
# ---------------------------------------------------------------------------
def inline_boxes(res):
  """[(page, index, (x0,y0,x1,y1))] from `# page=n inline spray=i box=...`."""
  out = []
  for m in re.finditer(api.LOG_INLINE_RE, res.kacho_log or ""):
    g = m.groups()
    out.append((int(g[0]), int(g[1]), tuple(float(v) for v in g[2:6])))
  return out


@dataclasses.dataclass
class Spawn:
  page: int
  index: int
  at: str
  origin: tuple
  angle: float
  size: float
  status: str


def user_spawns(res):
  """Spawn records from `# page=n user spawn=i at=.. origin=x y ...` lines."""
  out = []
  for m in re.finditer(api.LOG_SPAWN_RE, res.kacho_log or ""):
    g = m.groups()
    out.append(Spawn(int(g[0]), int(g[1]), g[2], (float(g[3]), float(g[4])),
                     float(g[5]), float(g[6]), g[7]))
  return out


def bbox_inside(a, b, tol=0.5):
  return (a[0] >= b[0] - tol and a[1] >= b[1] - tol and a[2] <= b[2] + tol
          and a[3] <= b[3] + tol)


def point_rect_dist(pt, b):
  dx = max(b[0] - pt[0], 0.0, pt[0] - b[2])
  dy = max(b[1] - pt[1], 0.0, pt[1] - b[3])
  return math.hypot(dx, dy)


def center(b):
  return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def union(boxes):
  boxes = list(boxes)
  if not boxes:
    return None
  return (min(b[0] for b in boxes), min(b[1] for b in boxes),
          max(b[2] for b in boxes), max(b[3] for b in boxes))


def anchor_point(at, w, h):
  fx, fy = api.ANCHORS[at]
  return (fx * w, fy * h)


def diff_pixels(ctx, on, off, page, dpi=50, thresh=24):
  """Pixels (x, y; top-left origin) that differ between two renders of a page.

  Returns (pixels, scale px-per-bp, page_h_bp, (w, h) raster size).
  """
  need_ok(on)
  need_ok(off)
  a = render_page(ctx, on.pdf, page, dpi)
  b = render_page(ctx, off.pdf, page, dpi)
  if (a.w, a.h) != (b.w, b.h):
    raise Fail("page %d raster size differs (%dx%d vs %dx%d)" % (
        page, a.w, a.h, b.w, b.h))
  pw, ph = page_sizes(on.pdf)[page - 1]
  px = []
  for y in range(a.h):
    ra, rb = a.row(y), b.row(y)
    if ra == rb:
      continue
    for x in range(a.w):
      o = x * a.ch
      if max(abs(ra[o + c] - rb[o + c]) for c in range(a.ch)) > thresh:
        px.append((x, y))
  return px, a.w / pw, ph, (a.w, a.h)


def bp_to_px(b, scale, page_h, pad=0):
  """bp bbox (bottom-left origin) -> px rect (top-left origin), padded."""
  return (b[0] * scale - pad, (page_h - b[3]) * scale - pad,
          b[2] * scale + pad, (page_h - b[1]) * scale + pad)


def in_px_rect(p, r):
  return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def pdf_all_bytes(pdf):
  """Raw PDF bytes plus every decompressed Flate stream (object streams
  included), for searching structural markers such as /JavaScript."""
  data = open(pdf, "rb").read()
  parts = [data]
  for m in re.finditer(rb"stream\r?\n", data):
    start = m.end()
    end = data.find(b"endstream", start)
    if end < 0:
      continue
    try:
      parts.append(zlib.decompressobj().decompress(data[start:end]))
    except zlib.error:
      pass
  return b"\n".join(parts)


def kacho_diagnostic(log_text):
  """True if the LaTeX log carries a clean kacho package diagnostic."""
  return bool(re.search(r"Package kacho (Error|Warning)", log_text or ""))


def raw_lua_traceback(log_text):
  return bool(re.search(r"stack traceback:", log_text or ""))
