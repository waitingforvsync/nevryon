# Nevryon Ultimate

Remake of the BBC Micro game **Nevryon** (The Fourth Dimension, 1990)
— a MODE 5 sideways-scrolling R-Type clone. The remake runs in
**MODE 2 with hardware scrolling**, double the original frame rate
(every 3 vsyncs instead of every 6), and a per-sprite palette.

This directory is a subdirectory of the reverse-engineering repo;
the parent's `docs/`, `extracted/`, `levels/`, `disasm/` are the
authoritative reference. All new code, assets and tools for the
remake live HERE under `ultimate/`.

## Display + timing model

* **MODE 2, hardware-scrolled, 16 K screen buffer.** Only **20 char
  rows** of the buffer are visible at any time (= 12.5 K), giving a
  playfield the same vertical footprint as the original. The remaining
  3.5 K of the buffer is used as an offscreen scratch for the
  unpack-pipeline.
* **HUD = static 2 lines below the playfield** via a CRTC "vertical
  rupture" split — the CRTC base address is reprogrammed mid-frame
  so the HUD comes from a fixed region of RAM that the scroll never
  touches.
* **MODE 2 chars are half the width of MODE 5 chars.** A 1-char/tick
  scroll in MODE 5 is 2 chars/tick in MODE 2, which is too fast — we
  drop the visual scroll rate back to half a MODE 5 column per tick
  by **doubling the game-tick rate** (every 3 vsyncs ≈ 16.7 Hz instead
  of the original's every-6-vsyncs 8.3 Hz). Net motion across the
  screen is the same; everything is smoother.
* **Sprite storage stays 2bpp.** On-disk and in the compressed-blob
  region, sprites are stored as MODE 5 2bpp source bytes; at unpack
  time each source byte expands through a 16-entry ZP LUT into two
  4bpp MODE 2 output bytes. The LUT is initialised per sprite from
  the sprite's own 3-colour palette, so every sprite picks its own
  3 non-background colours.

### Frame budget (one game-tick = 3 vsyncs)

| Vsync | Work                                                                |
|------:|---------------------------------------------------------------------|
|     1 | **Decompress + expand** the sprites this tick needs, from compressed `.6502`-baked source to 4bpp MODE 2, into the 3.5 K offscreen scratch buffer. |
|     2 | **Plot animating hazards** (large 4×32 sprites — gun-towers, tanks, structures). |
|     3 | **Erase + re-plot moving sprites** (player, enemies, missiles, pickups, starfield) at their new positions, and program the CRTC for the next hardware-scroll step. |

## Repository layout (under `ultimate/`)

```
CLAUDE.md                    \\ this file
JOURNAL.md                   \\ working log; newest at top
build.sh                     \\ regen data/ from assets/; also future asm + .ssd

boot.6502                    \\ !BOOT shim (chains to /NEVRYON ULTIMATE)
nevryon.6502                 \\ master source -- INCLUDE order goes here
main.6502                    \\ game-loop + per-tick pipeline (TBD)
entry.6502                   \\ load-time setup + irq install (TBD)

tools/                       \\ build-time Python utilities (self-contained)
  sprite_rle.py              \\ scheme C: encode_*, decode_*, pick_flag
  encode_sprites.py          \\ glob a dir of .png -> compressed BeebAsm file

assets/                      \\ source artwork -- editable in any pixel editor
  level<1..4>/
    tiles/                   \\ 18 x 16x32-px tile PNGs, per-scenario palette
    explosions/              \\ 6 x 16x32-px player-death frames, per-scenario
    stage<1,2>/
      hazards/               \\ 14 per-stage hazard PNGs (hazard_00..13) +
                             \\ 3 game-shared GRAPHIX hazard PNGs
                             \\ (hazard_15/16/19) duplicated per (level, stage)
    (future: enemies/)
  (future: shared/{player,flames,pickups}/)

data/                        \\ generated BeebAsm sources, ready to INCLUDE
  level<1..4>/
    tiles.6502               \\ scheme C RLE'd 18-tile catalog (one per level)
    explosions.6502          \\ scheme C RLE'd 6-frame death explosion
    stage<1,2>/
      hazards.6502           \\ scheme C RLE'd 17-sprite hazard set per stage
```

Run `./build.sh` from `ultimate/` to regenerate everything in
`data/` from the PNG sources in `assets/`. The script is also the
landing pad for BeebAsm assembly + SSD packaging when those land.

## Sprite RLE — scheme C

See `../docs/sprite_rle_notes.md` for the full design notes. The
short version that matters for code:

* **Per-sprite blob layout (NO inline header)**: just the encoded
  stream. The flag byte is exported as a separate equate
  (e.g. `tile_00_rle_flag = &20`) and consumed at decode-start to
  self-mod the literal-path `EOR #imm`.
* **Per-sprite shape equates**: alongside the flag, the encoder
  emits `<name>_width = W` (in MODE 5 byte-columns) and
  `<name>_height = H` (in pixels = bytes per column). The runtime
  reads these for plot loops, metadata tables, and the decoder
  column-walk.
* **Encoded stream semantics:**
  * `b < 8`  → run code. `count = b + 3` (so 3..10). The NEXT
    stream byte is the run's source value, shipped **raw** (NOT
    XOR'd with the flag byte — the count code already
    discriminates it).
  * `b >= 8` → literal. Emit `b EOR flag_byte` once.
* **Runs never cross sprite-column boundaries.** Each
  `.<name>_col_M` label is a fresh decoder re-entry point for one
  MODE 5 column (`<name>_height` source bytes).
* **Per-sprite FLAG** in 0..31 is chosen so no source byte has
  top-5-bits == FLAG. Empirically always possible (every 4×32
  sprite in the corpus has 3+ free 5-bit prefixes).
* **Decoder = option α / final form** from the design notes:
  separate literal and run code paths, four self-modified
  `STA &FFFF,X` instructions per decoder, in-band column exit via
  `DEX` / `BPL`. ≈ 5 300 cyc per tile sprite, ≈ 6 000 cyc per
  hazard sprite at the surveyed corpus' literal/run mix.

### Encoder optimisations beyond the survey

`tools/encode_sprites.py` ships two extras on top of the spec-exact
encoder in `tools/sprite_rle.py`:

* **All-RLE long-run split.** For runs > 10 bytes the spec encoder
  caps at 10 and lets the residue spill as literals (e.g. 32 zeros →
  three 10-runs + two literals, 8 bytes). We instead always close
  the tail with another RLE block (32 zeros → 10+10+9+3, also 8 B —
  but no literal-path entries, since the literal decoder body is
  ~56 cyc vs ~26 cyc per run-body byte). Adds 1 byte for runs of
  length 10·q+1; equal-size otherwise.
* **Within-sprite column coalescing.** If two or more columns of a
  sprite encode to the same byte stream (e.g. tile_06's blank
  all-zero columns, or tile_02's vertically-uniform pattern), the
  stream is emitted ONCE and the duplicate `.<name>_col_M` labels
  are stacked above it so they all resolve to the same address.
  The user's per-column offset table populates from the labels — no
  runtime change.

Both transforms keep the output spec-conformant: the local
`tools/sprite_rle.decode_sprite` round-trips every sprite.

### Per-level encoded sizes

Tiles (18 sprites × 128 B raw / level) and explosions (6 sprites ×
128 B / level):

| Level | Palette                  | Tiles enc / raw    | Explosions enc / raw |
|------:|--------------------------|-------------------:|---------------------:|
|     1 | black/red/yellow/white   |   1 547 / 2 304    |        553 /   768   |
|     2 | black/blue/cyan/white    |   1 231 / 2 304    |        371 /   768   |
|     3 | black/red/green/white    |   1 267 / 2 304    |        645 /   768   |
|     4 | black/red/magenta/white  |   1 835 / 2 304    |        653 /   768   |
|       |                          | **5 880** / 9 216  |  **2 222** / 3 072   |

Hazards: each (level, stage) bundle is the 14 stage-specific
hazards (LEVD2 / LEVD3 slots 0..13) plus the 3 shared GRAPHIX
hazards (slots 15 / 16 / 19) duplicated in, encoded under a
black/red/yellow/white fallback palette. 17 sprites × 128 B raw =
2 176 B per stage:

| Level | Stage 1 enc / raw | Stage 2 enc / raw |
|------:|------------------:|------------------:|
|     1 |    1 634 / 2 176  |    1 658 / 2 176  |
|     2 |    1 672 / 2 176  |    1 622 / 2 176  |
|     3 |    1 666 / 2 176  |    1 542 / 2 176  |
|     4 |    1 694 / 2 176  |    1 660 / 2 176  |
|       | **6 666** / 8 704 | **6 482** / 8 704 |

Three of the four levels match the spec-exact tile survey figures
in `../docs/sprite_rle_notes.md` to the byte; L1 tiles save 216 B
via within-sprite column coalescing, L2 explosions save 4 B for
the same reason, and L2 tiles is +9 B (the all-RLE-tail rule's
+1 B-per-run cost on a sprite set with no coalescing opportunities).
Hazard sets all run a bit larger than the bare LEVD-only survey
numbers because the 3 GRAPHIX hazards (~ 299 B encoded) are folded
into every stage's bundle now.

## Regenerating the data

```bash
./build.sh
```

regenerates every `data/*.6502` from the PNGs in `assets/`. The
script lives at `ultimate/build.sh` and codifies the
per-asset-category invocations of `tools/encode_sprites.py`. It is
re-runnable; the resulting `.6502` files are checked-in so a fresh
clone can assemble without running the encoders.

### tools/encode_sprites.py — what it does

* Globs `*.png` from `--src` (top-level, sorted alphabetically).
* Auto-detects each PNG's dimensions; rejects any whose width isn't
  a multiple of 4 (MODE 5 = 4 px per byte).
* The PNG's filename stem becomes the BeebAsm symbol prefix —
  `tile_06.png` → `tile_06_width`, `tile_06_height`,
  `tile_06_rle_flag`, `.tile_06_col_0..3`. The stem (and the
  optional `--name-prefix` joined to it) must match
  `[A-Za-z_][A-Za-z0-9_]*`.
* `--name-prefix PREFIX` (optional) prepends `PREFIX_` to every
  generated symbol, so the four per-level data files in this repo
  carry `level1_` / `level2_` / etc. prefixes and can be INCLUDE'd
  side-by-side without colliding (`level1_tile_06_rle_flag` vs
  `level2_tile_06_rle_flag`).
* Validates every pixel against `--palette` (4 colours, comma-
  separated, BBC physical names or 6-digit hex). Off-palette pixels
  error with their `(x, y)` coordinates so they're easy to find in
  an editor.
* Accepts one or more `--fallback-palette` arguments. If a sprite's
  pixels don't all match the primary palette, the encoder tries
  each fallback in order; the first palette covering every pixel of
  that sprite is the one used. The chosen palette index is noted in
  the per-sprite header comment (`fallback palette N`). Use case:
  copying "general" sprites (e.g. GRAPHIX-hosted hazards rendered
  in L1 colours) into another scenario's asset set without
  repainting.
* Round-trips every sprite through `tools/sprite_rle.decode_sprite`
  before writing the output file.

## 2bpp → 4bpp expansion

Same as designed in `../docs/sprite_rle_notes.md`. Hot path:

* `init_colour_lut(A, X, Y)` — fills 15 sparse ZP entries from
  the sprite's three colour bytes. Run once per sprite at
  unpack-start (each sprite stores its three palette colours in
  its metadata).
* `convert2bpp4bpp` — 38 cyc body: takes one MODE 5 source byte in
  A, line index in X, writes two MODE 2 output bytes to the
  current pair of self-modded output columns.

Both the RLE path and any raw-blit path (animating sprites that
opt out of RLE — player, enemies, flames, pickups) feed every
source byte through this LUT. The LUT is the format converter,
not part of the compressor.

## Numeric notation

* Use BBC-style hex with `&` (e.g. `&3000`, `&7380`) in 6502 source,
  BeebAsm comments, and prose.
* Use `0x` only inside Python (`tools/*.py`).
* `EQUB &XX, &YY, ...` for byte literals in `.6502` sources.

## Tool conventions

* Python tools: standard library only where possible; Pillow OK if
  needed for image I/O (call it out in the tool).
* **Source of truth for art is the PNG in `assets/<level>/`** — not
  the parent repo's extracted LEVD bytes. Encoders read PNGs and
  emit the compressed BeebAsm-ready bytes, so the workflow is:
  edit PNG in any pixel editor → re-run encoder → BeebAsm picks up
  the new `.6502`. Pixels must stay on the level's palette (the
  encoder errors with pixel coordinates if anything goes off-palette).
* All scripts are deterministic + re-runnable. The output of
  `tools/encode_tiles.py` is checked-in; regenerating it from the
  current PNGs must produce a byte-identical file.
* Round-trip-verify every sprite during encode. A silent encoder bug
  becomes invisible at the BeebAsm level — the assembler just bakes
  in whatever bytes we ship.
* Scripts resolve paths from their own location (`Path(__file__)`),
  not from CWD, so they run from anywhere in the tree.

## Where to look in the parent repo

The remake's `tools/` is **self-contained** — it doesn't import from
the parent. The parent is the reference / archaeology source:

* `../CLAUDE.md` — RE workflow + conventions for the original.
* `../JOURNAL.md` — the running RE journal (sessions 1..41+).
* `../docs/sprite_rle_notes.md` — full scheme-C design + cycle-counted
  decoder + the 2bpp→4bpp LUT init / expansion code.
* `../docs/engine_overview.md` — how the original engine actually
  runs (NPC pools, state machines, motion patterns, pickups,
  force-pod / missile unlocks).
* `../docs/memory_map.md` — original CPU memory map + spawn-attribute
  encoding.
* `../docs/file_layout.md` — per-file content reference for the
  extracted LEVD/CODE/GRAPHIX binaries.
* `../levels/<n>/README.md` — per-level sprite + map inventory.
* `../extracted/` — canonical extracted-from-disk binaries
  (`1.LEVD1`, `1.LEVD2`, `1.LEVD3`, `$.GRAPHIX`, etc.). Use when
  re-deriving an `assets/` PNG from scratch.
* `../tools/sprite_rle.py` — spec-exact scheme-C reference that
  produced the survey numbers; mirrored locally as
  `tools/sprite_rle.py`.

## Git workflow

* Branch: `main`. Commits live in the same repo as the RE work.
* Commit only when explicitly asked. Don't push without instruction.
* Generated `.6502` files (e.g. `tiles_level1.6502`) ARE checked in
  alongside the script that produced them — they're considered
  "build inputs" for BeebAsm, and the reproducibility lives in
  `tools/encode_tiles.py`.

## How to update these docs

* **CLAUDE.md** — stable; update when the workflow / display model /
  RLE format / directory layout changes.
* **JOURNAL.md** — newest at top, date-stamped (YYYY-MM-DD), a short
  narrative per working session: what was attempted, what worked,
  what didn't, next planned step.
