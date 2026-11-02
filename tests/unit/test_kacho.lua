-- Copyright 2026 Allen Jue
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--
-- Tests for the pure parts of kacho.lua: option validation, key parsing,
-- env overrides, context rules and the demo layout's containment.
return function(T)
  local K = require("kacho")
  local G = require("kacho-geom")
  local pdf = require("kacho-pdf")
  local H = require("helpers")

  local kv = K.parse_keyvals("layout=corner-spray, seed = 11, title={A, B}, off")
  T.ok(#kv == 4 and kv[1][1] == "layout" and kv[1][2] == "corner-spray", "parse k=v")
  T.ok(kv[2][2] == "11" and kv[3][2] == "A, B" and kv[4][1] == "off" and kv[4][2] == "", "parse spaces, braces, flags")

  T.ok(K.check("palette", "hanga") == "hanga", "palette hanga accepted")
  T.raises(function() K.check("palette", "delft") end, "bad palette rejected")
  T.raises(function() K.check("theme", "winter") end, "bad theme rejected")
  T.ok(K.check("density", "7") == 1 and K.check("density", "-1") == 0, "density clamped to 0..1")
  T.ok(K.check("off", "") == true and K.check("debug", "false") == false, "boolean flags")
  T.ok(K.check("buffer", 1, nil) == 4, "buffer cannot go below 4mm")
  T.near(K.check("safe", 8 * 72 / 25.4 * G.SP_PER_BP, "sp"), 8, 1e-9, "safe given in sp converts to mm")
  T.raises(function() K.check("colour", "x") end, "unknown option rejected")
  T.ok(K.check("layout", "shikishi") == "shikishi", "any layout name accepted (resolved at shipout)")
  T.ok(K.check("motif", "ume+uguisu") == "ume+uguisu" and K.check("regions", "outer,top") == "outer,top",
    "motif and regions options accepted")
  T.ok(K.PAGE_KEYS.motif and K.PAGE_KEYS.regions and K.PAGE_KEYS.spawn, "motif/regions/spawn are PAGE_KEYS")

  -- env overrides beat document options
  local saved = {}
  for k, v in pairs(K.opts) do saved[k] = v end
  K.apply_env(function(n) return ({ KACHO_SEED = "99", KACHO_DEBUG = "1", KACHO_OFF = "1" })[n] end)
  T.ok(K.opts.seed == 99 and K.opts.debug and K.opts.off, "KACHO_SEED/DEBUG/OFF applied")
  K.set("seed", "5")
  T.ok(K.opts.seed == 99, "document seed cannot override KACHO_SEED")
  K.env_lock = {}
  for k, v in pairs(saved) do K.opts[k] = v end

  -- layout resolution: unknown names fall back to the demo layout; regions=none -> none
  local name, fn = K.resolve_layout("header-garland", {}, {})
  T.ok(K.layouts["header-garland"] ~= nil or (name == "demo" and fn == K.demo_layout), "missing layout falls back to demo")
  local n2, f2 = K.resolve_layout("none", {}, {})
  T.ok(n2 == "none" and f2 == nil, "layout none draws nothing")
  local n3, f3 = K.resolve_layout("auto", { opts = { regions = "none" } }, {})
  T.ok(n3 == "none" and f3 == nil, "regions=none resolves to layout none")

  -- demo layout on synthetic pages: every recorded element obeys the rules.
  -- These test the built-in tree, independent of whether kacho-flora exists.
  K._set_flora(false)
  local function sp_mm(x) return x * 72 / 25.4 * G.SP_PER_BP end
  local INCH = sp_mm(25.4)
  local papers = { { 148, 210, 16, 34 }, { 210, 297, 25, 25 }, { 297, 210, 20, 42 }, { 210, 297, 10, 10 } }
  for pi_, pp in ipairs(papers) do
    for folio = 1, 2 do
      local d = {
        paperwidth = sp_mm(pp[1]), paperheight = sp_mm(pp[2]), hoffset = 0, voffset = 0,
        oddsidemargin = sp_mm(pp[3]) - INCH, evensidemargin = sp_mm(pp[4]) - INCH,
        topmargin = sp_mm(15) - INCH, headheight = 12 * 65536, headsep = 25 * 65536,
        textheight = sp_mm(pp[2] - 50), textwidth = sp_mm(pp[1] - pp[3] - pp[4]), footskip = 30 * 65536,
        baselineskip = 13.6 * 65536,
      }
      local page = G.page(d, { folio = folio, index = folio, twoside = true })
      G.regions(page, page.typearea, {})
      local lines = {}
      local W = pdf.new(pdf.registry(H.backend()))
      local opts = {}
      for k, v in pairs(K.defaults) do opts[k] = v end
      local ctx = K.make_context(page, opts, W, function(l) lines[#lines + 1] = l end)
      K.demo_layout(ctx, page)
      local warn, nrec = 0, 0
      for _, l in ipairs(lines) do
        if l:find("^# WARN") then warn = warn + 1 end
        if l:find("^page=") then nrec = nrec + 1 end
      end
      local tag = string.format("paper %d page %d", pi_, folio)
      T.ok(warn == 0, "demo layout: no rule violations (" .. tag .. ")")
      if pi_ < 4 then T.ok(nrec >= 3, "demo layout draws trunk, twigs/blossoms, wash (" .. tag .. ", " .. nrec .. " elems)") end
      local fmt_ok = true
      for _, l in ipairs(lines) do
        if l:find("^page=") and not l:match("^page=%d+ elem=%S+ bbox=%S+ %S+ %S+ %S+ textblock=%S+ %S+ %S+ %S+$") then fmt_ok = false end
        if l:find("^page=") and not l:find("elem=demo%-") then fmt_ok = false end
      end
      T.ok(fmt_ok, "debug-log element lines match the agreed format and carry the motif name (" .. tag .. ")")
      local ok_bal, pieces = pcall(W.pieces, W)
      T.ok(ok_bal, "demo output balanced (" .. tag .. ")")
      -- painted geometry stays out of the text exclusion (ignoring the bleed trunk base)
      local clear = true
      for _, rec in ipairs(ctx.records) do
        if not G.clear_of(rec.bbox, page.exclude) then clear = false end
      end
      T.ok(clear, "no recorded element touches the type-area exclusion (" .. tag .. ")")
    end
  end
  -- mirroring: odd page draws on the right, even on the left
  local d = {
    paperwidth = sp_mm(148), paperheight = sp_mm(210), hoffset = 0, voffset = 0,
    oddsidemargin = sp_mm(16) - INCH, evensidemargin = sp_mm(34) - INCH,
    topmargin = sp_mm(15) - INCH, headheight = 12 * 65536, headsep = 25 * 65536,
    textheight = sp_mm(160), textwidth = sp_mm(98), footskip = 30 * 65536, baselineskip = 13.6 * 65536,
  }
  local cx = {}
  for folio = 1, 2 do
    local page = G.page(d, { folio = folio, index = folio, twoside = true })
    G.regions(page, page.typearea, {})
    local W = pdf.new(pdf.registry(nil))
    local opts = {}
    for k, v in pairs(K.defaults) do opts[k] = v end
    local ctx = K.make_context(page, opts, W, nil)
    K.demo_layout(ctx, page)
    cx[folio] = (W.bbox.x0 + W.bbox.x1) / 2
  end
  T.ok(cx[1] > 148 * 72 / 25.4 / 2 and cx[2] < 148 * 72 / 25.4 / 2, "two-sided mirroring: odd right, even left")

  -- bleed contract enforcement, per-part ctx:try, and M3 context classifiers
  do
    local page = G.page(d, { folio = 1, index = 1, twoside = true })
    G.regions(page, page.text, {})
    local W = pdf.new(pdf.registry(H.backend()))
    local opts = {}
    for k, v in pairs(K.defaults) do opts[k] = v end
    local lines = {}
    local ctx = K.make_context(page, opts, W, function(l) lines[#lines + 1] = l end)
    T.ok(ctx.under ~= nil and ctx.is_ground("kakejiku-ground") and ctx.is_inline("inline-spray"),
      "ctx.under, ctx.is_ground, and ctx.is_inline present")
    local sub_none = ctx:sub({ region = page.regions.outer, bleed = {}, tag = "b0" })
    local sub_right = ctx:sub({ region = page.regions.outer, bleed = { right = true }, tag = "b1" })
    local top_bleed = { x0 = sub_none.region.x0 + 2, y0 = page.safe.y1 - 4, x1 = sub_none.region.x1 - 2, y1 = page.paper.h + 15 }
    local right_bleed = { x0 = sub_none.region.x0 + 2, y0 = sub_none.region.y0 + 10, x1 = page.paper.w + 10, y1 = sub_none.region.y0 + 30 }
    local across = { x0 = -20, y0 = 10, x1 = page.paper.w + 20, y1 = 20 }
    T.ok(not sub_none.fits(top_bleed, "ume-trunk"), "bleed={} rejects trunk crossing top edge")
    T.ok(not sub_right.fits(top_bleed, "ume-trunk"), "bleed={right=true} rejects trunk crossing top edge")
    T.ok(sub_right.fits(right_bleed, "ume-trunk"), "bleed={right=true} allows trunk crossing right edge")
    T.ok(not ctx.fits(across, "bamboo-culm"), "bleed rejects culm spanning across opposite edges")
    sub_none.record("ume-trunk", top_bleed)
    local bwarn = 0
    for _, l in ipairs(lines) do if l:find("^# WARN.*outside safe zone") then bwarn = bwarn + 1 end end
    T.ok(bwarn == 1, "sub.record logs # WARN when bleed kind crosses unlisted edge")

    -- per-part ctx:try: L-shaped multi-part trial whose union straddles the text block corner
    local arm_bot = { x0 = page.exclude[1].x1 - 30, y0 = page.regions.bottom.y0 + 2, x1 = page.regions.outer.x1 - 2, y1 = page.regions.bottom.y1 - 2 }
    local arm_side = { x0 = page.regions.outer.x0 + 2, y0 = page.regions.bottom.y0 + 2, x1 = page.regions.outer.x1 - 2, y1 = page.exclude[1].y0 + 30 }
    local l_bb = ctx:try("ume-branch", function(tc)
      tc.pdf:fill(tc.pdf:rect(arm_bot), { 0, 0, 0 }, 1)
      tc.record("ume-branch", arm_bot)
      tc.pdf:fill(tc.pdf:rect(arm_side), { 0, 0, 0 }, 1)
      tc.record("ume-branch", arm_side)
      return G.union(arm_bot, arm_side)
    end)
    T.ok(l_bb ~= nil and not ctx.fits(l_bb, "ume-branch"),
      "per-part ctx:try accepts L-shaped spray whose individual parts fit even when union straddles corner")
  end

  -- run the demo on the A5 page `d` with a seed; returns info, ctx, log lines, page
  local function run_demo(seed, folio)
    local page = G.page(d, { folio = folio, index = folio, twoside = true })
    G.regions(page, page.typearea, {})
    local W = pdf.new(pdf.registry(H.backend()))
    local opts = {}
    for k, v in pairs(K.defaults) do opts[k] = v end
    opts.seed = seed
    local lines = {}
    local ctx = K.make_context(page, opts, W, function(l) lines[#lines + 1] = l end)
    ctx.log = function(l) lines[#lines + 1] = l end      -- as M.shipout does in debug mode
    local info = K.demo_layout(ctx, page)
    return info, ctx, lines, page, W
  end
  local function kinds(ctx)
    local t = {}
    for _, r in ipairs(ctx.records) do t[r.kind] = (t[r.kind] or 0) + 1 end
    return t
  end

  -- built-in tree: ground wash centred under the trunk base, no stray mist band,
  -- blossoms attached to twig nodes in clusters
  local centred, rooted, nomist, attached, clustered, enough = true, true, true, true, true, true
  for seed = 1, 10 do
    for folio = 1, 2 do
      local info, ctx = run_demo(seed, folio)
      local g, bx, by = info.ground, info.base[1], info.base[2]
      if not g then centred = false
      else
        local gcx = (g.x0 + g.x1) / 2
        if math.abs(gcx - bx) > 0.08 * (g.x1 - g.x0) or by < g.y0 or by > g.y1 then centred = false end
      end
      local trunk
      for _, r in ipairs(ctx.records) do if r.kind == "demo-trunk" then trunk = r.bbox end end
      if not trunk or bx < trunk.x0 or bx > trunk.x1 or trunk.y0 > by then rooted = false end
      local k = kinds(ctx)
      if k["demo-mist"] then nomist = false end
      local limbs = {}
      for _, r in ipairs(ctx.records) do
        if r.kind == "demo-branch" or r.kind == "demo-twig" then limbs[#limbs + 1] = r.bbox end
      end
      local per_node = {}
      for _, b in ipairs(info.blossoms) do
        local dx, dy = b.x - b.node[1], b.y - b.node[2]
        if math.sqrt(dx * dx + dy * dy) > 1.4 * b.r then attached = false end
        local on_limb = false
        for _, l in ipairs(limbs) do
          if b.node[1] >= l.x0 - 0.5 and b.node[1] <= l.x1 + 0.5 and b.node[2] >= l.y0 - 0.5 and b.node[2] <= l.y1 + 0.5 then on_limb = true end
        end
        if not on_limb then attached = false end
        local key = string.format("%.2f,%.2f", b.node[1], b.node[2])
        per_node[key] = (per_node[key] or 0) + 1
      end
      local maxc = 0
      for _, v in pairs(per_node) do maxc = math.max(maxc, v) end
      if maxc < 2 then clustered = false end
      if #info.blossoms < 8 then enough = false end
    end
  end
  T.ok(centred, "demo: ground wash is centred under the trunk base (10 seeds x 2 sides)")
  T.ok(rooted, "demo: trunk foot sits at the wash centre")
  T.ok(nomist, "demo: no stray mist band crossing the trunk")
  T.ok(attached, "demo: every blossom/bud sits within 1.4 r of a node on a drawn twig")
  T.ok(clustered, "demo: blossoms form clusters (>= 2 flowers at some node)")
  T.ok(enough, "demo: at least 8 flowers on an A5 margin")

  -- spray depth: far (light, behind) and near limbs both exist and overlap
  -- each other on most pages; far limbs use a lighter ink than near limbs
  local layered = 0
  for seed = 1, 10 do
    local info = run_demo(seed, 1)
    local far, near = {}, {}
    for _, l in ipairs(info.limbs) do
      if l.far then far[#far + 1] = l.bbox elseif l.kind == "demo-branch" then near[#near + 1] = l.bbox end
    end
    local cross = false
    for _, f in ipairs(far) do for _, nb in ipairs(near) do if G.intersection(f, nb) then cross = true end end end
    if #far > 0 and #near > 0 and cross then layered = layered + 1 end
  end
  T.ok(layered >= 8, "demo: far and near limbs overlap (depth) on >= 8 of 10 seeds (" .. layered .. ")")

  -- delegation to kacho-flora.ume when present
  local calls = {}
  K._set_flora({ ume = function(c, spec)
    calls[#calls + 1] = spec
    local r = { x0 = spec.x - 4, y0 = spec.y, x1 = spec.x + 4, y1 = spec.y + 60 }
    c.pdf:fill(c.pdf:rect(r.x0, r.y0, r.x1, r.y1), { 0.2, 0.2, 0.2 }, 0.5)
    c.record("ume-trunk", r)
    return r
  end })
  local info, ctx = run_demo(3, 1)
  local k = kinds(ctx)
  T.ok(#calls == 1 and info.delegated, "demo delegates the tree to kacho-flora.ume when available")
  T.ok(calls[1] and calls[1].x == info.base[1] and calls[1].y == info.base[2] and calls[1].angle == math.pi / 2,
    "flora.ume receives the trunk base at the ground-wash centre")
  T.ok(k["ume-trunk"] == 1 and k["demo-earth"] and not k["demo-trunk"] and not k["demo-blossom"],
    "delegated page: motif records + demo ground wash, no built-in tree")
  -- a failing motif falls back to the built-in tree and is logged
  K._set_flora({ ume = function() error("boom") end })
  local info2, ctx2, lines2 = run_demo(3, 1)
  local logged = false
  for _, l in ipairs(lines2) do if l:find("kacho%-flora%.ume failed: .*boom") then logged = true end end
  T.ok(not info2.delegated and kinds(ctx2)["demo-trunk"] == 1 and logged, "failing flora.ume falls back to the built-in tree")
  -- a motif that draws nothing falls back too
  K._set_flora({ ume = function() return nil end })
  local info3, ctx3 = run_demo(3, 1)
  T.ok(not info3.delegated and kinds(ctx3)["demo-trunk"] == 1, "flora.ume returning nil falls back to the built-in tree")
  -- a motif whose art hits the text is discarded with its records (growth limiting)
  K._set_flora({ ume = function(c, spec)
    local r = { x0 = c.page.text.x0 + 5, y0 = spec.y, x1 = c.page.text.x0 + 20, y1 = spec.y + 20 }
    c.pdf:fill(c.pdf:rect(r.x0, r.y0, r.x1, r.y1), { 0, 0, 0 }, 1)
    c.record("ume-blossom", r)
    return r
  end })
  local info4, ctx4 = run_demo(3, 1)
  T.ok(not info4.delegated and not kinds(ctx4)["ume-blossom"] and kinds(ctx4)["demo-trunk"] == 1,
    "flora art overlapping the text is discarded and its records dropped")
  -- a motif whose sub-part crosses the paper edge is rejected and falls back to built-in tree
  K._set_flora({ ume = function(c, spec)
    local tr = { x0 = spec.x - 3, y0 = spec.y, x1 = spec.x + 3, y1 = spec.y + 40 }
    local bl = { x0 = c.page.safe.x1 - 2, y0 = spec.y + 30, x1 = c.page.paper.w + 10, y1 = spec.y + 45 }
    c.pdf:fill(c.pdf:rect(tr), { 0, 0, 0 }, 1)
    c.record("ume-trunk", tr)
    c.pdf:fill(c.pdf:rect(bl), { 1, 0, 0 }, 1)
    c.record("ume-blossom", bl)
    return tr
  end })
  local info5, ctx5 = run_demo(3, 1)
  T.ok(not info5.delegated and not kinds(ctx5)["ume-blossom"] and kinds(ctx5)["demo-trunk"] == 1,
    "flora art with off-page blossom record is rejected and falls back to built-in tree")
  K._set_flora(nil)
end
