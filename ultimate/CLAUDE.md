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

boot.6502                    \\ !BOOT shim (chains to /NEVRYON ULTIMATE)
nevryon.6502                 \\ master source -- INCLUDE order goes here
main.6502                    \\ game-loop + per-tick pipeline (TBD)
entry.6502                   \\ load-time setup + irq install (TBD)

tools/                       \\ build-time Python utilities (self-contained)
  sprite_rle.py              \\ scheme C: encode_*, decode_*, pick_flag
  encode_tiles.py            \\ assets/level<N>/tile_NN.png -> data/level<N>/tiles.6502

assets/                      \\ source artwork -- editable in any pixel editor
  level1/                    \\ tile_00..17.png (16x32 native, scenario-1 palette)

data/                        \\ generated BeebAsm sources, ready to INCLUDE
  level1/
    tiles.6502               \\ scheme C RLE'd 18-tile catalog (1547 B encoded)
```

`build.sh` / Makefile lands when there's something for BeebAsm to
chew on beyond `boot.6502`.

## Sprite RLE — scheme C

See `../docs/sprite_rle_notes.md` for the full design notes. The
short version that matters for code:

* **Per-sprite blob layout (NO inline header)**: just the encoded
  stream. The flag byte is exported as a separate equate
  (e.g. `tile_00_rle_flag = &20`) and consumed at decode-start to
  self-mod the literal-path `EOR #imm`.
* **Encoded stream semantics:**
  * `b < 8`  → run code. `count = b + 3` (so 3..10). The NEXT
    stream byte is the run's source value, shipped **raw** (NOT
    XOR'd with the flag byte — the count code already
    discriminates it).
  * `b >= 8` → literal. Emit `b EOR flag_byte` once.
* **Runs never cross sprite-column boundaries.** Each
  `.tile_NN_col_M` (or `.hazard_XX_col_M`) label is a fresh decoder
  re-entry point for one MODE 5 column (32 source bytes).
* **Per-sprite FLAG** in 0..31 is chosen so no source byte has
  top-5-bits == FLAG. Empirically always possible (every 4×32
  sprite in the corpus has 3+ free 5-bit prefixes).
* **Decoder = option α / final form** from the design notes:
  separate literal and run code paths, four self-modified
  `STA &FFFF,X` instructions per decoder, in-band column exit via
  `DEX` / `BPL`. ≈ 5 300 cyc per tile sprite, ≈ 6 000 cyc per
  hazard sprite at the surveyed corpus' literal/run mix.

### Encoder optimisations beyond the survey

`tools/encode_tiles.py` ships two extras on top of the spec-exact
encoder in `../tools/sprite_rle.py`:

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
  stream is emitted ONCE and the duplicate `.tile_NN_col_M` labels
  are stacked above it so they all resolve to the same address.
  The user's per-column offset table populates from the labels — no
  runtime change.

Both transforms keep the output spec-conformant: the local
`tools/sprite_rle.decode_sprite` round-trips every sprite. Survey
numbers in `../docs/sprite_rle_notes.md` reflect the spec-exact
encoder; ours come out smaller (1 547 B vs 1 763 B for L1 tiles).

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
