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
-- Tests for kacho-brush: Bézier math, outline robustness, bbox honesty, dry brush.
return function(T)
  local B = require("kacho-brush")
  local H = require("helpers")

  local sg = { { 0, 0 }, { 0, 10 }, { 10, 10 }, { 10, 0 } }
  local x, y = B.bez(sg, 0.5)
  T.near(x, 5, 1e-9, "bez midpoint x"); T.near(y, 7.5, 1e-9, "bez midpoint y")
  local a, b = B.split(sg, 0.3)
  local ax, ay = B.bez(a, 1)
  local bx, by = B.bez(sg, 0.3)
  T.ok(math.abs(ax - bx) < 1e-9 and math.abs(ay - by) < 1e-9, "split joins at the split point")
  T.ok(#B.normalize(sg) == 1, "single cubic is normalized to a chain")

  -- chain is C1: handles collinear across joins
  local ch = B.chain({ { 0, 0 }, { 30, 20 }, { 60, 0 }, { 90, 30 } })
  local c1 = true
  for i = 1, #ch - 1 do
    local p, q = ch[i], ch[i + 1]
    local d1x, d1y = p[4][1] - p[3][1], p[4][2] - p[3][2]
    local d2x, d2y = q[2][1] - q[1][1], q[2][2] - q[1][2]
    if math.abs(d1x * d2y - d1y * d2x) > 1e-6 or (d1x * d2x + d1y * d2y) <= 0 then c1 = false end
    if p[4][1] ~= q[1][1] or p[4][2] ~= q[1][2] then c1 = false end
  end
  T.ok(c1, "chain() is C1-continuous (collinear handles, shared endpoints)")

  -- spine sampling and arc-length evaluation
  local line = { B.line({ 0, 0 }, { 100, 0 }) }
  local S, L = B.spine(line)
  T.near(L, 100, 1e-6, "spine length of a straight segment")
  local ex, ey, tx, ty = B.at(S, 0.25)
  T.near(ex, 25, 1e-6, "at(0.25) on a straight line"); T.near(tx, 1, 1e-9, "tangent of a straight line")
  local px = B.eval(line, 0.5)
  T.near(px, 50, 1e-6, "eval(segs, 0.5)")

  -- hairpin: tight bend; outline must be loop-free and not self-crossing
  local hp = { { { 0, 0 }, { 0, 60 }, { 12, 60 }, { 12, 0 } } }
  local Sh = B.spine(hp)
  local wfn = function(u) return 46 * B.profile.both(u) end
  local out = B.outline(Sh, wfn)
  -- winding number of the closed outline at (x, y)
  local function winding(poly, x, y)
    local w = 0
    for i = 1, #poly do
      local a, b = poly[i], poly[i % #poly + 1]
      if a[2] <= y then
        if b[2] > y and ((b[1] - a[1]) * (y - a[2]) - (x - a[1]) * (b[2] - a[2])) > 0 then w = w + 1 end
      elseif b[2] <= y and ((b[1] - a[1]) * (y - a[2]) - (x - a[1]) * (b[2] - a[2])) < 0 then w = w - 1 end
    end
    return w
  end
  -- every point well inside the brush -- on the normal of a spine sample within
  -- 0.6 of its curvature-clamped half width -- must be painted (winding ~= 0)
  local function pinholes(poly, Sp, wf)
    local holes = 0
    for _, p in ipairs(Sp) do
      local h0 = wf(p.u) / 2
      if h0 >= 0.5 then
        for t = -0.6, 0.6, 0.05 do
          local h = h0     -- the curvature clamp applies to the inner side only
          if (t > 0 and p.k > 0) or (t < 0 and p.k < 0) then h = math.min(h, 0.85 / math.abs(p.k)) end
          if winding(poly, p.x - p.ty * h * t, p.y + p.tx * h * t) == 0 then holes = holes + 1 end
        end
      end
    end
    return holes
  end
  T.ok(pinholes(out, Sh, wfn) == 0, "hairpin (46bp wide, 12bp bend): no unpainted pinholes inside the stroke")
  local spur = 0
  for _, q in ipairs(out) do
    local dmin = math.huge
    for _, p in ipairs(Sh) do dmin = math.min(dmin, math.sqrt((q[1] - p.x) ^ 2 + (q[2] - p.y) ^ 2)) end
    if dmin > 23.5 * 1.08 then spur = spur + 1 end
  end
  T.ok(spur == 0, "hairpin outline has no swallowtail spurs beyond the brush radius")
  T.ok(B.area2(out) > 0, "outline is counter-clockwise (safe for nonzero unions with discs)")

  -- F2: genuine spine loop (figure-8 / self-crossing cubic) is preserved without pinholes
  local loop_seg = { { { 0, 0 }, { 80, 60 }, { -40, 60 }, { 40, 0 } } }
  local Sl = B.spine(loop_seg)
  local wf_l = function(u) return 14 * B.profile.both(u) end
  local out_l = B.outline(Sl, wf_l)
  T.ok(pinholes(out_l, Sl, wf_l) == 0, "genuine spine loop is not spliced out by outline/deloop")

  -- deloop removes a simple loop
  local loop = { { 0, 0 }, { 10, 0 }, { 10, 10 }, { 5, -5 }, { 20, -5 } }
  local dl = B.deloop(loop)
  local crossings = 0
  for i = 1, #dl - 1 do for j = i + 2, #dl - 1 do if B.seg_cross(dl[i], dl[i + 1], dl[j], dl[j + 1]) then crossings = crossings + 1 end end end
  T.ok(crossings == 0 and #dl < #loop + 1, "deloop splices out a crossing loop")

  -- stroke: bbox honestly contains every emitted coordinate
  local ctx = H.ctx(3)
  local segs = B.chain({ { 100, 100 }, { 130, 160 }, { 120, 220 }, { 160, 260 } })
  local bb = B.stroke(ctx, segs, { w = 8, profile = "branch", rgb = { 0, 0, 0 }, alpha = 0.9, cap = true, joints = { { 130, 160, 3 } } })
  local body = ctx.pdf:body()
  local inside = true
  for _, p in ipairs(H.path_points(body)) do
    if p[1] < bb.x0 - 0.006 or p[1] > bb.x1 + 0.006 or p[2] < bb.y0 - 0.006 or p[2] > bb.y1 + 0.006 then inside = false end
  end
  T.ok(inside, "stroke bbox contains all emitted path points")
  T.ok(bb.x0 < 100 and bb.y0 < 100, "bbox includes the round start cap")

  -- P4: outline_path, crotch, and fork produce a single compound fill without double-darkening
  local cf = H.ctx(7)
  local pS = B.spine(segs)
  local ch1 = B.offshoot(pS, 0.45, math.pi * 0.7, 45, 0.4, 0.1)
  local ch2 = B.offshoot(pS, 0.75, math.pi * 0.25, 38, 0.4, -0.1)
  local opath = B.outline_path(cf, segs, { w = 8, profile = "branch" })
  T.ok(opath and opath.s and cf.pdf:is_empty(), "outline_path builds path without painting")
  local fbb = B.fork(cf, { segs = segs, w = 8, profile = "branch" }, {
    { segs = ch1, u = 0.45, w = 4.5, profile = "branch" },
    { segs = ch2, u = 0.75, w = 3.6, profile = "twig" },
  }, { rgb = { 0.1, 0.1, 0.1 }, alpha = 0.85 })
  local fbody = cf.pdf:body()
  local ffills = select(2, fbody:gsub(" f Q", ""))
  T.ok(fbb and ffills == 1, "B.fork paints parent + children + crotch fillets in one compound fill")
  T.near(B.profile.branch(1), 0, 1e-6, "branch profile rounds smoothly to 0 at tip")

  -- every profile is finite and in [0, ~1]
  local okp = true
  for name, f in pairs(B.profile) do
    for i = 0, 100 do local v = f(i / 100); if v ~= v or v < 0 or v > 1.0001 then okp = false; io.write("  bad profile ", name, "\n") end end
  end
  T.ok(okp, "all width profiles finite in [0,1]")
  T.raises(function() B.stroke(H.ctx(1), segs, { profile = "nope" }) end, "unknown profile raises")

  -- zero-length spine does not crash and paints nothing harmful
  local okz = pcall(function() B.stroke(H.ctx(1), { { { 5, 5 }, { 5, 5 }, { 5, 5 }, { 5, 5 } } }, { w = 3 }) end)
  T.ok(okz, "zero-length spine does not crash")

  -- dry brush: deterministic, one bristle fill + under-layer, dryness clamped
  local function dry_body(seed, dryness)
    local c = H.ctx(seed)
    local bbd = B.dry(c, segs, { w = 10, rgb = { 0.2, 0.2, 0.2 }, alpha = 0.9, dryness = dryness })
    return c.pdf:body(), bbd
  end
  local d1, bb1 = dry_body(5, 0.5)
  local d2 = dry_body(5, 0.5)
  T.ok(d1 == d2, "dry brush deterministic for a seed")
  local nfills = select(2, d1:gsub(" f Q", ""))
  T.ok(nfills == 2, "dry brush = under-layer fill + one compound bristle fill (" .. nfills .. ")")
  T.ok(bb1 and bb1.x1 > bb1.x0, "dry brush returns a bbox")
  local d3 = dry_body(5, 5.0)
  local d4 = dry_body(5, 0.6)
  T.ok(d3 == d4, "dryness is clamped to <= 0.6 (no stray blobs)")

  local db = B.dot(H.ctx(1), 10, 10, 2, { rgb = { 0, 0, 0 } })
  T.ok(db and db.x0 >= 7.9 and db.x1 <= 12.1, "dot bbox")
end
