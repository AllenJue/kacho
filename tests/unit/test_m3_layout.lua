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
-- Unit tests for tex/kacho-layout.lua (M3): variety deck, zones, Plan
-- transactions, all 10 layouts, all 5 seasonal themes, regions=, motif=,
-- and user-controlled placement (\kachoSpawn and \kachospray).

return function(T)
  local K   = require("kacho")
  local G   = require("kacho-geom")
  local L   = require("kacho-layout")
  local pdf = require("kacho-pdf")
  local H   = require("helpers")

  local function sp_mm(x) return x * 72 / 25.4 * G.SP_PER_BP end
  local INCH = sp_mm(25.4)

  local function make_page(folio, index, custom_opts)
    local d = {
      paperwidth = sp_mm(210), paperheight = sp_mm(297), hoffset = 0, voffset = 0,
      oddsidemargin = sp_mm(22) - INCH, evensidemargin = sp_mm(38) - INCH,
      topmargin = sp_mm(18) - INCH, headheight = 12 * 65536, headsep = 18 * 65536,
      textheight = sp_mm(220), textwidth = sp_mm(150), footskip = 26 * 65536,
      baselineskip = 13.6 * 65536,
    }
    local opts = {}
    for k, v in pairs(K.defaults) do opts[k] = v end
    for k, v in pairs(custom_opts or {}) do opts[k] = v end
    local page = G.page(d, { folio = folio or 1, index = index or 1, twoside = true,
                             safe_mm = opts.safe, buffer_mm = opts.buffer })
    page.ink = { { x0 = page.text.x0 + 10, y0 = page.text.y1 - 40, x1 = page.text.x1 - 10, y1 = page.text.y1 - 10 } }
    local block = page.typearea
    if opts.layout == "shikishi" then block = page.ink[1] end
    G.regions(page, block, page.ink)
    page.opts = opts
    local lines = {}
    local W = pdf.new(pdf.registry(H.backend()))
    local ctx = K.make_context(page, opts, W, function(l) lines[#lines + 1] = l end)
    ctx.log = function(l) lines[#lines + 1] = l end
    return ctx, page, lines, W
  end

  -- 1. Variety deck: deterministic and no consecutive repeats
  local list = { "overhang", "corner-spray", "rising", "margin-column", "header-garland", "footer-ground" }
  local prev = nil
  local repeat_found = false
  for i = 1, 24 do
    local p1 = L.deck_pick(42, i, list)
    local p2 = L.deck_pick(42, i, list)
    if p1 ~= p2 then repeat_found = true end
    if p1 == prev then repeat_found = true end
    prev = p1
  end
  T.ok(not repeat_found, "L.deck_pick is deterministic and avoids consecutive repeats across deck epochs")

  -- 2. Dimension & spawn shorthand parsing
  T.near(L.dim("10mm", 0), 10 * 72 / 25.4, 1e-4, "L.dim converts mm to bp")
  T.near(L.dim("72bp", 0), 72, 1e-4, "L.dim converts bp")
  local sp1 = L.parse_spawn("br+10mm-5mm@125")
  T.ok(sp1 and sp1.at == "br" and sp1.dx == "+10mm" and sp1.dy == "-5mm" and tonumber(sp1.angle) == 125,
    "L.parse_spawn parses shorthand anchor+dx+dy@angle")
  local sp2 = L.parse_spawn("at=tl, size=55mm, seed=3")
  T.ok(sp2 and sp2.at == "tl" and sp2.size == "55mm" and sp2.seed == "3",
    "L.parse_spawn parses key=value syntax")

  -- 3. Anchors & regions parsing
  local ctx0, page0 = make_page(1, 1)
  local ax, ay, af = L.anchor(page0, "tl", "page")
  T.ok(af and math.abs(ax - 0) < 1e-3 and math.abs(ay - page0.paper.h) < 1e-3, "L.anchor resolves tl on page")
  local bx, by, bf = L.anchor(page0, "nowhere", "page")
  T.ok(bx == nil and by == nil and bf == nil, "L.anchor returns nil for unknown anchor")

  local r_none = L.parse_regions_opt("none", page0)
  local r_frame = L.parse_regions_opt("frame", page0)
  local r_corners = L.parse_regions_opt("corners", page0)
  local r_sides = L.parse_regions_opt("{left,top}", page0)
  T.ok(r_none.mode == "none" and r_frame.mode == "frame" and r_corners.mode == "corners", "L.parse_regions_opt modes")
  T.ok(r_sides.mode == "sides" and r_sides.sides.left and r_sides.sides.top, "L.parse_regions_opt side set")

  -- 4. L.auto dispatches regions and forced motifs
  local _, p_none = make_page(1, 1, { regions = "none" })
  T.ok(L.auto(p_none, ctx0) == "none", "L.auto returns none for regions=none")
  local _, p_frame = make_page(1, 1, { regions = "frame" })
  T.ok(L.auto(p_frame, ctx0) == "border-frame", "L.auto returns border-frame for regions=frame")
  local _, p_corners = make_page(1, 1, { regions = "corners" })
  T.ok(L.auto(p_corners, ctx0) == "corners", "L.auto returns corners for regions=corners")

  -- 5. All 10 layouts execute cleanly with 0 WARN lines and valid containment
  local layout_names = {
    "overhang", "rising", "corner-spray", "margin-column",
    "header-garland", "footer-ground", "scattered-petals",
    "border-frame", "kakejiku", "shikishi",
  }
  for _, lname in ipairs(layout_names) do
    local ctx, page, lines, W = make_page(1, 1, { layout = lname, seed = 17 })
    local fn = L.layouts[lname]
    T.ok(type(fn) == "function", "layout registered: " .. lname)
    fn(ctx, page)
    local warns = 0
    for _, l in ipairs(lines) do
      if l:find("^# WARN") then warns = warns + 1 end
    end
    T.ok(#ctx.records > 0, "layout draws elements: " .. lname .. " (" .. #ctx.records .. ")")
    T.ok(warns == 0, "layout has zero safety/overlap warnings: " .. lname)
    local ok_p = pcall(W.pieces, W)
    T.ok(ok_p, "layout PDF stream is balanced: " .. lname)
  end

  -- 6. All 5 seasonal themes execute cleanly
  for _, th in ipairs({ "haru", "natsu", "aki", "fuyu", "shochikubai" }) do
    local ctx, page, lines = make_page(1, 1, { theme = th, seed = 21 })
    L.layouts.overhang(ctx, page)
    local warns = 0
    for _, l in ipairs(lines) do if l:find("^# WARN") then warns = warns + 1 end end
    T.ok(#ctx.records > 0 and warns == 0, "theme=" .. th .. " draws without warnings")
  end

  -- 7. User placement: \kachoSpawn and \kachospray
  local ctx_u, page_u, lines_u = make_page(1, 1, { regions = "none", seed = 9 })
  local ibox = { x0 = page_u.text.x0 + 20, y0 = page_u.text.y0 + 60, x1 = page_u.text.x0 + 180, y1 = page_u.text.y0 + 140 }
  L.user(ctx_u, page_u, {
    spawns = { "at=br, size=55mm, angle=135, motif=ume, seed=4", "tl@-45" },
    sprays = {
      { keys = "motif=bamboo,seed=5,from=left", rect = ibox },
      { keys = "seed=1", rect = { x0 = 100, y0 = 100, x1 = 100, y1 = 100 } }, -- zero-size box safety
    },
  })
  local has_inline, has_spawn, warns_u = false, false, 0
  for _, r in ipairs(ctx_u.records) do
    if r.kind:find("^inline%-") then
      has_inline = true
      T.ok(G.contains(ibox, r.bbox, 0.5), "inline element stays inside spray box")
    else
      has_spawn = true
    end
  end
  for _, l in ipairs(lines_u) do if l:find("^# WARN") then warns_u = warns_u + 1 end end
  T.ok(has_spawn, "L.user draws spawn elements")
  T.ok(has_inline, "L.user draws inline spray elements")
  T.ok(warns_u == 0, "L.user emits zero safety warnings")
end
