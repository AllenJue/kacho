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
-- Tests for kacho-geom: rect ops, page geometry, mirroring, regions.
return function(T)
  local G = require("kacho-geom")
  local function sp_mm(x) return x * 72 / 25.4 * G.SP_PER_BP end
  local function sp_pt(x) return x * 65536 end
  local INCH = sp_mm(25.4)

  -- page: 170x240 mm, twoside, inner 18mm, outer 45mm, top of head 20mm, text 170mm high
  local d = {
    paperwidth = sp_mm(170), paperheight = sp_mm(240), hoffset = 0, voffset = 0,
    oddsidemargin = sp_mm(18) - INCH, evensidemargin = sp_mm(45) - INCH,
    topmargin = sp_mm(20) - INCH, headheight = sp_pt(12), headsep = sp_pt(25),
    textheight = sp_mm(170), textwidth = sp_mm(107), footskip = sp_pt(30), baselineskip = sp_pt(13.6),
  }
  local odd = G.page(d, { folio = 1, index = 1, twoside = true })
  local even = G.page(d, { folio = 2, index = 2, twoside = true })
  T.near(odd.text.x0, G.mm(18), 0.02, "odd page text x0 = inner margin")
  T.near(even.text.x0, G.mm(45), 0.02, "even page text x0 = outer margin (mirrored)")
  T.near(odd.text.x1 - odd.text.x0, G.mm(107), 0.02, "text width")
  local headtop = G.mm(240) - G.mm(20)
  T.near(odd.head.y1, headtop, 0.02, "head top")
  T.near(odd.text.y1, headtop - 37 * 72 / 72.27, 0.02, "text top = head top - headheight - headsep")
  T.near(odd.text.y1 - odd.text.y0, G.mm(170), 0.02, "text height")
  T.ok(odd.outer == "right" and even.outer == "left", "outer side alternates in twoside")
  local one = G.page(d, { folio = 2, index = 2, twoside = false })
  T.ok(one.text.x0 == odd.text.x0 and one.outer == "right", "oneside: odd margins on every page, outer = wider side")
  T.ok(G.contains(odd.typearea, odd.text) and G.contains(odd.typearea, odd.head) and G.contains(odd.typearea, odd.foot),
    "type area contains body, head and foot")
  T.near(odd.safe.x0, G.mm(5), 1e-9, "safe zone 5mm")

  -- rect ops
  local a, b = G.rect(0, 0, 10, 10), G.rect(10, 0, 20, 10)
  T.ok(not G.intersects(a, b), "touching rects do not intersect")
  T.ok(G.intersects(a, G.rect(5, 5, 15, 15)), "overlapping rects intersect")
  T.ok(G.intersection(a, b) == nil, "intersection of touching rects is nil")
  local u = G.union(a, nil, b)
  T.ok(u.x0 == 0 and u.x1 == 20, "union skips nil")
  local pieces = G.subtract(G.rect(0, 0, 10, 10), G.rect(3, 3, 6, 6))
  local area = 0
  for _, p in ipairs(pieces) do area = area + G.area(p) end
  T.near(area, 100 - 9, 1e-9, "subtract keeps the exact remaining area")
  local overlap = false
  for i = 1, #pieces do for j = i + 1, #pieces do if G.intersects(pieces[i], pieces[j]) then overlap = true end end end
  T.ok(not overlap, "subtract pieces do not overlap")
  T.near(G.mm(25.4), 72, 1e-9, "mm -> bp")

  -- regions: never intersect exclusions, always inside safe, for several papers
  local papers = {
    { "a4", 210, 297, 30, 30 }, { "a5", 148, 210, 16, 34 }, { "letter", 215.9, 279.4, 25.4, 25.4 },
    { "narrow", 210, 297, 10, 10 },
  }
  for _, pp in ipairs(papers) do
    for _, twoside in ipairs({ true, false }) do
      local dd = {}
      for k, v in pairs(d) do dd[k] = v end
      dd.paperwidth, dd.paperheight = sp_mm(pp[2]), sp_mm(pp[3])
      dd.oddsidemargin, dd.evensidemargin = sp_mm(pp[4]) - INCH, sp_mm(pp[5]) - INCH
      dd.textwidth = sp_mm(pp[2] - pp[4] - pp[5])
      dd.textheight = sp_mm(pp[3] - 60)
      for folio = 1, 2 do
        local pg = G.page(dd, { folio = folio, index = folio, twoside = twoside })
        local ink = { G.rect(pg.text.x1 + 4, pg.text.y0 + 50, pg.text.x1 + 40, pg.text.y0 + 80) } -- a marginpar
        G.regions(pg, pg.typearea, ink)
        local okx, oks = true, true
        for _, r in ipairs(pg.region_list) do
          if not G.clear_of(r, pg.exclude) then okx = false end
          if not G.contains(pg.safe, r, 1e-9) then oks = false end
        end
        local tag = string.format("%s %s p%d", pp[1], twoside and "twoside" or "oneside", folio)
        T.ok(okx, "regions clear of exclusions (" .. tag .. ")")
        T.ok(oks, "regions inside safe zone (" .. tag .. ")")
      end
    end
  end
  -- marginpar becomes an extra exclusion and splits the outer column
  local pg = G.page(d, { folio = 1, index = 1, twoside = true })
  local mp = G.rect(pg.text.x1 + 10, 300, pg.text.x1 + 60, 340)
  G.regions(pg, pg.typearea, { mp })
  T.ok(#pg.exclude == 2, "measured ink outside the type area becomes an extra exclusion")
  T.ok(G.clear_of(pg.regions.outer, { G.inflate(mp, pg.buffer) }), "outer region avoids the marginpar")
  -- ink inside the type area (within tolerance) adds nothing
  local pg2 = G.page(d, { folio = 1, index = 1, twoside = true })
  G.regions(pg2, pg2.typearea, { G.rect(pg2.text.x0, pg2.text.y1 - 10, pg2.text.x1 + 0.5, pg2.text.y1) })
  T.ok(#pg2.exclude == 1, "justified lines on the text edge are not extra exclusions")
  -- partial page: no region is ever offered inside the type area
  local pg3 = G.page(d, { folio = 1, index = 1, twoside = true })
  G.regions(pg3, pg3.typearea, { G.rect(pg3.text.x0, pg3.text.y1 - 60, pg3.text.x1, pg3.text.y1) })
  local inside = false
  for _, r in ipairs(pg3.region_list) do if G.intersects(r, pg3.typearea) then inside = true end end
  T.ok(not inside, "partial page: no region inside the type area")
  -- title page: block = title box only
  local pg4 = G.page(d, { folio = 1, index = 1, twoside = false })
  local tbox = G.rect(pg4.text.x0, pg4.text.y1 - 80, pg4.text.x0 + 200, pg4.text.y1)
  G.regions(pg4, tbox, {})
  T.ok(pg4.regions.bottom and G.height(pg4.regions.bottom) > 200, "title page frees the space below the title box")
end
