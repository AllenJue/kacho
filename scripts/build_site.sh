#!/usr/bin/env bash
# Copyright 2026 Allen Jue
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# scripts/build_site.sh — Build the static interactive showcase website in
# build/site/ (for local preview or GitHub Pages deployment).

set -euo pipefail

BUILD="${1:-build}"
SITE="$BUILD/site"
ASSETS="$SITE/assets"
PDF_OUT="$SITE/pdfs"
DPI="${SITE_DPI:-150}"

mkdir -p "$SITE" "$ASSETS" "$PDF_OUT"
touch "$SITE/.nojekyll"

echo "[site] copying compiled PDFs to $PDF_OUT/ ..."
for pdf in "$BUILD"/*.pdf; do
  [ -f "$pdf" ] || continue
  base="$(basename "$pdf")"
  [[ "$base" == "kacho-animated-frames.pdf" ]] && continue
  cp -f "$pdf" "$PDF_OUT/$base"
done

render_doc() {
  local doc="$1"
  local prefix="$2"
  local pdf="$BUILD/$doc.pdf"
  [ -f "$pdf" ] || return 0
  echo "[site] rendering $doc.pdf -> $ASSETS/${prefix}-*.png (${DPI} dpi) ..."
  rm -f "$ASSETS/${prefix}-"*.png
  pdftoppm -png -r "$DPI" "$pdf" "$ASSETS/${prefix}_raw"
  local idx=1
  for f in $(ls "$ASSETS/${prefix}_raw-"*.png 2>/dev/null | sort -V); do
    mv "$f" "$ASSETS/${prefix}-${idx}.png"
    idx=$((idx + 1))
  done
}

render_doc "kacho-showcase" "showcase"
render_doc "kacho-gallery"  "gallery"
render_doc "kacho-motifs"   "motifs"
render_doc "kacho-article"  "article"
render_doc "kacho-seasons"  "seasons"
render_doc "kacho-minimal"  "minimal"

if [ -f "$BUILD/kacho-animated-frames.pdf" ]; then
  echo "[site] rendering 24 animation frames -> $ASSETS/frame-*.png ..."
  rm -f "$ASSETS/frame-"*.png
  pdftoppm -png -r 150 "$BUILD/kacho-animated-frames.pdf" "$ASSETS/anim_raw"
  idx=1
  for f in $(ls "$ASSETS/anim_raw-"*.png 2>/dev/null | sort -V); do
    printf -v pad "%02d" "$idx"
    mv "$f" "$ASSETS/frame-${pad}.png"
    idx=$((idx + 1))
  done

  echo "[site] synthesizing looping animated GIF -> $ASSETS/kacho-animated.gif ..."
  rm -f "$ASSETS/gif_ppm-"*.ppm
  pdftoppm -r 96 "$BUILD/kacho-animated-frames.pdf" "$ASSETS/gif_ppm"
  python3 - "$ASSETS" <<'PYEOF'
import glob, os, struct, sys

assets = sys.argv[1]
ppm_paths = sorted(glob.glob(os.path.join(assets, "gif_ppm-*.ppm")))
out_gif = os.path.join(assets, "kacho-animated.gif")

def read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    idx = 0
    tokens = []
    while len(tokens) < 4:
        while idx < len(data) and data[idx] in b" \t\r\n":
            idx += 1
        if idx < len(data) and data[idx] == ord("#"):
            while idx < len(data) and data[idx] != ord("\n"):
                idx += 1
            continue
        start = idx
        while idx < len(data) and data[idx] not in b" \t\r\n#":
            idx += 1
        tokens.append(data[start:idx].decode("ascii"))
    idx += 1
    w, h = int(tokens[1]), int(tokens[2])
    return w, h, data[idx:idx + w * h * 3]

def lzw_encode(indices, min_code_size=8):
    clear_code = 1 << min_code_size
    eoi_code = clear_code + 1
    next_code = eoi_code + 1
    code_size = min_code_size + 1
    table = {(i,): i for i in range(clear_code)}
    out_bytes = bytearray()
    bit_buf = 0
    bit_cnt = 0
    def emit(code, csize):
        nonlocal bit_buf, bit_cnt
        bit_buf |= (code << bit_cnt)
        bit_cnt += csize
        while bit_cnt >= 8:
            out_bytes.append(bit_buf & 0xFF)
            bit_buf >>= 8
            bit_cnt -= 8
    emit(clear_code, code_size)
    if not indices:
        emit(eoi_code, code_size)
    else:
        w = (indices[0],)
        for k in indices[1:]:
            wk = w + (k,)
            if wk in table:
                w = wk
            else:
                emit(table[w], code_size)
                if next_code < 4096:
                    table[wk] = next_code
                    next_code += 1
                    if next_code > (1 << code_size) and code_size < 12:
                        code_size += 1
                else:
                    emit(clear_code, code_size)
                    table = {(i,): i for i in range(clear_code)}
                    next_code = eoi_code + 1
                    code_size = min_code_size + 1
                w = (k,)
        emit(table[w], code_size)
        emit(eoi_code, code_size)
    if bit_cnt > 0:
        out_bytes.append(bit_buf & 0xFF)
    return bytes(out_bytes)

if ppm_paths:
    palette = bytearray()
    for r in range(6):
        for g in range(7):
            for b in range(6):
                palette.extend((int(round(r * 255 / 5)), int(round(g * 255 / 6)), int(round(b * 255 / 5))))
    while len(palette) < 256 * 3:
        palette.extend((0, 0, 0))
    rmap = [int(round(i * 5 / 255)) * 42 for i in range(256)]
    gmap = [int(round(i * 6 / 255)) * 6 for i in range(256)]
    bmap = [int(round(i * 5 / 255)) for i in range(256)]
    w0, h0, _ = read_ppm(ppm_paths[0])
    with open(out_gif, "wb") as gf:
        gf.write(b"GIF89a")
        gf.write(struct.pack("<HHBBB", w0, h0, 0xF7, 0, 0))
        gf.write(palette)
        gf.write(b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00")
        for idx, p in enumerate(ppm_paths):
            w, h, rgb = read_ppm(p)
            delay_cs = 140 if idx == len(ppm_paths) - 1 else 9
            gf.write(struct.pack("<BBBBHB", 0x21, 0xF9, 4, 0x04, delay_cs, 0) + b"\x00")
            gf.write(struct.pack("<BHHHHB", 0x2C, 0, 0, w, h, 0))
            gf.write(bytes([8]))
            indices = [rmap[rgb[i]] + gmap[rgb[i + 1]] + bmap[rgb[i + 2]] for i in range(0, len(rgb), 3)]
            comp = lzw_encode(indices, 8)
            for pos in range(0, len(comp), 255):
                chunk = comp[pos:pos + 255]
                gf.write(bytes([len(chunk)]) + chunk)
            gf.write(b"\x00")
        gf.write(b"\x3B")
    print("[site] wrote kacho-animated.gif (%d frames, %d bytes)" % (len(ppm_paths), os.path.getsize(out_gif)))
PYEOF
  rm -f "$ASSETS/gif_ppm-"*.ppm
fi

cat > "$SITE/index.html" <<'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>kacho</title>
  <meta name="description" content="Procedural Japanese kachō-e watercolour margins for LuaLaTeX." />
  <style>
    :root {
      --bg: #f6f1e6;
      --card: #fbf8f1;
      --ink: #1d1a17;
      --muted: #605a52;
      --accent: #b83326;
      --border: #dcd2be;
      --code-bg: #211e1b;
      --code-fg: #f3ede0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    .container {
      max-width: 980px;
      margin: 0 auto;
      padding: 3.5rem 1.5rem 4rem;
    }

    header {
      margin-bottom: 2.75rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
    }
    h1 {
      font-size: 2.8rem;
      font-weight: 600;
      margin: 0 0 0.35rem;
      letter-spacing: 0.01em;
    }
    .tagline {
      font-size: 1.15rem;
      color: var(--muted);
      margin: 0;
    }

    h2 {
      font-size: 1.35rem;
      font-weight: 600;
      margin: 0 0 0.85rem;
    }

    /* Top row: How to use + Animated GIF */
    .intro-grid {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 2rem;
      align-items: start;
      margin-bottom: 3.25rem;
    }
    pre {
      margin: 0 0 1rem;
      padding: 1.1rem 1.25rem;
      background: var(--code-bg);
      color: var(--code-fg);
      border-radius: 6px;
      font-family: "JetBrains Mono", "Fira Code", Menlo, Consolas, monospace;
      font-size: 0.82rem;
      line-height: 1.55;
      overflow-x: auto;
    }
    .usage-note {
      font-size: 0.95rem;
      color: var(--muted);
      margin: 0;
    }
    .usage-note code {
      font-family: "JetBrains Mono", Menlo, Consolas, monospace;
      font-size: 0.84rem;
      background: #ebe3d2;
      padding: 0.1rem 0.35rem;
      border-radius: 3px;
      color: var(--ink);
    }

    .anim-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.85rem;
      text-align: center;
    }
    .anim-card img {
      display: block;
      width: 100%;
      height: auto;
      border-radius: 3px;
    }
    .anim-caption {
      font-size: 0.84rem;
      color: var(--muted);
      margin-top: 0.55rem;
    }

    /* Sample Pages Showcase (hover/click to highlight in-place, locked dimensions so nothing ever shifts or jitters) */
    .showcase-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 290px;
      gap: 1.75rem;
      align-items: start;
    }
    .preview-pane {
      min-width: 0;
      width: 100%;
      background: #e9e0ce;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      overflow: hidden;
    }
    .preview-frame {
      position: relative;
      width: 100%;
      max-width: 480px;
      aspect-ratio: 1241 / 1754;
      background: #fff;
      border-radius: 2px;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.15);
      overflow: hidden;
    }
    .preview-frame img.preview-layer {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #fff;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.12s ease;
      will-change: opacity;
    }
    .preview-frame img.preview-layer.active {
      opacity: 1;
    }
    .preview-meta {
      width: 100%;
      min-width: 0;
      margin-top: 1rem;
      text-align: center;
    }
    .preview-title {
      font-size: 0.98rem;
      font-weight: 600;
      line-height: 1.4;
      height: 1.4em;
      margin-bottom: 0.35rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .preview-code {
      display: block;
      width: 100%;
      font-family: "JetBrains Mono", Menlo, Consolas, monospace;
      font-size: 0.75rem;
      line-height: 1.5;
      background: var(--code-bg);
      color: var(--code-fg);
      padding: 0.35rem 0.65rem;
      border-radius: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .sample-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.7rem;
    }
    .sample-thumb {
      background: var(--card);
      border: 2px solid var(--border);
      border-radius: 4px;
      padding: 0.3rem;
      cursor: pointer;
      transition: border-color 0.12s ease, opacity 0.12s ease;
      opacity: 0.72;
    }
    .sample-thumb:hover,
    .sample-thumb.active {
      border-color: var(--accent);
      opacity: 1;
    }
    .sample-thumb img {
      display: block;
      width: 100%;
      aspect-ratio: 210 / 297;
      object-fit: cover;
      border-radius: 2px;
    }
    .sample-thumb span {
      display: block;
      font-size: 0.74rem;
      color: var(--muted);
      text-align: center;
      margin-top: 0.25rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    footer {
      margin-top: 4rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      font-size: 0.9rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
    }

    @media (max-width: 780px) {
      .intro-grid { grid-template-columns: 1fr; }
      .showcase-layout { grid-template-columns: 1fr; }
      .sample-grid { grid-template-columns: repeat(4, 1fr); }
    }
  </style>
</head>
<body>

<div class="container">
  <header>
    <h1>kacho</h1>
    <p class="tagline">Procedural Japanese <em>kachō-e</em> watercolour and ink-wash page margins for LuaLaTeX.</p>
  </header>

  <div class="intro-grid">
    <div>
      <h2>How to Include &amp; Use</h2>
<pre>\documentclass[11pt,a4paper,twoside]{article}
\usepackage[
  seed=7,
  palette=hanga,   % sumi (monochrome ink) or hanga (polychrome)
  theme=haru,      % haru | natsu | aki | fuyu | shochikubai
  ground=washi     % none | washi | kinu | torinoko | koson
]{kacho}

\begin{document}
\section*{Notes from the Plum Orchard}
Every page margin is painted automatically at shipout time...

% Override any single page:
\kachoThisPage{theme=aki, motif={maple,mejiro}, layout=overhang}

% Inline botanical vignette inside the text column:
\kachospray[width=0.75\linewidth, height=42mm, motif=ume]
\end{document}</pre>
      <p class="usage-note">
        Compile with <code>lualatex your-doc.tex</code>. Use <code>\kachoOff</code> and <code>\kachoOn</code> to pause or resume margin painting on any page.
      </p>
    </div>

    <div class="anim-card">
      <img src="assets/kacho-animated.gif" alt="24-frame procedural kacho growth animation" />
      <div class="anim-caption">Continuous procedural growth (<code>t = 0 &rarr; 1</code>) rendered directly by LuaLaTeX.</div>
    </div>
  </div>

  <section>
    <h2>Sample Pages</h2>
    <div class="showcase-layout">
      <div class="preview-pane">
        <div class="preview-frame" id="previewFrame"></div>
        <div class="preview-meta">
          <div class="preview-title" id="mainTitle">Spring Sakura &amp; Interleaved Bamboo (Overhang)</div>
          <code class="preview-code" id="mainCode">\kachoThisPage{theme=haru, palette=hanga, layout=overhang, motif={sakura,uguisu}, seed=11}</code>
        </div>
      </div>

      <div class="sample-grid" id="sampleGrid"></div>
    </div>
  </section>

  <footer>
    <div><a href="https://github.com/AllenJue/kacho">GitHub — AllenJue/kacho</a></div>
    <div>Apache-2.0 License &middot; Copyright 2026 Allen Jue</div>
  </footer>
</div>

<script>
const SAMPLES = [
  {
    src: "assets/showcase-2.png",
    label: "Sakura & Bamboo",
    title: "Spring Sakura & Interleaved Bamboo (Overhang)",
    code: "\\kachoThisPage{theme=haru, palette=hanga, layout=overhang, motif={sakura,uguisu}, seed=11}"
  },
  {
    src: "assets/showcase-1.png",
    label: "Kakejiku Scroll",
    title: "Kakejiku Hanging-Scroll Title Page",
    code: "\\kachoTitlePage[layout=kakejiku, palette=hanga, theme=haru, seed=7]{...}"
  },
  {
    src: "assets/showcase-3.png",
    label: "Wisteria & Ume",
    title: "Cascading Wisteria, Plum & Bamboo (Corner Spray)",
    code: "\\kachoThisPage{theme=haru, palette=hanga, layout=corner-spray, motif={wisteria,ume,bamboo}, seed=15}"
  },
  {
    src: "assets/showcase-4.png",
    label: "Autumn Maple",
    title: "Autumn Momiji Maple, Bamboo & Mejiro White-Eyes",
    code: "\\kachoThisPage{theme=aki, palette=hanga, layout=overhang, motif={maple,mejiro}, seed=21}"
  },
  {
    src: "assets/showcase-5.png",
    label: "Sumi Winter Pine",
    title: "Three Friends of Winter (Shōchikubai) in Sumi Ink",
    code: "\\kachoThisPage{theme=shochikubai, palette=sumi, layout=rising, motif={pine,ume,sparrow}, seed=29}"
  },
  {
    src: "assets/showcase-6.png",
    label: "Border Frame",
    title: "Four-Sided Interleaved Border Frame",
    code: "\\kachoThisPage{theme=haru, palette=hanga, layout=border-frame, seed=33}"
  },
  {
    src: "assets/gallery-10.png",
    label: "Mt. Fuji Vista",
    title: "Footer Ground with Scholar Rock & Distant Mount Fuji",
    code: "\\kachoThisPage{theme=natsu, palette=hanga, layout=footer-ground, motif=fuji, seed=19}"
  },
  {
    src: "assets/gallery-9.png",
    label: "Inline Spray",
    title: "Osmanthus Margin & Inline Chrysanthemum Vignette",
    code: "\\kachospray[width=0.72\\linewidth, height=40mm, motif=chrysanthemum, seed=25]"
  },
  {
    src: "assets/seasons-1.png",
    label: "Shikishi Opener",
    title: "Gold-Rimmed Shikishi Chapter Opener",
    code: "\\kachoThisPage{theme=haru, layout=shikishi, palette=hanga, seed=101}"
  },
  {
    src: "assets/motifs-1.png",
    label: "Ume Study",
    title: "Motif Study — Ume (Winter Plum) in Sumi & Hanga",
    code: "\\kachomotifsheet (Plate 1: motif=ume)"
  },
  {
    src: "assets/motifs-6.png",
    label: "Wisteria Study",
    title: "Motif Study — Fuji (Cascading Wisteria)",
    code: "\\kachomotifsheet (Plate 6: motif=wisteria)"
  },
  {
    src: "assets/motifs-10.png",
    label: "Kachō-e Birds",
    title: "Motif Study — Five Perched & Flying Kachō-e Bird Species",
    code: "\\kachomotifsheet (Plate 10: robin, uguisu, sparrow, mejiro, swallow)"
  }
];

const gridEl = document.getElementById("sampleGrid");
const previewFrameEl = document.getElementById("previewFrame");
const mainTitleEl = document.getElementById("mainTitle");
const mainCodeEl = document.getElementById("mainCode");
let activeIdx = 0;

function selectSample(idx) {
  if (idx === activeIdx) return;
  activeIdx = idx;
  const s = SAMPLES[idx];
  mainTitleEl.textContent = s.title;
  mainCodeEl.textContent = s.code;
  Array.from(previewFrameEl.children).forEach((el, i) => {
    el.classList.toggle("active", i === idx);
  });
  Array.from(gridEl.children).forEach((el, i) => {
    el.classList.toggle("active", i === idx);
  });
}

SAMPLES.forEach((s, idx) => {
  const layer = document.createElement("img");
  layer.className = "preview-layer" + (idx === 0 ? " active" : "");
  layer.src = s.src;
  layer.alt = s.title;
  layer.decoding = "async";
  previewFrameEl.appendChild(layer);

  const item = document.createElement("div");
  item.className = "sample-thumb" + (idx === 0 ? " active" : "");
  item.innerHTML = `<img src="${s.src}" alt="${s.label}" /><span>${s.label}</span>`;
  item.addEventListener("mouseenter", () => selectSample(idx));
  item.addEventListener("click", () => selectSample(idx));
  gridEl.appendChild(item);
});
</script>
</body>
</html>
HTMLEOF

echo "[site] built $SITE/index.html ($(ls -1 "$ASSETS" | wc -l) asset files, $(ls -1 "$PDF_OUT" | wc -l) PDFs)"
