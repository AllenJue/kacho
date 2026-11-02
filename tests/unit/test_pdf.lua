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
-- Tests for kacho-pdf: q/Q balance, NaN guard, ExtGState caching, shadings, groups.
return function(T)
  local pdf = require("kacho-pdf")
  local H = require("helpers")
  local be = H.backend()
  local R = pdf.registry(be)
  local W = pdf.new(R)

  T.ok(pdf.num(1.230) == "1.23" and pdf.num(-0.001) == "0" and pdf.num(5) == "5", "number formatting")
  T.ok(tonumber(pdf.num(1e30)) <= 1e5 and tonumber(pdf.num(-1e30)) >= -1e5, "extreme coordinates clamped to [-1e5, 1e5]")
  T.ok(W:poly({ { 0, 0 }, { 0 / 0, 1 } }, true) == nil, "path with NaN is dropped")
  T.ok(W:poly({ { 0, 0 }, { math.huge, 1 } }, true) == nil, "path with inf is dropped")
  T.ok(W:fill(nil, { 0, 0, 0 }, 0.5) == nil, "fill(nil) paints nothing")

  local p = W:poly({ { 10, 10 }, { 20, 10 }, { 20, 30 } }, true)
  local bb = W:fill(p, { 1, 0, 0 }, 0.5)
  T.ok(bb.x0 == 10 and bb.y1 == 30, "fill returns the path bbox")
  W:fill(p, { 0, 1, 0 }, 0.5)
  W:fill(p, { 0, 1, 0 }, 0.501)     -- quantizes to the same state
  T.ok(#be.extgs_list == 1, "ExtGState registered once per (alpha, blend)")
  W:fill(p, { 0, 1, 0 }, 0.5, { blend = "multiply" })
  T.ok(#be.extgs_list == 2 and be.extgs_list[2][2]:find("/BM /Multiply"), "multiply blend gets its own ExtGState")
  W:fill(p, { 0, 0, 1 }, 1)
  T.ok(#be.extgs_list == 2, "opaque normal fill needs no ExtGState")
  T.raises(function() W:fill(p, { 0, 0, 0 }, 0.5, { blend = "weird" }) end, "unknown blend raises")

  local sb = W:stroke(p, { 0, 0, 0 }, 2, 1)
  T.ok(sb.x0 == 9 and sb.y1 == 31, "stroke bbox inflated by half the width")

  W:clip(W:rect(0, 0, 50, 50))
  W:fill(W:circle(25, 25, 10), { 0.2, 0.2, 0.2 }, 0.3)
  T.raises(function() W:layer(30) end, "layer change inside an open clip raises")
  T.raises(function() W:pieces() end, "flush with an open clip raises")
  W:unclip()
  T.raises(function() W:unclip() end, "unbalanced unclip raises")

  local pat = W:axial(0, 100, 0, 0, { { 0, { 1, 0.8, 0.4 } }, { 1, { 1, 1, 1 } } })
  local pat2 = W:axial(0, 100, 0, 0, { { 0, { 1, 0.8, 0.4 } }, { 1, { 1, 1, 1 } } })
  T.ok(pat == pat2 and #be.patterns == 1, "identical shadings are cached")
  local pat3 = W:axial(0, 0, 100, 0, { { 0, { 1, 0, 0 } }, { 0.5, { 0, 1, 0 } }, { 1, { 0, 0, 1 } } })
  T.ok(pat3 ~= pat, "multi-stop shading registered")
  local stitched = false
  for _, o in ipairs(be.objs) do if o:find("/FunctionType 3") then stitched = true end end
  T.ok(stitched, ">2 stops use a stitching function")
  W:fill_pattern(W:rect(0, 0, 100, 100), pat, 0.8)
  local f = W:fade_radial(50, 50, 30, 20, 0.1)
  T.ok(f:match("^kcF%d+$") ~= nil and be.extgs_list[#be.extgs_list][2]:find("/SMask"), "radial soft mask registered as ExtGState")
  local fa = W:fade_axial(0, 0, 0, 100, 1, 0, { x0 = 0, y0 = 0, x1 = 100, y1 = 100 })
  T.ok(fa ~= f and #be.streams == 2, "axial soft mask writes a form stream")
  W:with_gs(f, function() W:fill(W:circle(50, 50, 40), { 0.5, 0.5, 0.5 }, 0.4) end)

  local gb = W:group(function(g)
    g:fill(g:circle(10, 10, 5), { 1, 0, 0 }, 1)
    g:fill(g:circle(14, 10, 5), { 0, 0, 1 }, 1)
  end, 0.5)
  T.ok(gb and gb.x0 == 5 and gb.x1 == 19, "group returns bbox of its content")
  local pieces = W:pieces()
  local kinds = {}
  for _, pc in ipairs(pieces) do kinds[#kinds + 1] = pc.kind end
  T.ok(table.concat(kinds, ","):find("group") ~= nil, "group appears as its own output piece")
  local body = W:body()
  T.ok(pdf.balanced(body), "q/Q balanced in the flattened page content")
  T.ok(not body:find("nan") and not body:find("inf"), "no nan/inf in output")
  T.ok(not pdf.balanced("q q Q") and not pdf.balanced("Q q"), "balance checker detects imbalance")

  -- layers paint in numeric order
  local W2 = pdf.new(pdf.registry(nil))
  W2:layer(40); W2:put("% forty")
  W2:layer(10); W2:put("% ten")
  local s = W2:body()
  T.ok(s:find("ten") < s:find("forty"), "lower layers are emitted first")

  -- join and ellipse
  local j = W2:join(W2:circle(0, 0, 1), nil, W2:circle(5, 0, 1))
  T.ok(j and j.bbox.x0 <= -1 and j.bbox.x1 >= 6, "join skips nil and unions bboxes")
  T.ok(W2:ellipse(0, 0, -1, 1) == nil, "degenerate ellipse rejected")
  local sm = W2:smooth({ { 0, 0 }, { 10, 5 }, { 20, 0 }, { 30, 5 } }, false)
  T.ok(sm.s:find(" c") ~= nil, "smooth path uses cubic curves")

  -- F4: non-finite channels/widths/radii and duplicate stops are sanitized
  local be3 = H.backend()
  local W3 = pdf.new(pdf.registry(be3))
  T.ok(W3:fill(p, { 0 / 0, 1 / 0, -1 / 0 }, 0.5) ~= nil and not W3:body():find("nan") and not W3:body():find("inf"),
    "fill with NaN/inf channels sanitizes to valid RGB")
  T.ok(W3:stroke(p, { 0, 0, 0 }, 0 / 0, 0.5) == nil, "stroke with NaN width is dropped")
  T.ok(W3:axial(0, 0, 10, 0, {}) == nil, "axial with empty stops returns nil")
  T.ok(W3:radial(0, 0, 0, 10, { { 0, { 0, 0, 0 } }, { 1, { 1, 1, 1 } } }, { sy = 0 }) == nil, "radial with sy=0 returns nil")
  T.ok(W3:fade_radial(0, 0, 0, 10, 0.1) == nil, "fade_radial with rx=0 returns nil")
  local dup = W3:axial(0, 0, 10, 0, { { 0, { 1, 0, 0 } }, { 0.5, { 0, 1, 0 } }, { 0.5, { 0, 0, 1 } }, { 1, { 1, 1, 1 } } })
  T.ok(dup ~= nil, "duplicate t stops are deduplicated without degenerate bounds")
end
