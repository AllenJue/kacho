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
-- Tests for kacho-wash: blob robustness, layer counts/alphas, bboxes, balance.
return function(T)
  local Wsh = require("kacho-wash")
  local B = require("kacho-brush")
  local pdf = require("kacho-pdf")
  local H = require("helpers")
  local rng = require("kacho-rng")

  -- blobs never self-intersect (no even-odd holes / spikes) over many seeds
  local bad = 0
  for s = 1, 60 do
    local pts = Wsh.blob(rng.new(s), 0, 0, 30, 20, 0.5, 48)
    if B.self_crossings(pts) > 0 then bad = bad + 1 end
  end
  T.ok(bad == 0, "rough blobs (rough=0.5) never self-intersect (" .. bad .. "/60)")
  local pts = Wsh.blob(rng.new(1), 50, 50, 10, 10, 0.3, 32)
  local minr = math.huge
  for _, p in ipairs(pts) do minr = math.min(minr, math.sqrt((p[1] - 50) ^ 2 + (p[2] - 50) ^ 2)) end
  T.ok(#pts == 32 and minr > 3, "blob keeps a positive radius")

  local function alphas(be)
    local t = {}
    for _, e in ipairs(be.extgs_list) do
      local a = e[2]:match("/ca ([%d%.]+)")
      if a then t[#t + 1] = tonumber(a) end
    end
    return t
  end

  -- nijimi: >= 6 layers, every layer alpha <= 0.12, bbox covers emitted points
  local ctx = H.ctx(2)
  local bb = Wsh.nijimi(ctx, { x = 100, y = 100, rx = 30, ry = 40 }, { rgb = ctx.palette.color("momo") })
  local body = ctx.pdf:body()
  local nf = select(2, body:gsub(" f Q", ""))
  T.ok(nf >= 6, "nijimi paints >= 6 layers (" .. nf .. ")")
  local maxa = 0
  for _, a in ipairs(alphas(ctx.backend)) do maxa = math.max(maxa, a) end
  T.ok(maxa <= 0.12 + 1e-9, "nijimi per-layer alpha <= 0.12 (max " .. maxa .. ")")
  local inside = true
  for _, p in ipairs(H.path_points(body)) do
    if p[1] < bb.x0 - 0.006 or p[1] > bb.x1 + 0.006 or p[2] < bb.y0 - 0.006 or p[2] > bb.y1 + 0.006 then inside = false end
  end
  T.ok(inside, "nijimi bbox contains all emitted points")
  local ctx2 = H.ctx(2)
  Wsh.nijimi(ctx2, { x = 100, y = 100, rx = 30, ry = 40 }, { rgb = ctx2.palette.color("momo") })
  T.ok(ctx2.pdf:body() == body, "nijimi deterministic for a seed")

  -- soft wash: uses a soft mask, balanced, bbox = mask ellipse
  local c3 = H.ctx(3)
  local sb = Wsh.soft(c3, 200, 300, 40, 20, { rgb = { 0.9, 0.7, 0.7 } })
  T.ok(sb.x0 == 160 and sb.x1 == 240 and sb.y0 == 280, "soft wash bbox is the mask ellipse")
  local b3 = c3.pdf:body()
  T.ok(b3:find("/kcF%d+ gs") ~= nil and pdf.balanced(b3), "soft wash painted through a balanced soft-mask state")

  -- bokashi: pattern fill inside an axial soft-mask fade
  local c4 = H.ctx(4)
  local r = { x0 = 0, y0 = 0, x1 = 100, y1 = 50 }
  local bk = Wsh.bokashi(c4, r, c4.palette.color("bokashi-sky"), c4.palette.color("bokashi-sky-horizon"))
  local b4 = c4.pdf:body()
  T.ok(bk.x0 == 0 and bk.y1 == 50, "bokashi bbox = rect")
  T.ok(b4:find("/Pattern cs /kcP%d+ scn") ~= nil and b4:find("/kcF%d+ gs") ~= nil, "bokashi = native shading pattern through a fade mask")
  T.ok(#c4.backend.streams == 1, "bokashi fade writes one mask form")

  -- rim / mokkotsu / tarashikomi / mottle: balanced clips, bbox within shape, per-layer alpha <= 0.12
  local shape = Wsh.blob(rng.new(9), 300, 300, 25, 18, 0.25, 36)
  local c5 = H.ctx(5)
  local rb = Wsh.rim(c5, shape, { rgb = { 0.3, 0.2, 0.2 }, partial = true })
  local mb = Wsh.mokkotsu(c5, shape, { rgb = c5.palette.color("beni") })
  local tb = Wsh.tarashikomi(c5, shape, { rgb = c5.palette.color("koke") })
  local gb = Wsh.mottle(c5, shape, {})
  local lb = Wsh.lift(c5, { B.line({ 290, 300 }, { 310, 305 }) }, {})
  local b5 = c5.pdf:body()
  T.ok(pdf.balanced(b5), "rim/mokkotsu/tarashikomi/mottle/lift keep q/Q balanced")
  T.ok(rb and mb and tb and gb and lb, "all wash primitives return bboxes")
  T.ok(c5.pdf.depth == 0, "no clip left open")
  local mul = false
  for _, e in ipairs(c5.backend.extgs_list) do if e[2]:find("Multiply") then mul = true end end
  T.ok(mul, "rim darkening uses Multiply")

  -- F3 & P1: mokkotsu and band keep per-layer alpha <= 0.12 and honest bboxes
  local c6 = H.ctx(6)
  local mbb = Wsh.mokkotsu(c6, shape, { rgb = c6.palette.color("sumi-noir"), alpha = 0.9 })
  local max_m = 0
  for _, a in ipairs(alphas(c6.backend)) do max_m = math.max(max_m, a) end
  T.ok(max_m <= 0.12 + 1e-9, "mokkotsu with dark pigment keeps per-layer alpha <= 0.12 (max " .. max_m .. ")")
  local minside = true
  for _, p in ipairs(H.path_points(c6.pdf:body())) do
    if p[1] < mbb.x0 - 0.01 or p[1] > mbb.x1 + 0.01 or p[2] < mbb.y0 - 0.01 or p[2] > mbb.y1 + 0.01 then minside = false end
  end
  T.ok(minside, "mokkotsu bbox contains all emitted points")

  local c7 = H.ctx(7)
  local bbb = Wsh.band(c7, { x0 = 20, x1 = 220, y = 100, height = 40, rgb = c7.palette.color("matsuba"), alpha = 0.5 })
  local max_b = 0
  for _, a in ipairs(alphas(c7.backend)) do max_b = math.max(max_b, a) end
  T.ok(bbb and max_b <= 0.12 + 1e-9 and pdf.balanced(c7.pdf:body()), "Wsh.band balanced with per-layer alpha <= 0.12")
end
