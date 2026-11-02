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
-- Unit tests for the pure-Lua kacho modules.
-- Run from the repository root:  texlua tests/unit/run.lua   (or: make unit)
package.path = "./tex/?.lua;./tests/unit/?.lua;" .. package.path

local T = { n = 0, fails = 0 }
function T.ok(cond, name)
  T.n = T.n + 1
  if cond then io.write("ok   ", name, "\n")
  else T.fails = T.fails + 1; io.write("FAIL ", name, "\n") end
end
function T.near(a, b, eps, name)
  T.ok(type(a) == "number" and math.abs(a - b) <= (eps or 1e-6), string.format("%s (%s vs %s)", name, tostring(a), tostring(b)))
end
function T.raises(fn, name)
  local ok = pcall(fn)
  T.ok(not ok, name)
end

local suites = { "test_rng", "test_geom", "test_palette", "test_pdf", "test_brush", "test_wash", "test_kacho", "test_m2_motifs", "test_m3_layout" }
if arg and arg[1] then suites = { arg[1] } end
for _, f in ipairs(suites) do
  io.write("# ", f, "\n")
  local ok, err = pcall(function() require(f)(T) end)
  if not ok then
    T.n = T.n + 1; T.fails = T.fails + 1
    io.write("FAIL ", f, " crashed: ", tostring(err), "\n")
  end
end
io.write(string.format("%d/%d passed\n", T.n - T.fails, T.n))
os.exit(T.fails == 0 and 0 or 1)
