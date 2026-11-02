#!/usr/bin/env python3
"""kacho E2E test runner. Usage: tests/e2e/run.sh [options]

  --quick            run the quick subset (smoke coverage of every group)
  --tier T[,T]       only tiers (1,2,3,4,adv)
  --group G[,G]      only groups (build,view,noimg,overlap,edge,det,palette,
                     theme,layout,control,title,motif,docs,place,license,
                     animated)
  -k REGEX           only tests whose name matches REGEX (repeatable, OR)
  --jobs N           parallel workers (default: nproc)
  --list             list selected tests and exit
  --repo PATH        repository root (default: two levels above this file)
  --out DIR          scratch dir (default: /tmp/kacho_e2e/run-<timestamp>)
  --no-advisory      skip advisory tests
  --verbose          print info for passing tests

Exit status: 0 iff every selected blocking test passed (advisory failures
are reported as WARN and never affect the exit status).
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness as H  # pylint: disable=g-import-not-at-top
import suite  # pylint: disable=g-import-not-at-top


def parse_args(argv):
  ap = argparse.ArgumentParser(add_help=True, usage=__doc__)
  ap.add_argument("--quick", action="store_true")
  ap.add_argument("--tier", default="")
  ap.add_argument("--group", default="")
  ap.add_argument("-k", action="append", default=[])
  ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
  ap.add_argument("--list", action="store_true")
  ap.add_argument("--repo", default=os.path.abspath(
      os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
  ap.add_argument("--out", default="")
  ap.add_argument("--no-advisory", action="store_true")
  ap.add_argument("--verbose", action="store_true")
  return ap.parse_args(argv)


def select(tests, a):
  tiers = set(filter(None, a.tier.split(",")))
  groups = {"animated" if g == "anim" else g
            for g in filter(None, a.group.split(","))}
  out = []
  for t in tests:
    if tiers and t.tier not in tiers:
      continue
    if groups and t.group not in groups:
      continue
    if a.k and not any(re.search(k, t.name) for k in a.k):
      continue
    if a.quick and not t.quick:
      continue
    if a.no_advisory and t.advisory:
      continue
    out.append(t)
  return out


def warmup(ctx):
  """Build luaotfload's font cache once, serially, before parallel runs."""
  d = os.path.join(ctx.run_dir, "warmup")
  os.makedirs(d, exist_ok=True)
  with open(os.path.join(d, "w.tex"), "w") as f:
    f.write("\\documentclass{article}\\begin{document}warm\\end{document}\n")
  H.run(["lualatex", "-interaction=nonstopmode", "w.tex"], cwd=d,
        env=ctx.tex_env(debug=False), timeout=600)


def main(argv):
  a = parse_args(argv)
  tests = suite.build_registry(a.repo)
  sel = select(tests, a)
  if a.list:
    for t in sel:
      print("%-55s tier=%-3s group=%-8s %s%s" % (
          t.name, t.tier, t.group, "[quick] " if t.quick else "", t.doc))
    print("%d test(s)" % len(sel))
    return 0
  out = a.out or "/tmp/kacho_e2e/run-%s" % time.strftime("%Y%m%d-%H%M%S")
  ctx = H.Ctx(a.repo, out, verbose=a.verbose)
  print("kacho E2E: %d test(s), repo=%s, scratch=%s, jobs=%d" % (
      len(sel), a.repo, out, a.jobs))
  sys.stdout.flush()
  warmup(ctx)
  results = []
  lock = threading.Lock()
  t_start = time.time()

  def run_one(t):
    t0 = time.time()
    try:
      info = t.fn(ctx)
      st, msg = "PASS", info or ""
    except H.Fail as e:
      st, msg = ("WARN" if t.advisory else "FAIL"), str(e)
    except Exception as e:  # pylint: disable=broad-except
      st = "WARN" if t.advisory else "FAIL"
      msg = "harness exception %s: %s | %s" % (
          type(e).__name__, e, traceback.format_exc().strip().splitlines()[-2]
          .strip())
    dt = time.time() - t0
    with lock:
      results.append((t, st, msg, dt))
      line = "%-4s %-55s %6.1fs" % (st, t.name, dt)
      if st != "PASS" or a.verbose:
        if msg:
          line += "  " + msg.replace("\n", " ")[:400]
      print(line)
      sys.stdout.flush()

  # Long-running tests first improves wall time.
  order = sorted(sel, key=lambda t: (0 if (t.group in ("build", "view") or
                                           "long" in t.name) else 1))
  with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
    list(ex.map(run_one, order))

  # Summary
  by_tier = {}
  for t, st, _, _ in results:
    d = by_tier.setdefault(t.tier, {"PASS": 0, "FAIL": 0, "WARN": 0})
    d[st] += 1
  print("\n=== Summary (%.0fs) ===" % (time.time() - t_start))
  for tier in sorted(by_tier):
    d = by_tier[tier]
    print("tier %-3s  pass %3d  fail %3d  warn %3d" % (tier, d["PASS"],
                                                       d["FAIL"], d["WARN"]))
  fails = [r for r in results if r[1] == "FAIL"]
  warns = [r for r in results if r[1] == "WARN"]
  npass = sum(1 for r in results if r[1] == "PASS")
  print("TOTAL: %d passed, %d failed, %d advisory warnings" % (
      npass, len(fails), len(warns)))
  rep = os.path.join(out, "report.json")
  with open(rep, "w") as f:
    json.dump([{"name": t.name, "tier": t.tier, "group": t.group,
                "status": st, "message": m, "seconds": round(dt, 2)}
               for t, st, m, dt in sorted(results, key=lambda r: r[0].name)],
              f, indent=1)
  print("report: %s" % rep)
  return 0 if not fails else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
