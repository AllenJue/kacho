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
-- Unit tests for the M2 motif library: kacho-growth invariants, kacho-ink
-- glazing primitives, and flora / fauna / scenery / seal behaviour.
return function(T)
  local H = require("helpers")
  local GR = require("kacho-growth")
  local F = require("kacho-flora")
  local FA = require("kacho-fauna")
  local SC = require("kacho-scenery")
  local SE = require("kacho-seal")
  local rng = require("kacho-rng")
  local pi = math.pi

  local REGION = { x0 = 20, y0 = 20, x1 = 300, y1 = 780 }
  local EXCL = { x0 = 320, y0 = 60, x1 = 575, y1 = 780 }
  local function mkctx(seed, pal)
    local c = H.ctx(seed or 1, pal or "sumi")
    c.region = { x0 = REGION.x0, y0 = REGION.y0, x1 = REGION.x1, y1 = REGION.y1 }
    c.safe = { x0 = 14, y0 = 14, x1 = 581, y1 = 828 }
    c.exclude = { EXCL }
    c.density = 0.5
    c.recs = {}
    c.record = function(kind, b) c.recs[#c.recs + 1] = { kind = kind, bbox = b }; return b end
    return c
  end
  local function inside(b, r, eps)
    eps = eps or 0.01
    return b.x0 >= r.x0 - eps and b.y0 >= r.y0 - eps and b.x1 <= r.x1 + eps and b.y1 <= r.y1 + eps
  end
  local function hits(b, r) return b.x0 < r.x1 and r.x0 < b.x1 and b.y0 < r.y1 and r.y0 < b.y1 end
  local function bleed(kind)
    for tok in kind:gmatch("[^%-_:%.]+") do
      if tok == "trunk" or tok == "culm" or tok == "stem" or tok == "vine" then return true end
    end
    return false
  end
  local function check_records(c, name)
    local bad_region, bad_excl, n = 0, 0, 0
    for _, r in ipairs(c.recs) do
      n = n + 1
      if hits(r.bbox, EXCL) then bad_excl = bad_excl + 1 end
      if not bleed(r.kind) and not inside(r.bbox, REGION) then bad_region = bad_region + 1 end
    end
    T.ok(n > 0, name .. ": logs its pieces (" .. n .. ")")
    T.ok(bad_excl == 0, name .. ": no piece intersects the exclusion (" .. bad_excl .. ")")
    T.ok(bad_region == 0, name .. ": non-bleed pieces stay inside the region (" .. bad_region .. ")")
  end
  local function has_kind(c, pat)
    for _, r in ipairs(c.recs) do if r.kind:find(pat) then return true end end
    return false
  end

  ---------------------------------------------------------------- growth engine
  for _, sp in ipairs({ "ume", "sakura", "maple", "osmanthus", "camellia", "pine" }) do
    local ctx = { rng = rng.new(11), region = REGION, exclude = { EXCL }, density = 0.6 }
    local sk = GR.grow(ctx, { origins = { { x = 150, y = 30, angle = pi / 2 } }, size = 360, species = sp })
    local c = GR.check(sk)
    T.ok(#sk.branches >= 2 and c.forks >= 1, sp .. ": skeleton branches (" .. #sk.branches .. ", forks " .. c.forks .. ")")
    T.ok(c.max_pipe_err < 1e-9, sp .. ": pipe model w^p = sum child w^p at every fork (err " .. c.max_pipe_err .. ")")
    T.ok(c.detached == 0, sp .. ": every lateral starts exactly on a node of its parent")
    T.ok(c.taper_violations == 0, sp .. ": widths never increase toward the tips")
    -- branching angles of laterals within [25, 60] deg (+kink tolerance) of the leader
    local P = GR.SPECIES[sp]
    local bad = 0
    for _, n in ipairs(sk.nodes) do
      if #n.children > 1 then
        local a1 = math.atan(n.children[1].y - n.y, n.children[1].x - n.x)
        for k = 2, #n.children do
          local a2 = math.atan(n.children[k].y - n.y, n.children[k].x - n.x)
          local d = math.abs((a2 - a1 + pi) % (2 * pi) - pi)
          if d < math.rad(P.angle_min) - 0.02 or d > math.rad(P.angle_max) + P.kink + 0.6 then bad = bad + 1 end
        end
      end
    end
    T.ok(bad == 0, sp .. ": branching angles respect the species range (" .. bad .. " off)")
    -- no node inside the exclusion: growth bends around the text
    local inx = 0
    for _, n in ipairs(sk.nodes) do
      if n.x > EXCL.x0 and n.x < EXCL.x1 and n.y > EXCL.y0 and n.y < EXCL.y1 then inx = inx + 1 end
    end
    T.ok(inx == 0, sp .. ": no skeleton node inside the exclusion")
  end
  -- orders form a hierarchy: a lateral's order is its parent's + 1
  do
    local ctx = { rng = rng.new(3), region = REGION, exclude = {}, density = 0.7 }
    local sk = GR.grow(ctx, { origins = { { x = 150, y = 30, angle = pi / 2 } }, size = 380, species = "sakura" })
    local bad, maxo = 0, 0
    for _, br in ipairs(sk.branches) do
      if br.parent and br.order ~= br.parent.order + 1 then bad = bad + 1 end
      maxo = math.max(maxo, br.order)
    end
    T.ok(bad == 0 and maxo >= 2 and maxo <= GR.SPECIES.sakura.max_order, "growth: branch orders 0.." .. maxo .. " form a hierarchy")
    local fl = GR.to_branches(sk)
    local mono = true
    for _, b in ipairs(fl) do
      for i = 2, #b.nodes do if b.nodes[i].w > b.nodes[i - 1].w + 1e-9 then mono = false end end
      if b.parent then
        local px, py = F.eval_at(b.parent, b.attach_s)
        if math.abs(px - b.nodes[1].x) > 1e-6 or math.abs(py - b.nodes[1].y) > 1e-6 then mono = false end
        local _, _, pw = F.eval_at(b.parent, b.attach_s)
        if b.nodes[1].w > pw + 1e-6 then mono = false end
      end
    end
    T.ok(mono, "to_branches: monotone taper, child starts on the parent and no wider than it")
  end
  -- determinism
  do
    local function run()
      local ctx = { rng = rng.new(42), region = REGION, exclude = { EXCL }, density = 0.5 }
      local sk = GR.grow(ctx, { origins = { { x = 150, y = 30, angle = pi / 2 } }, size = 300, species = "ume" })
      local t = {}
      for _, n in ipairs(sk.nodes) do t[#t + 1] = string.format("%.3f,%.3f,%.3f", n.x, n.y, n.w) end
      return table.concat(t, ";")
    end
    T.ok(run() == run(), "growth: same seed gives the same skeleton")
  end

  ---------------------------------------------------------------- flora motifs
  local motifs = {
    { "ume", { x = 150, y = 30, size = 360, angle = pi / 2 }, "ume%-blossom" },
    { "sakura", { x = 150, y = 30, size = 360, angle = pi / 2 }, "sakura%-blossom" },
    { "maple", { x = 150, y = 30, size = 360, angle = pi / 2 }, "maple%-leaf" },
    { "osmanthus", { x = 150, y = 30, size = 360, angle = pi / 2 }, "osmanthus%-leaf" },
    { "camellia", { x = 150, y = 30, size = 360, angle = pi / 2 }, "camellia%-leaf" },
    { "bamboo", { x = 150, y = 30, size = 500 }, "bamboo%-leaf" },
    { "orchid", { x = 150, y = 60, size = 220 }, "orchid%-leaf" },
    { "iris", { x = 150, y = 60, size = 300 }, "iris%-flower" },
    { "wisteria", { x = 30, y = 700, size = 260, angle = 0 }, "wisteria%-raceme" },
    { "narcissus", { x = 150, y = 60, size = 220 }, "narcissus%-flower" },
    { "pine", { x = 150, y = 30, size = 400 }, "pine%-needles" },
    { "chrysanthemum", { x = 150, y = 60, size = 260 }, "chrysanthemum%-flower" },
  }
  for _, m in ipairs(motifs) do
    for _, pal in ipairs({ "sumi", "hanga" }) do
      local c = mkctx(5, pal)
      local spec = {}
      for k, v in pairs(m[2]) do spec[k] = v end
      local ok, bb, info = pcall(F[m[1]], c, spec)
      T.ok(ok and bb ~= nil, m[1] .. "/" .. pal .. ": draws (" .. tostring(ok and "ok" or bb) .. ")")
      if ok and bb then
        check_records(c, m[1] .. "/" .. pal)
        T.ok(has_kind(c, m[3]), m[1] .. "/" .. pal .. ": logs kind " .. m[3])
        T.ok(H and require("kacho-pdf").balanced(c.pdf:body()), m[1] .. "/" .. pal .. ": balanced q/Q")
      end
    end
  end
  -- ume blossoms are attached: every blossom/bud lies within 1.6 r of a twig node
  do
    local c = mkctx(9, "hanga")
    local _, info = F.ume(c, { x = 150, y = 30, size = 360, angle = pi / 2 })
    local far = 0
    for _, it in ipairs(info.items) do
      local best = math.huge
      for _, br in ipairs(info.tree) do
        local nd = br.nodes
        for i = 1, #nd - 1 do   -- distance to each painted segment
          local ax, ay, bx, by = nd[i].x, nd[i].y, nd[i + 1].x, nd[i + 1].y
          local vx, vy = bx - ax, by - ay
          local t = math.max(0, math.min(1, ((it.x - ax) * vx + (it.y - ay) * vy) / math.max(1e-9, vx * vx + vy * vy)))
          local d = math.sqrt((ax + vx * t - it.x) ^ 2 + (ay + vy * t - it.y) ^ 2) - (nd[i].w + (nd[i + 1].w - nd[i].w) * t) / 2
          best = math.min(best, d)
        end
      end
      if best > it.r * 1.6 + 2 then far = far + 1 end
    end
    T.ok(#info.items >= 10, "ume: places blossom clusters (" .. #info.items .. ")")
    T.ok(far == 0, "ume: no floating blossom (" .. far .. " far from every twig)")
    local cl = {}
    for _, it in ipairs(info.items) do if it.cluster and it.cluster > 0 then cl[it.cluster] = (cl[it.cluster] or 0) + 1 end end
    local multi = 0
    for _, n in pairs(cl) do if n >= 2 then multi = multi + 1 end end
    T.ok(multi >= 3, "ume: blossoms grow in clusters of 2+ (" .. multi .. " clusters)")
  end
  -- determinism of a whole motif
  do
    local function run()
      local c = mkctx(77, "sumi")
      F.sakura(c, { x = 150, y = 30, size = 300, angle = pi / 2 })
      return c.pdf:body()
    end
    T.ok(run() == run(), "sakura: same seed gives identical PDF content")
  end
  -- a motif that cannot fit draws nothing and does not raise
  do
    local c = mkctx(1, "sumi")
    c.region = { x0 = 20, y0 = 20, x1 = 26, y1 = 26 }
    local ok, bb = pcall(F.orchid, c, { x = 23, y = 23, size = 200 })
    T.ok(ok and bb == nil, "orchid: nothing fits in a 6 bp region -> nil, no error")
  end
  -- spec.region restricts growth
  do
    local c = mkctx(4, "sumi")
    local sub = { x0 = 40, y0 = 40, x1 = 200, y1 = 400 }
    F.ume(c, { x = 120, y = 50, size = 300, angle = pi / 2, region = sub })
    local out = 0
    for _, r in ipairs(c.recs) do if not bleed(r.kind) and not inside(r.bbox, sub) then out = out + 1 end end
    T.ok(#c.recs > 0 and out == 0, "ume: spec.region limits every piece (" .. out .. " outside)")
  end
  -- wispy secondary flora & C^1 branch_path
  do
    local r = rng.new(21)
    local pts5, bez5 = F.branch_path({ 100, 100 }, { 140, 150 }, pi / 2, pi / 3, r)
    T.ok(#pts5 >= 8 and #bez5 == 4 and math.abs(pts5[1][1] - 100) < 1e-6 and math.abs(pts5[#pts5][1] - 140) < 1e-6,
      "branch_path (5-arg): C^1 cubic Bezier polyline from p0 to p1")
    local pts9, bez9 = F.branch_path(r, 100, 100, 0, 1, 140, 150, 0.5, 0.866)
    T.ok(#pts9 >= 8 and #bez9 == 4 and math.abs(pts9[1][2] - 100) < 1e-6 and math.abs(pts9[#pts9][2] - 150) < 1e-6,
      "branch_path (9-arg): florilegium signature compatibility")
    local wispy = {
      { "cyme", { x = 140, y = 200, size = 30, angle = pi / 3, stalk_from = { 120, 180 } }, "cyme" },
      { "umbel", { x = 140, y = 300, size = 26, angle = pi / 2, stalk_from = { 130, 275 } }, "umbel" },
      { "sprig", { x = 140, y = 400, size = 28, angle = pi / 4, stalk_from = { 120, 380 } }, "sprig" },
      { "tendril", { x = 140, y = 500, size = 24, angle = pi / 3 }, "tendril" },
      { "leaf_pair", { x = 140, y = 580, size = 22, angle = pi / 2 }, "leaf%-pair" },
      { "stalked_bud", { x = 140, y = 650, size = 18, angle = pi / 3 }, "stalked%-bud" },
    }
    for _, pal in ipairs({ "sumi", "hanga" }) do
      local cw = mkctx(23, pal)
      for _, w in ipairs(wispy) do
        local bb = F[w[1]](cw, w[2])
        T.ok(bb ~= nil and has_kind(cw, w[3]), w[1] .. "/" .. pal .. ": drawn and logged")
      end
      check_records(cw, "wispy/" .. pal)
      T.ok(require("kacho-pdf").balanced(cw.pdf:body()), "wispy/" .. pal .. ": balanced q/Q")
    end
  end

  ---------------------------------------------------------------- fauna
  do
    local c = mkctx(8, "sumi")
    local perch = { cx = 150, cy = 300, angle = 0.1, w = 5 }
    local bb, info = FA.bird(c, { perch = perch, kind = "robin", size = 44 })
    T.ok(bb ~= nil and has_kind(c, "robin"), "robin: drawn and logged")
    if bb then
      -- feet on the branch top: within w/2 of the perch centre line
      local ok = true
      for _, f in ipairs(info.feet) do
        local d = math.abs((f[2] - perch.cy) * math.cos(perch.angle) - (f[1] - perch.cx) * math.sin(perch.angle))
        if math.abs(d - perch.w / 2) > 0.5 then ok = false end
      end
      T.ok(ok, "robin: feet grip the top of the branch")
      T.ok(bb.y0 <= perch.cy + perch.w / 2 and bb.y1 > perch.cy, "robin: bbox touches the branch")
    end
    for _, k in ipairs({ "uguisu", "sparrow", "mejiro" }) do
      local c2 = mkctx(8, "hanga")
      local b = FA.bird(c2, { perch = perch, kind = k, size = 40 })
      T.ok(b ~= nil and #c2.recs == 1 and c2.recs[1].kind:find("bird") or (c2.recs[1] and c2.recs[1].kind == k),
        k .. ": drawn and logged as a bird kind")
    end
    local c3 = mkctx(8, "sumi")
    T.ok(FA.bird(c3, { perch = { cx = 318, cy = 300, angle = 0, w = 4 }, kind = "robin", size = 44 }) == nil and #c3.recs == 0,
      "bird: does not draw when it would cross the exclusion")
    local c4 = mkctx(8, "sumi")
    T.ok(FA.swallow(c4, { x = 150, y = 500, size = 60, angle = 0.2 }) ~= nil and has_kind(c4, "swallow"), "swallow: drawn and logged")
  end

  ---------------------------------------------------------------- scenery
  do
    local c = mkctx(6, "hanga")
    T.ok(SC.rock(c, { x = 150, y = 40, size = 200 }) ~= nil and has_kind(c, "^rock$"), "rock: drawn and logged")
    T.ok(SC.cliffs(c, { x = 150, y = 180, width = 150, height = 160 }) ~= nil and has_kind(c, "cliffs"), "cliffs: drawn and logged")
    T.ok(SC.waves(c, { x0 = 30, x1 = 290, y = 300, height = 110 }) ~= nil and has_kind(c, "waves"), "waves: drawn and logged")
    T.ok(SC.tanzaku(c, { x = 260, y = 740, width = 24, height = 84 }) ~= nil and has_kind(c, "tanzaku"), "tanzaku: drawn and logged")
    T.ok(SC.fuji(c, { x = 160, y = 420, width = 240 }) ~= nil and has_kind(c, "fuji"), "fuji: drawn and logged")
    T.ok(SC.kasumi(c, { x0 = 30, x1 = 290, y = 420, height = 16, bands = 2 }) ~= nil and has_kind(c, "kasumi"), "kasumi: drawn and logged")
    T.ok(SC.sky(c, { rect = { x0 = 30, y0 = 400, x1 = 290, y1 = 760 } }) ~= nil and has_kind(c, "bokashi"), "sky: drawn and logged")
    T.ok(SC.bank(c, { x0 = 30, x1 = 290, y = 24, height = 30 }) ~= nil and has_kind(c, "bank"), "bank: drawn and logged")
    check_records(c, "scenery")
    -- the bank crest passes through its root point region (trunk rooted in it)
    local c2 = mkctx(6, "sumi")
    local _, info = SC.bank(c2, { x0 = 40, x1 = 280, y = 24, height = 30, root = { x = 160, y = 40, w = 10 } })
    T.ok(info and info.crest(160) > 24 + 15, "bank: crest rises under the root point")
    -- a rock too big for the region shrinks, then fits
    local c3 = mkctx(6, "sumi")
    local b = SC.rock(c3, { x = 150, y = 40, size = 300 })
    T.ok(b ~= nil and inside(b, REGION), "rock: shrinks to fit the region")
  end

  ---------------------------------------------------------------- seal
  do
    for _, st in ipairs({ "hakubun", "shubun" }) do
      for _, shape in ipairs({ "square", "oval", "tall" }) do
        local c = mkctx(13, "sumi")
        local b, info = SE.hanko(c, { x = 150, y = 400, size = 30, style = st, shape = shape })
        T.ok(b ~= nil and info.style == st and has_kind(c, "seal"), "seal " .. st .. "/" .. shape .. ": drawn and logged")
        if b then
          local h = b.y1 - b.y0
          T.ok(h > 20 and h < 60, "seal " .. st .. "/" .. shape .. ": plausible size (" .. string.format("%.1f", h) .. ")")
        end
      end
    end
    local glyph = SE.glyph(rng.new(3), 0, 0, 20, 20, 1.5, 1)
    local ok = #glyph >= 3
    for _, r in ipairs(glyph) do if r[1] < -1e-9 or r[2] < -1e-9 or r[3] > 20 + 1e-9 or r[4] > 20 + 1e-9 then ok = false end end
    T.ok(ok, "seal glyph: strokes fill and stay inside the cell (" .. #glyph .. ")")
    local c = mkctx(13, "sumi")
    T.ok(SE.hanko(c, { x = 330, y = 400, size = 30 }) == nil and #c.recs == 0, "seal: refuses to overlap the exclusion")
  end

  ---------------------------------------------------------------- ink glazing
  do
    local INK = require("kacho-ink")
    local c = mkctx(17, "hanga")
    local r = rng.new(19)
    local poly = { { 80, 100 }, { 90, 95 }, { 110, 100 }, { 90, 105 } }
    INK.begin(c.pdf, { 0.50, 0.36, 0.68 })
    INK.glaze_petal(r, poly, 80, 100, 110, 100, 10, { vein_color = { 0.22, 0.15, 0.38 }, signal_color = { 0.92, 0.76, 0.22 } })
    local b4 = INK.finish()
    T.ok(b4 and math.abs(b4.x0 - 80) < 1e-6 and math.abs(b4.x1 - 110) < 1e-6, "ink.glaze_petal: stays strictly within polygon bbox")
    INK.begin(c.pdf, { 0.28, 0.44, 0.22 })
    INK.glaze_leaf(r, poly, 80, 100, 110, 100, 10, {})
    local b5 = INK.finish()
    T.ok(b5 and math.abs(b5.y0 - 95) < 1e-6 and math.abs(b5.y1 - 105) < 1e-6, "ink.glaze_leaf: stays strictly within polygon bbox")
    INK.begin(c.pdf, { 0.96, 0.72, 0.78 })
    INK.push()
    INK.translate(100, 200)
    INK.scale(14, 14)
    INK.petal(r, { notch = 0.22, w = 0.42 })
    INK.leaf(r, { w = 0.40, serrate = 0.08 })
    INK.maple_leaf(r, { lobes = 7 })
    INK.pop()
    local b_all = INK.finish()
    T.ok(b_all and b_all.x1 > b_all.x0 and b_all.y1 > b_all.y0, "ink.begin/finish: tracks cumulative glazed bbox")
    T.ok(require("kacho-pdf").balanced(c.pdf:body()), "ink primitives: balanced q/Q PDF state")
  end
end
