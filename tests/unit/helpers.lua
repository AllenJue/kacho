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
-- Shared test helpers: a fake PDF backend and a drawing context.
local H = {}

--- Fake backend recording every resource registration.
function H.backend()
  local b = { extgs_list = {}, patterns = {}, objs = {}, streams = {} }
  function b.extgs(name, dict) b.extgs_list[#b.extgs_list + 1] = { name, dict } end
  function b.pattern(name, num) b.patterns[#b.patterns + 1] = { name, num } end
  function b.obj(dict) b.objs[#b.objs + 1] = dict; return 100 + #b.objs end
  function b.stream(dict, data) b.streams[#b.streams + 1] = { dict, data }; return 500 + #b.streams end
  return b
end

function H.ctx(seed, palette)
  local pdf = require("kacho-pdf")
  local be = H.backend()
  local W = pdf.new(pdf.registry(be))
  return {
    pdf = W, rng = require("kacho-rng").new(seed or 1), palette = require("kacho-palette").get(palette or "sumi"),
    brush = require("kacho-brush"), wash = require("kacho-wash"), backend = be,
  }
end

--- All numeric coordinates appearing in a content string.
function H.numbers(s)
  local t = {}
  for tok in s:gmatch("%S+") do
    local v = tonumber(tok)
    if v then t[#t + 1] = v end
  end
  return t
end

--- Path coordinates (x y pairs before m/l/c/re operators) in content. Paint
--- inside a clip (after "W n" until the matching Q) is skipped: the clip path
--- itself bounds what can be painted there.
function H.path_points(s)
  local pts = {}
  local stack = {}
  local depth, clip_at = 0, nil
  for tok in s:gmatch("%S+") do
    local v = tonumber(tok)
    if v then stack[#stack + 1] = v
    else
      if tok == "q" then depth = depth + 1
      elseif tok == "Q" then
        depth = depth - 1
        if clip_at and depth < clip_at then clip_at = nil end
      elseif tok == "W" or tok == "W*" then
        if not clip_at then clip_at = depth end
      elseif not clip_at then
        if tok == "m" or tok == "l" or tok == "c" then
          for i = 1, #stack - 1, 2 do pts[#pts + 1] = { stack[i], stack[i + 1] } end
        elseif tok == "re" and #stack >= 4 then
          local x, y, w, h = stack[#stack - 3], stack[#stack - 2], stack[#stack - 1], stack[#stack]
          pts[#pts + 1] = { x, y }; pts[#pts + 1] = { x + w, y + h }
        end
      end
      stack = {}
    end
  end
  return pts
end

return H
