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
-- Tests for kacho-palette.
return function(T)
  local pal = require("kacho-palette")
  local P = pal.get("sumi")
  local H = pal.get("hanga")
  local names = pal.names()
  T.ok(#names >= 30, "at least 30 named colours (" .. #names .. ")")
  local allok = true
  for _, n in ipairs(names) do
    local c = P.color(n)
    if not (c[1] >= 0 and c[1] <= 1 and c[2] >= 0 and c[2] <= 1 and c[3] >= 0 and c[3] <= 1) then allok = false end
    if pal.rgb2hex(c) ~= P.hex(n) then allok = false end
  end
  T.ok(allok, "every colour resolves and round-trips hex")
  T.ok(P.hex("shu") == "#C8382A", "seal red is shu #C8382A")
  T.ok(P.hex("washi") == "#F3EEDC", "washi paper")
  T.raises(function() P.color("no-such-colour") end, "unknown colour raises (no silent black)")
  T.raises(function() pal.get("delft") end, "unknown palette raises")
  local c0 = P.ink(0)
  local c1 = P.ink(1)
  T.ok(pal.lightness(c0) < pal.lightness(c1), "ink ramp: 0 darkest, 1 lightest")
  local _, a0 = P.ink(0)
  local _, a1 = P.ink(1)
  T.near(a0, 0.95, 1e-9, "ink(0) alpha equivalent")
  T.near(a1, 0.15, 1e-9, "ink(1) alpha equivalent")
  local m = pal.mix(P.color("sumi-noir"), P.color("gofun"), 0.5)
  local L = pal.lightness(m)
  T.ok(L > pal.lightness(P.color("sumi-noir")) and L < pal.lightness(P.color("gofun")), "Oklab mix lies between endpoints")
  T.ok(P.role("seal")[1] > 0.7, "role lookup (seal is red)")
  T.ok(H.paper[1] ~= P.paper[1] or H.paper[2] ~= P.paper[2], "hanga and sumi assume different papers")
  T.ok(pal.ground("none") == nil and pal.ground("washi") == "washi", "ground option mapping")
  T.raises(function() pal.ground("plaid") end, "unknown ground raises")
  local la = pal.layer_alpha(P.color("sumi-noir"), P.paper)
  local lb = pal.layer_alpha(P.color("sakura-pale"), P.paper)
  T.ok(la < lb and la <= 0.12 and lb <= 0.12, "layer alpha lower for dark pigments, <= 0.12")
end
