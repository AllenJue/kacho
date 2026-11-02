# kacho

Procedural Japanese *kachō-e* (flower-and-bird), *kanga-e*, and *ukiyo-e* watercolour and ink-wash page margins for LuaLaTeX.

**[Showcase Website (`allenjue.github.io/kacho`)](https://allenjue.github.io/kacho/)**

---

## How to Include & Use

Add `\usepackage[...]{kacho}` to any LuaLaTeX document:

```latex
\documentclass[11pt,a4paper,twoside]{article}
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
\end{document}
```

Compile with `lualatex`:

```bash
TEXINPUTS=$PWD/tex//: LUAINPUTS=$PWD/tex//: lualatex mydoc.tex
```

---

## Sample Pages & Procedural Growth

| Kakejiku Title Page | Spring *Sakura* & Bamboo | Cascading Wisteria & *Ume* |
|:---:|:---:|:---:|
| <img src="https://allenjue.github.io/kacho/assets/showcase-1.png" width="250" alt="Kakejiku Title Page"/> | <img src="https://allenjue.github.io/kacho/assets/showcase-2.png" width="250" alt="Spring Sakura and Bamboo"/> | <img src="https://allenjue.github.io/kacho/assets/showcase-3.png" width="250" alt="Wisteria, Ume, and Bamboo"/> |
| **Autumn *Momiji* & Bamboo** | **Winter *Shōchikubai* (*Sumi*)** | **24-Frame Procedural Growth** |
| <img src="https://allenjue.github.io/kacho/assets/showcase-4.png" width="250" alt="Autumn Maple and Bamboo"/> | <img src="https://allenjue.github.io/kacho/assets/showcase-5.png" width="250" alt="Winter Pine, Plum, and Bamboo"/> | <img src="https://allenjue.github.io/kacho/assets/kacho-animated.gif" width="235" alt="24-Frame Animated Growth"/> |

---

## Build Commands

```bash
make                # compile all examples/*.tex into build/*.pdf
make view           # compile and open build/kacho-showcase.pdf
make animated       # compile examples/animated/kacho-animated.tex -> build/kacho-animated.pdf
make site           # build the showcase website + GIF in build/site/index.html
make test           # run Lua unit tests (texlua) and the E2E verification suite
make clean          # remove build/
```

---

## Package Options & Placement Commands

Pass options at `\usepackage[...]{kacho}` time or change them mid-document with `\kachosetup{...}` and `\kachoThisPage{...}`.

| Option | Values (default) | Description |
|---|---|---|
| `seed` | integer (`1`) | Master document seed; page `p` derives an independent stream from `(seed, p)` |
| `palette` | `sumi`, `hanga`, `kinpaku`, `usuzumi` (`sumi`) | Pigment palette: `sumi` (ink wash), `hanga` (polychrome woodblock), `kinpaku` (gold screen), `usuzumi` (pale ghost ink) |
| `theme` | `haru`, `natsu`, `aki`, `fuyu`, `shochikubai` (`haru`) | Seasonal motif pool (`haru` spring, `natsu` summer, `aki` autumn, `fuyu` winter, `shochikubai` pine–bamboo–plum trio) |
| `layout` | `auto`, `overhang`, `rising`, `corner-spray`, `margin-column`, `header-garland`, `footer-ground`, `scattered-petals`, `border-frame`, `kakejiku`, `shikishi`, `demo`, `none` (`auto`) | Page composition archetype; `auto` draws from a shuffled deck so consecutive pages never repeat |
| `density` | `0.0` .. `1.0` (`0.5`) | Decoration richness and blossom/leaf cluster density |
| `ground` | `none`, `washi`, `kinu`, `torinoko`, `koson` (`none`) | Full-page warm paper/silk ground tint painted underneath all content |
| `birds` / `seal` | `true` / `false` (`true`) | Enable or disable perched songbirds and vermilion *hanko* seals |
| `motif` | `<name>` or `{m1,m2,...}` (empty) | Force specific motif(s): `ume`, `sakura`, `bamboo`, `orchid`, `maple`, `wisteria`, `iris`, `pine`, `camellia`, `osmanthus`, `narcissus`, `chrysanthemum`, `fuji`, `rock`, `bird`, `seal` |
| `regions` | `auto`, `outer`, `inner`, `left`, `right`, `top`, `bottom`, `corners`, `frame`, `none`, or `{top,outer,...}` (`auto`) | Restrict which margin bands page layouts may occupy |
| `spawn` | `{<anchor>@<angle>; ...}` (empty) | Shorthand per-page spawn specification (e.g. `spawn={br@125; tl@-45}`) |
| `safe` / `buffer` | TeX dimensions (`5mm` / `4mm`) | Minimum paper-edge inset (`safe`) and protective clearance around typeset text (`buffer`) |
| `debug` / `off` | boolean (`false`) | Emit `<jobname>.kacho.log` bounding boxes (`debug`) or disable painting (`off`) |

| Command | Description |
|---|---|
| `\kachosetup{<keys>}` | Set package options in the preamble or persistently from the current page onward |
| `\kachoThisPage{<keys>}` | Override `layout`, `theme`, `palette`, `density`, `ground`, `birds`, `seal`, `motif`, `regions`, `spawn`, `seed`, or `off` for the current page only |
| `\kachoOff` / `\kachoOn` | Suspend or resume decoration from the current page onward |
| `\kachoTitlePage[<keys>]{title=..., subtitle=..., author=..., date=...}` | Typeset a framed title block surrounded by a *kakejiku* hanging-scroll composition |
| `\kachoSpawn{<keys>}` | Grow a motif on the current page from an explicit anchor (`at=tl\|tc\|tr\|ml\|c\|mr\|bl\|bc\|br`, `from=page\|text\|safe`, `dx=`, `dy=`, `angle=`, `size=`, `motif=`, `seed=`) |
| `\kachospray[<keys>]` | Reserve an inline box (`width=`, `height=`, `motif=`, `palette=`, `seed=`, `from=`) and paint a self-contained spray clipped inside that box |

---

## Algorithms & References

Every Lua module in `tex/` documents its mathematical models and attributions in a structured `-- ALGORITHMS & REFERENCES:` header block. Below is the complete architecture and provenance summary across all modules, explicitly distinguishing code **adapted from** third-party open-source software (under the MIT License or public domain) from algorithms **inspired by** academic papers (implemented from scratch).

### 1. Core Engine, Geometry, PRNG, Colour, and PDF Primitives

- **`tex/kacho.sty` and `tex/kacho.lua`** — *Shipout inspection, key-value plumbing, safety clipping, and built-in pipe-model fallback*:
  - **Adapted from** Kevin Raymond's `florilegium` (`florilegium.sty`, `florilegium-layout.lua`, MIT License): LaTeX `ltkeys` option declarations, `\AddToHook{shipout/background}` integration, and user-defined whatsit markers (`MARK_ID = 0x4B4143`).
  - **Inspired by** Kichiro Shinozaki, Kyoji Yoda, Kazuo Hozumi, and Tatuo Kira, *"A Quantitative Analysis of Plant Form — The Pipe Model Theory"*, Japanese Journal of Ecology 14(3):97–105, 1964: recursive area-preserving limb cross-sections ($w_1^2 + w_2^2 \le w_0^2$) in `M.demo_layout`.
  - **Inspired by** Michael T. Wong, Douglas E. Zongker, and David H. Salesin, *"Computer-Generated Floral Ornament"*, SIGGRAPH 1998: recursive LuaTeX node-list traversal (`walker`) measuring glyph, rule, leader, and graphics bounding boxes at shipout to carve free margin zones.
- **`tex/kacho-geom.lua`** — *2-D axis-aligned geometry, rect subtraction, and transactional `ctx:try` fitting*:
  - **Inspired by** Michael T. Wong, Douglas E. Zongker, and David H. Salesin, *"Computer-Generated Floral Ornament"*, SIGGRAPH 1998: decomposing page margins (`M.page`, `M.regions`, `M.subtract_all`) around typeset ink obstacles and testing candidate ornament placements against forbidden rectangles (`M.bbox_allowed`) before committing PDF paths.
- **`tex/kacho-rng.lua`** — *Deterministic PRNG streams and 1-D coherent noise*:
  - **Adapted from** **Tommy Ettinger**'s public-domain `mulberry32` 32-bit state-mixing generator (<https://gist.github.com/tommyettinger/46a874533244883189143505d203312c>) and **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua`, MIT License): `M.stream`, `M.hash32` FNV-1a string hashing, hierarchical `.child(tag)` stream forking, and smoothstep-interpolated 1-D value noise (`rng.noise1`).
- **`tex/kacho-palette.lua`** — *Perceptual Oklab colour mixing and historical Japanese pigments*:
  - **Adapted from** **Björn Ottosson**'s public-domain Oklab perceptual colour space (*"A perceptual color space for image processing"*, 2020, <https://bottosson.github.io/posts/oklab/>) and **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua`, MIT License): exact IEC 61966-2-1 sRGB transfer functions (`to_lin`, `from_lin`), LMS cube-root matrix transforms (`rgb_to_oklab`, `oklab_to_rgb`), and perceptual pigment interpolation (`M.mix`, `M.tone`).
- **`tex/kacho-pdf.lua`** — *Low-level PDF vector stream, ExtGState, and shading builder*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua`, MIT License): layered display list (`W:layer`, `W:pieces`), cubic Bézier fitting (`W:curve`, `W:smooth_closed` Catmull-Rom-to-Bézier conversion), quantized `/ExtGState` fill/stroke opacity (`ca`/`CA`) and blend mode (`/BM /Multiply`) registration (`M.registry`), and isolated transparency groups. Also implements native PDF Type 2 axial/function shadings (`/ShadingType 2`) for banding-free gradients.

### 2. Brushwork and Watercolour Wash Engine

- **`tex/kacho-brush.lua`** — *Calligraphic sumi-e strokes, ribbons, and mokkotsu shapes*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua` and `florilegium-flora.lua`, MIT License): centripetal Catmull-Rom chain discretization (`M.chain`), arc-length parameterized spine queries (`M.spine`, `M.at`, `M.slice`), variable-width normal-offset stroke envelopes (`M.stroke`, `M.profiles`), folded botanical leaf ribbons (`M.ribbon`), and split-bristle *kasure* dry-brush filaments.
- **`tex/kacho-wash.lua`** — *Wet-on-wet watercolour washes, nijimi, tarashikomi, and bokashi*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua`, MIT License): multi-layer low-opacity polygon flooding, `/Multiply` interior mottle, dark pooled perimeter rim, and lifted highlight streaks (`M.flood`).
  - **Inspired by** **Cassidy J. Curtis, Sean E. Anderson, Joshua E. Seims, Kurt W. Fleischer, and David H. Salesin**, *"Computer-Generated Watercolor"*, Proceedings of SIGGRAPH 1997, pp. 421–430: outward pigment migration (`M.nijimi`), wet-in-wet secondary pigment blooming (`M.tarashikomi`), mineral pigment settling (`M.granulate`), and native PDF Type 2 axial *bokashi* horizon gradations (`M.bokashi`).
- **`tex/kacho-ink.lua`** — *Botanical watercolour glazes, venation, petals, leaves, and bark*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-ink.lua`, MIT License): 4-stage botanical watercolour glaze pipeline (`M.wash_fill`: base washes, `/Multiply` back-run rim, dry-brush streaks, pigment stipple), curved midrib + lateral venation (`M.vein_fan`), notched/ruffled petal geometry (`M.petal`), serrated leaf outlines (`M.leaf_shape`), and multi-pass shaded wood/bark strokes (`M.branch_stroke`).
  - **Inspired by** **Cassidy J. Curtis et al.** (SIGGRAPH 1997) and **Björn Ottosson** (Oklab, 2020) for perceptual wet-glaze tone shifts (`M.shift`, `M.mix_ok`).

### 3. Procedural Botanical Growth, Motifs, and Page Layouts

- **`tex/kacho-growth.lua`** — *2-D space-colonization branching, pipe-model widths, and phototropism*:
  - **Inspired by** **Adam Runions, Brendan Lane, and Przemyslaw Prusinkiewicz**, *"Modeling Trees with a Space Colonization Algorithm"*, Eurographics Workshop on Natural Phenomena (EGWNP), pp. 63–70, 2007: iterative 2-D attractor-cloud colonization within elliptic/fan/annular/ribbon envelopes (`M.colonize`, `M.envelope`, `M.tree`, `M.garland`, `M.clip_chains`).
  - **Inspired by** **Kichiro Shinozaki et al.** (Pipe Model Theory, 1964) and **Leonardo da Vinci**: bottom-up cross-sectional area accumulation ($w = w_{\text{tip}} (\sum_c w_c^p)^{1/p}$, $p \approx 2.05$) and taper profiles (`M.chains`).
  - **Inspired by** **Przemyslaw Prusinkiewicz and Aristid Lindenmayer**, *The Algorithmic Beauty of Plants*, Springer, 1990: tropism bias and organ attachment site classification (`tips`, `forks`, `internodes`).
- **`tex/kacho-flora.lua`** — *Twelve Japanese botanical motif generators*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-flora.lua`, MIT License): multi-layer cupped corolla rendering (`full_blossom`, `side_cup`, `plum_bud`), filament + gold anther stamen rings (`stamen_crown`), compound serrated foliage (`compound_leaf`, `M.maple`), and drooping wisteria racemes (`M.wisteria`).
  - **Inspired by** **Adam Runions et al.** (2007), **Kichiro Shinozaki et al.** (1964), and **Przemyslaw Prusinkiewicz & Aristid Lindenmayer** (1990): woody spray habits (`M.ume`, `M.sakura`, `M.maple`, `M.wisteria`, `M.pine`, `M.camellia`, `M.osmanthus`), monopodial jointed culms (`M.bamboo`), and basal fan/clump herbs (`M.orchid`, `M.iris`, `M.narcissus`, `M.chrysanthemum`).
- **`tex/kacho-fauna.lua`** — *Perched and flying kachō-e birds*:
  - **Inspired by** **Cassidy J. Curtis et al.** (SIGGRAPH 1997) and traditional *kachō-ga* manuals (Kōno Bairei, Ohara Koson, Imao Keinen): constructivist anatomical layering (undertail coverts, folded wing primaries, breast wash, crown, beak, eye-ring, and clutching tarsi anchored to branch spine coordinates) in `M.uguisu`, `M.robin`, `M.sparrow`, `M.mejiro`, `M.swallow`, and `M.perch`.
- **`tex/kacho-scenery.lua`** — *Suibokuga and ukiyo-e landscape elements*:
  - **Inspired by** **Cassidy J. Curtis et al.** (SIGGRAPH 1997) and Hiroshige / Hokusai *meisho-e* landscapes: faceted *fuppi-cun* (axe-cut) rock geometry (`M.rock`), layered Mount Fuji vista with receding flanking ridges, asymmetric 3-lobed crater rim (*Kengamine* / *Shaka-dake*), soft snow mantle with radial *sawa* wisps, and basal *kasumi* mist fade (`M.fuji`), multi-tier ukiyo-e / kanga-e grass banks (`M.grass_bank`, `M.grass_tuft`), woodblock *seigaiha* waves (`M.waves`), coastal cliffs (`M.cliffs`), vertical *tanzaku* title cartouches (`M.tanzaku`), and horizontal *kasumi* mist bands (`M.kasumi`).
- **`tex/kacho-seal.lua`** — *Carved vermilion hanko seals (`shubun` and `hakubun`)*:
  - **Inspired by** traditional East Asian *tenkoku* seal carving: jittered weathered border polygons, a procedural dictionary of 16 authentic Small Seal Script (*Tenshotai* / *Kaku-tensho* / 角篆) kanji characters (`花`, `鳥`, `風`, `月`, `春`, `夏`, `秋`, `冬`, `山`, `水`, `松`, `竹`, `梅`, `雅`, `芳`, `印`) arranged into classical 1-, 2-, and 4-kanji seal compounds (`M.hanko`, `M.glyph`), and cinnabar (`shu`) paste impression texture with *kasure* voids.
- **`tex/kacho-motifsheet.lua`** — *Studio specimen catalog layout (`examples/kacho-motifs.tex`)*:
  - **Inspired by** **Michael T. Wong, Douglas E. Zongker, and David H. Salesin** (SIGGRAPH 1998): isolated studio plates exercising all flora, fauna, scenery, and seal primitives within measured text-free boxes.
- **`tex/kacho-layout.lua`** — *Page layout archetypes, seasonal themes, variety deck, and user-controlled placement*:
  - **Adapted from** **Kevin Raymond**'s `florilegium` (`florilegium-layout.lua`, MIT License): transactional `Plan` sub-contexts (`Plan:attempt`, `Plan:fit`), region filtering (`regions=`), and 4-sided `border-frame` vine/branch framing.
  - **Inspired by** **Michael T. Wong, Douglas E. Zongker, and David H. Salesin** (*"Computer-Generated Floral Ornament"*, SIGGRAPH 1998) and **Adam Runions et al.** (2007): adaptive layout selection (`L.auto`, `L.deck_pick`), ten page composition archetypes (`overhang`, `rising`, `corner-spray`, `margin-column`, `header-garland`, `footer-ground`, `scattered-petals`, `border-frame`, `kakejiku`, `shikishi`), interleaved 3-tier bamboo and repeated woody boughs (`L.interleaved_boughs_and_bamboo`), seasonal theme pools (`haru`, `natsu`, `aki`, `fuyu`, `shochikubai`), inline `\kachospray` boxes, and anchor-based `\kachoSpawn` growth (`L.user`).
- **`tex/kacho-anim.lua` and `examples/animated/kacho-animated.tex`** — *Animated Growth Clock*:
  - **Inspired by** **tikz-flora** (<https://github.com/wn-mitch/tikz-flora>, MIT License): progressive botanical growth clock concept ("watch it grow"), implemented from scratch in Lua via frame-by-frame pruning of space-colonization trees and organ maturation schedules.

---

## License

Copyright 2026 Allen Jue. Released under the **Apache License 2.0** — see [LICENSE](LICENSE).  
Portions adapted from `florilegium` (Copyright (c) 2026 Kevin Raymond, MIT License) and public-domain algorithms (`mulberry32`, `Oklab`) are documented in [NOTICE.md](NOTICE.md).
