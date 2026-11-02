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
-- Tests for kacho-rng: golden vector, determinism, independence of streams.
return function(T)
  local rng = require("kacho-rng")

  local r = rng.new(1)
  local got = {}
  for i = 1, 5 do got[i] = r.next_u32() end
  -- reference: JavaScript mulberry32 with Math.imul, seed 1
  local want = { 2693262067, 11749833, 2265367787, 4213581821, 4159151403 }
  local same = true
  for i = 1, 5 do if got[i] ~= want[i] then same = false end end
  T.ok(same, "mulberry32(1) matches the reference vector")

  local a, b = rng.new(42), rng.new(42)
  local eq = true
  for _ = 1, 10000 do if a.u() ~= b.u() then eq = false; break end end
  T.ok(eq, "same seed gives identical 10k-draw streams")

  local c, d = rng.new(1), rng.new(2)
  local diff = 0
  for _ = 1, 100 do if c.u() ~= d.u() then diff = diff + 1 end end
  T.ok(diff > 95, "different seeds diverge")

  local e = rng.new(7)
  local sum, lo, hi = 0, 1, 0
  for _ = 1, 100000 do local v = e.u(); sum = sum + v; lo = math.min(lo, v); hi = math.max(hi, v) end
  T.ok(lo >= 0 and hi < 1, "u() in [0,1)")
  T.near(sum / 100000, 0.5, 0.01, "u() mean is 0.5")

  local f = rng.new(9)
  local ok_int = true
  for _ = 1, 2000 do local v = f.int(3, 6); if v < 3 or v > 6 or v ~= math.floor(v) then ok_int = false end end
  T.ok(ok_int, "int(a,b) stays in range and integral")
  local ok_nonint = true
  for _ = 1, 200 do
    local v1 = f.int(1.7, 4.3)
    local v2 = f.int(5, 2)
    if v1 ~= math.floor(v1) or v1 < 1 or v1 > 5 or v2 ~= math.floor(v2) or v2 < 2 or v2 > 5 then ok_nonint = false end
  end
  T.ok(ok_nonint, "int(a,b) handles non-integer and inverted bounds")
  local g = rng.new(9)
  local okr = true
  for _ = 1, 1000 do local v = g.range(-2, 5); if v < -2 or v >= 5 then okr = false end end
  T.ok(okr, "range(a,b) stays in [a,b)")

  -- child(name) is order independent
  local p1 = rng.new(5)
  local c1 = p1.child("ume").u()
  for _ = 1, 37 do p1.u() end
  local c2 = p1.child("ume").u()
  T.ok(c1 == c2, "child(name) is independent of parent draws")
  T.ok(rng.new(5).child("ume").u() ~= rng.new(5).child("take").u(), "children with different names differ")

  -- fork consumes exactly one parent draw
  local q1, q2 = rng.new(11), rng.new(11)
  local child = q1.fork("x")
  for _ = 1, 50 do child.u() end
  q2.next_u32()
  T.ok(q1.u() == q2.u(), "fork consumes exactly one parent draw; child draws don't move the parent")
  T.ok(rng.new(3).fork("a").u() ~= rng.new(3).fork("b").u(), "fork tags give distinct streams")

  T.ok(rng.page_seed(1, 1) ~= rng.page_seed(1, 2), "page seeds differ per page")
  T.ok(rng.page_seed(1, 3) == rng.page_seed(1, 3), "page seed deterministic")

  local n = rng.new(4).noise(3)
  local smooth, bounded = true, true
  local prev = n(0)
  for i = 1, 400 do
    local v = n(i * 0.01)
    if math.abs(v - prev) > 0.1 then smooth = false end
    if math.abs(v) > 1.01 then bounded = false end
    prev = v
  end
  T.ok(smooth, "noise is continuous (small steps -> small changes)")
  T.ok(bounded, "normalized fbm stays within [-1,1]")
  T.ok(n(0 / 0) == 0 and n(math.huge) == 0 and n(-math.huge) == 0 and n(1e20) == 0,
    "noise is total on NaN, +-inf, and huge numbers")

  T.ok(rng.hash("abc") == rng.hash("abc") and rng.hash("abc") ~= rng.hash("abd"), "hash deterministic and discriminating")
  local okseed = pcall(function() rng.new(0 / 0).u() end)
  T.ok(okseed, "NaN seed does not crash")
end
