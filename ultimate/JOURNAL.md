# Nevryon Ultimate — Development Journal

Newest entries at the top. The earlier reverse-engineering work is
tracked in `../JOURNAL.md`; this journal picks up where that one
left off, focused on the remake.

---

## 2026-05-22 — Session 2: tile catalogs for levels 2-4 + CLI refactor

Extended the tile pipeline to all four levels. Rich asked the
encoder to take its source path, destination path and palette as
input parameters so it can be plugged into a build script later.
The all-4-levels mode that briefly existed in `encode_tiles.py`
is gone; the script now encodes ONE level per invocation:

```
encode_tiles.py --src DIR --out FILE --palette C0,C1,C2,C3
                [--label TEXT] [--expected-bytes N]
```

Palette colours are either BBC physical names (`black` / `red` /
`green` / `yellow` / `blue` / `magenta` / `cyan` / `white`) or
6-digit hex (with or without `#`). The four invocations live in
CLAUDE.md ("Regenerating the data").

### Assets and outputs

* `assets/level2/tile_00..17.png` — copied from `../levels/2/`.
  Scenario-2 palette: black / blue / cyan / white.
* `assets/level3/tile_00..17.png` — scenario-3 palette: black /
  red / green / white.
* `assets/level4/tile_00..17.png` — scenario-4 palette: black /
  red / magenta / white.
* `data/level<N>/tiles.6502` for N in 1..4 — generated.

### Result

| Level | Encoded | Survey | Δ vs survey | Coalesced cols |
|------:|--------:|-------:|------------:|---------------:|
|     1 |   1 547 |  1 763 | −216 (−12 %)|             11 |
|     2 |   1 231 |  1 222 | **+9 (+1 %)** |              0 |
|     3 |   1 267 |  1 293 |  −26 (−2 %) |              3 |
|     4 |   1 835 |  1 856 |  −21 (−1 %) |              3 |
| Total |   5 880 |  6 234 | −354 (−6 %) |             17 |

L2 is the only level where the new encoder is bigger than the spec
survey — its tile artwork happens to have no duplicate columns AND
has nine runs whose length is `10q + 1` (the all-RLE-tail rule
pays +1 byte per such run). The other three levels recover the
deficit and then some via coalescing.

### Verification

* Every sprite round-trips through `tools/sprite_rle.decode_sprite`
  (the local spec decoder) before the output file is written.
* All 72 PNG-derived 128-byte sprites (4 levels × 18 tiles) are
  byte-identical to the corresponding `../extracted/N.LEVD1` tile
  catalogs at offset `&500..&DFF`. So the PNG-to-2bpp inversion is
  exact for every level's palette, and there's no drift between
  the editable assets in `assets/` and the original on-disk data.

### Next

Same as session 1 (CRTC vertical-rupture, hardware-scroll setup,
metadata tables + runtime decoder). The data-side now has all four
tile catalogs ready for whichever scenario we light up first.

---

## 2026-05-22 — Session 1: project kickoff, level-1 tile RLE pipeline

Rich kicked off the remake. We're now in `ultimate/` as a
subdirectory of the original RE repo; from this session forward,
all new code / tools / assets land here.

### Design recap (captured in CLAUDE.md)

The remake targets a hardware-scrolled **MODE 2** display with a
**16 K screen buffer**, of which **20 char rows = 12.5 K is
visible** as the playfield (same vertical envelope as the original).
The remaining 3.5 K of the buffer is used as a per-tick **offscreen
scratch** for the sprite unpacker. Under the playfield a **static
2-line HUD** is presented via a CRTC "vertical rupture" split.

Because MODE 2 chars are half the width of MODE 5 chars, we **double
the game-tick rate** — every 3 vsyncs (~16.7 Hz) instead of the
original's every-6-vsyncs 8.3 Hz. Net horizontal motion across the
screen ends up the same; everything is smoother. The per-tick
pipeline:

* Vsync 1 — unpack scheme-C-compressed 2bpp source bytes via the
  16-entry ZP LUT into 4bpp MODE 2 output bytes, in the offscreen
  scratch.
* Vsync 2 — plot animating hazards (the 4×32 sprites: gun-towers,
  tanks, structures).
* Vsync 3 — erase + re-plot moving sprites (player, enemies,
  missiles, pickups, starfield) and program the CRTC for the next
  scroll step.

Sprites stay 2bpp on-disk to halve storage; the 2bpp→4bpp expansion
through the per-sprite-palette LUT is the same hot path designed in
`../docs/sprite_rle_notes.md`.

### What landed this session

1. **`CLAUDE.md`** — workflow + display-model + RLE-scheme reference
   for the remake. Pointers to the parent's `docs/` for the
   authoritative reverse-engineering reference.
2. **`assets/level1/tile_00..17.png`** — 18 tile PNGs copied from
   `../levels/1/`. These are now the **source of truth** for level-1
   tile artwork. They're 16×32 px native, scenario-1 palette
   (black / red / yellow / white). Editable in any pixel editor;
   the encoder requires every pixel to stay on the 4-colour
   palette and errors out with coordinates if anything strays.
3. **`tools/encode_tiles.py`** — reads each `assets/level1/tile_NN.png`,
   inverts the BBC MODE 5 byte layout (pixel n in 0..3 uses bits
   `(7-n)` and `(3-n)` for its 2 bpp), packs to 4×32 column-major
   bytes (128 B per sprite), then RLE-encodes via scheme C from
   the parent's `tools/sprite_rle.py` (the canonical encoder from
   the survey work). Every sprite is round-tripped through the
   decoder before emit, so any encoder bug surfaces here rather
   than at runtime.
4. **`data/level1/tiles.6502`** — generated BeebAsm source, **1 763
   bytes of encoded data for 2 304 raw** (76 %). Matches the survey
   figure for L1 tiles in `../docs/sprite_rle_notes.md` to the
   byte; the encoder asserts this and refuses to write the output
   otherwise (catches encoder regressions and unintended repaints
   that change the run distribution). Layout per tile:
   ```
   \\ tile_NN: <enc-bytes> bytes (<pct>% of raw 128 B)
   tile_NN_rle_flag = &XX     \\ FLAG_BYTE = FLAG << 3
   .tile_NN_col_0
       EQUB ...
   .tile_NN_col_1
       EQUB ...
   .tile_NN_col_2
       EQUB ...
   .tile_NN_col_3
       EQUB ...
   ```
   Rich will build the per-sprite metadata tables (flag table,
   per-column offset tables, palette tables) on top of these
   labels + equates by hand.

### Cross-check

Encoded the same PNG-derived bytes against `../extracted/1.LEVD1`
at `&500..&DFF`: **18 / 18 tiles match byte-for-byte**. So the
PNG → 2bpp packer is the exact inverse of the parent repo's
`render_sprite.render_column_major`, and there's no drift between
the artwork in `assets/` and the original on-disk LEVD1 data.

### Encoder optimisations added later in the session

After the first round of `tiles.6502`, Rich pointed out two things:

1. **tile_06's four columns are identical** (all-zero blank tile),
   so they should share their stream — emit the column once and
   stack the four `.tile_06_col_M` labels above it. This generalises:
   any sprite where two or more column streams are byte-identical
   should coalesce.
2. **All-RLE long-run splits.** For runs of more than 10 bytes the
   spec encoder caps at 10 and lets the tail spill as literals
   (e.g. 32 zeros → three 10-runs + two literals). The remake
   decoder pays ~56 cyc per literal vs ~26 cyc per run-body byte,
   so we should always close the tail with another RLE block. For
   `run_len = 10*q + r` the split rule is:
   * `r == 0`           → q runs of 10
   * `r in 3..9`        → q runs of 10 + one run of r
   * `r in {1, 2}`      → (q-1) runs of 10 + one run of (r+7) + one run of 3

   Rich's worked example: 32 zeros now encode as
   `&07,&00, &07,&00, &06,&00, &00,&00` (10 + 10 + 9 + 3) — same
   8 bytes as before, but no literal-path entries.

Both transforms went into `tools/encode_tiles.py`. The parent's
`sprite_rle.py` is untouched (it remains the spec-exact encoder
that produced the survey numbers in `../docs/sprite_rle_notes.md`);
we inline a smarter column encoder here and reuse the parent's
`decode_sprite` + `pick_flag`. Every sprite still round-trips.

### Result

| Metric              | Before (spec-exact) | After (smart) | Δ       |
|---------------------|--------------------:|--------------:|--------:|
| Total encoded bytes |               1 763 |         1 547 | −216 B  |
| % of raw 2 304 B    |                76 % |          67 % | −9 pp   |
| Duplicate cols      |                   — |     11 of 72  |         |

Where the savings landed:

| Tile | Before | After | Unique cols | Why                       |
|-----:|-------:|------:|------------:|---------------------------|
|    2 |     80 |    20 |           1 | all 4 cols identical      |
|    3 |    108 |    27 |           1 | all 4 cols identical      |
|    6 |     32 |     8 |           1 | blank tile, all 4 == zero |
|    8 |     98 |    74 |           3 | 2 cols share              |
|   17 |    108 |    81 |           3 | 2 cols share              |

Other tiles (0, 1, 4, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16) had 4
distinct columns and saw at most ±1 byte from the run-split rule.

### Tools made self-contained

Final cleanup of the session: pulled the scheme-C library locally so
`ultimate/tools/` no longer imports from `../tools/`. New file
`tools/sprite_rle.py` carries `pick_flag`, `encode_column`,
`encode_sprite` (the spec-exact ones, kept as the documented
reference baseline), `decode_column`, and `decode_sprite`. The
sprite-size constants (`SPRITE_W_COLS=4`, `SPRITE_COL_BYTES=32`,
`SPRITE_SIZE=128`) are defined directly in the module, so it has no
upward imports either. `encode_tiles.py` imports `decode_sprite +
pick_flag` from the local module for round-trip + flag selection;
its column encoder stays a local override implementing the all-RLE
long-run split + within-sprite column coalescing. Verified: same
`tiles.6502` output (1 547 B), same round-trip pass.

### Next

* Wire up CRTC vertical-rupture for the HUD split.
* Sketch the hardware-scroll setup (which CRTC R12/R13 base
  addresses the playfield walks).
* Start building the per-sprite metadata tables and the runtime
  decoder + 2bpp→4bpp expander from `../docs/sprite_rle_notes.md`'s
  option-α / final-form code. Aim is a still picture of the level-1
  stage-1 playfield rendered from the compressed tile catalog +
  map streams before we add scrolling.
