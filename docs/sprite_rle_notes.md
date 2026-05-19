# Sprite RLE — design notes for a Nevryon remake

Working notes from a planning session — to be picked up tomorrow.
The Python encoder/decoder + CLI tool isn't built yet; this
document is purely the design + the numbers.

## Context

The remake will run in **MODE 2 with hardware scrolling** (smoother
motion than MODE 5 software scroll). Game-update cadence is one
tick per **3 vsyncs** (≈ 16.7 Hz), split across the three vsync
frames as:

* **Frame 1**: unpack the 2bpp packed sprite data (from on-disk
  storage) into 4bpp screen-ready bytes with the per-sprite
  palette mapping. **Decompression happens here**, in the same
  pass — read compressed source bytes, convert them through the
  per-byte 2bpp→4bpp LUT (≈ 15 cyc / source byte), write to the
  unpacked-sprite buffer.
* **Frame 2**: redraw animating hazards.
* **Frame 3**: redraw enemies, player, starfield.

The 2bpp→4bpp conversion is the big win that motivates RLE: each
source byte expands to two 4bpp output bytes, and a run of N
identical source bytes produces N identical output-byte-pairs.
So a run lets us do the LUT lookup ONCE and `STA` the result
N times — saving (N − 1) lookups per run.

That makes **inner-loop unpack speed critical**. Any per-byte
mask/compare in the decompress loop is paid every byte of every
active sprite, every game tick (which is at the same rate as the
game's own update). Whatever scheme we pick should optimise for
that.

## Survey scope

Just the two sprite categories Rich asked about for now:

* **Tile catalogs** — all 4 scenarios, LEVD1 `&4F00..&5700`
  (18 sprites × 128 B per scenario)
* **Hazard sprite blocks** — all 4 scenarios × 2 stages,
  LEVD2 / LEVD3 `&7380..&7A7F` (14 sprites × 128 B per stage)

12 sets total (4 tile sets + 8 hazard sets). Run-length tally
treats each 32-byte sprite column independently — runs never
cross either a sprite-column or a sprite boundary.

## Run-length distribution (within sprite columns)

Aggregated across all 12 sets:

| Length | Tiles: runs | Tiles: % bytes | Hazards: runs | Hazards: % bytes |
|-------:|-----------:|---------------:|--------------:|-----------------:|
|      1 |      3187  |        34.6 %  |          7484 |          52.2 %  |
|      2 |       328  |         7.1 %  |           888 |          12.4 %  |
|      3 |       117  |         3.8 %  |           329 |           6.9 %  |
|   4..6 |       139  |         6.9 %  |           318 |          10.7 %  |
|  7..10 |        55  |         5.1 %  |           115 |           6.4 %  |
| 11..15 |       100  |        13.7 %  |            61 |           5.0 %  |
| 16..21 |        48  |         9.4 %  |            21 |           2.6 %  |
| 22..31 |        45  |        12.8 %  |            22 |           3.8 %  |
|     32 |        19  |         6.6 %  |             0 |           0.0 %  |

Key signal:

* **Tiles**: 25 % of bytes sit in runs of 16 or more (long
  zero-pads from inter-tile margins). RLE pays handsomely.
* **Hazards**: denser; longest run anywhere is 30 bytes; 52 %
  of bytes are isolated single literals.

## Two scheme candidates — both prototyped, round-trip verified

### Scheme A — 5+3 with `c+1` literal-escape (per-byte branch)

```
stream byte B:
  if (B & 0xF8) != FLAG → emit B as literal
  else                  → read next byte D, count = B & 7:
                            if (D & 0xF8) == FLAG: run = count + 1   (1..8 — escape-the-escape)
                            else:                  run = count + 3   (3..10 — normal run)
                            emit D run times
```

* Per-set parameter: a 5-bit FLAG (the unused or rarest top-5-bit
  prefix in the source). Stored as one header byte in the
  encoded blob.
* The `c + 1` interpretation handles bytes whose top 5 bits
  *do* match FLAG without needing a separate escape sequence.

**Decoder** (per source byte):
```
LDA (zp_src),Y   ; 5
TAX              ; 2
AND #&F8         ; 2
CMP #FLAG        ; 2
BEQ run_path     ; 2/3
TXA              ; 2
STA (zp_dst),Y   ; 6
INC zp_dst       ; 5 (worst case, no page-cross)
```
≈ **26 cyc / literal source byte**. Run bodies amortise (LUT
done once per run; the run loop is just `STA / INX / CPX / BNE`
≈ 10 cyc / source-byte).

### Scheme B — alternating block scheme (per-block branch)

```
stream: [count][lit_0..lit_count-1] [count][value] [count][lit...] [count][value] ...

Always starts with a literal block (count may be 0).
Adjacent run blocks need a count=0 literal-block separator
(takes 1 byte).
```

* No per-set parameter (the only knob is `min_run`, and 3 and 4
  produce identical sizes — see "min_run break-even" below).
* count is one byte → 0..255 entries per block. Runs > 255
  split via a 0-count L-block separator; literal stretches >
  255 split via a 1-byte run junction (the encoder steals the
  next byte and encodes it as a run-of-1).

**Decoder** parses one block header, then runs a tight emit
loop. No per-byte branch in either path:
```
.alt_decode
    LDA (zp_src),Y       ; count
    INC zp_src
    TAX
    BEQ .skip_lit        ; empty separator
.lit_loop
    LDA (zp_src),Y / TAY ; or however we wire the 2bpp→4bpp LUT
    LDA lut_lo,Y / STA (zp_dst),Y / INC zp_dst
    LDA lut_hi,Y / STA (zp_dst),Y / INC zp_dst
    DEX / BNE .lit_loop
.skip_lit
    LDA (zp_src),Y       ; run count (or end-of-stream)
    INC zp_src
    BEQ .done
    TAX
    LDA (zp_src),Y / TAY ; the run's source byte (LUT once)
    INC zp_src
    LDA lut_lo,Y / STA scratch_lo
    LDA lut_hi,Y / STA scratch_hi
.run_loop
    LDA scratch_lo / STA (zp_dst),Y / INC zp_dst
    LDA scratch_hi / STA (zp_dst),Y / INC zp_dst
    DEX / BNE .run_loop
    JMP .alt_decode
```
≈ **14-20 cyc / source byte** for both literals and runs once
the LUT is folded in. Decoder code ≈ 25 bytes (vs ≈ 40 for
scheme A).

### `min_run` break-even for scheme B

For scheme B, runs of 3 and runs of 4 produce identical encoded
sizes:

| Source pattern | Inline (literal) | Broken out (run) |
|----------------|------------------|------------------|
| 3-byte run     | 3 bytes          | 2 (run block) + 1 (new L header) = 3 |
| 4-byte run     | 4 bytes          | 2 + 1 = 3 (saves 1) |

So `min_run = 4` is the natural choice (fewer run blocks
emitted, same total size).

* `min_run = 2` adds many 2-runs as run blocks; each costs +1
  byte vs literal. Whole-corpus penalty: +1 215 bytes — worse.
* `min_run = 5` skips 4-runs; each loses 1 byte. Whole-corpus
  penalty: +224 bytes.

## Survey results — round-trip verified

| Set                | Raw   | Scheme A (5+3 c+1)   | Scheme B (alt-block) | B − A |
|--------------------|------:|---------------------:|---------------------:|------:|
| L1 tiles           |  2304 |  **1 442** (62.6 %)  |  **1 437** (62.4 %)  |  −  5 |
| L2 tiles           |  2304 |  **1 139** (49.4 %)  |  **1 099** (47.7 %)  |  − 40 |
| L3 tiles           |  2304 |  **1 347** (58.5 %)  |   1 356  (58.9 %)    |  +  9 |
| L4 tiles           |  2304 |  **1 536** (66.7 %)  |  **1 524** (66.1 %)  |  − 12 |
| L1S1 hazards       |  1792 |  **1 331** (74.3 %)  |   1 391  (77.6 %)    |  + 60 |
| L1S2 hazards       |  1792 |  **1 440** (80.4 %)  |   1 524  (85.0 %)    |  + 84 |
| L2S1 hazards       |  1792 |  **1 471** (82.1 %)  |   1 533  (85.5 %)    |  + 62 |
| L2S2 hazards       |  1792 |  **1 418** (79.1 %)  |   1 485  (82.9 %)    |  + 67 |
| L3S1 hazards       |  1792 |  **1 361** (75.9 %)  |   1 421  (79.3 %)    |  + 60 |
| L3S2 hazards       |  1792 |  **1 341** (74.8 %)  |   1 466  (81.8 %)    |  +125 |
| L4S1 hazards       |  1792 |  **1 493** (83.3 %)  |   1 600  (89.3 %)    |  +107 |
| L4S2 hazards       |  1792 |  **1 373** (76.6 %)  |   1 446  (80.7 %)    |  + 73 |
| **TOTAL**          | 23 552 | **16 692** (70.9 %)  |  17 282 (73.4 %)     |  +590 |

* **Tiles** are mostly a wash; scheme B wins 3 of 4 by a handful
  of bytes thanks to no per-byte FLAG overhead in the long
  zero-pad regions.
* **Hazards** favour scheme A by +60 to +125 bytes per set
  because they're denser (more short runs, more isolated
  literals → more per-block framing overhead in scheme B).
* Scheme A's chosen flag per set:
    * L1 tiles `&12`, L2 tiles `&12`, L3 tiles `&0B`, L4 tiles `&17`
    * L1S1 `&13`, L1S2 `&0D`, L2S1 `&08`, L2S2 `&07`
    * L3S1 `&0A`, L3S2 `&0F`, L4S1 `&05`, L4S2 `&05`
* Scheme A's L4 sets all needed the `c + 1` literal-escape path
  (2-6 collision bytes each — no fully-unused 5-bit prefix
  exists in those sets). The refinement absorbed those at
  effectively zero overhead.

## Decode-speed estimate for the frame-1 unpack pipeline

Cycle estimates with the 2bpp→4bpp LUT folded into the emit
loop. Per **source** byte (each source byte emits two 4bpp
output bytes):

| Path                          | Scheme A    | Scheme B    |
|-------------------------------|------------:|------------:|
| Decide literal vs escape      | ~17 cyc     | (per-block, amortises away) |
| Literal: LUT lookup + 2 STAs  | +~25 cyc    | ~25 cyc     |
| **Per literal source byte**   | **~42 cyc** | **~25 cyc** |
| Run body (LUT once, copy N)   | ~15 cyc     | ~15 cyc     |

The literal path is where scheme B's "no per-byte branch" wins
— roughly **1.7 × faster per literal byte**. Run bodies are a
wash because the LUT lookup amortises identically in both.

Weighted by the actual data:

* **Hazards** (52 % length-1 literals): scheme A ≈ 0.52·42 +
  0.48·15 ≈ 29 cyc/source-byte; scheme B ≈ 0.52·25 + 0.48·15 ≈
  20 cyc. **Scheme B ≈ 31 % faster per source byte.**
* **Tiles** (35 % literals): scheme A ≈ 0.35·42 + 0.65·15 ≈ 25
  cyc; scheme B ≈ 0.35·25 + 0.65·15 ≈ 19 cyc. **Scheme B ≈
  24 % faster per source byte.**

Per game-tick budget: a 32 000-cycle vsync frame (BBC 2 MHz)
can unpack roughly **1 500** source bytes under scheme A or
**2 000 under scheme B** for hazard-shaped data. Big difference
for the per-tick on-screen sprite budget.

## Recommendation — scheme B (alt-block)

For the MODE 2 remake's hot path (decompress + LUT-unpack every
game tick), scheme B is meaningfully faster on the literal-heavy
hazard data — which is the byte category that dominates unpack
work. The +590 bytes (3.5 %) larger compressed corpus is a fine
trade for ~24-31 % faster unpacking.

If a different scenario emerges (e.g. multiple sprite sets
decompressed at level load only, never during play), scheme A's
smaller size could be more valuable. The Python tool will
implement both regardless, so swapping later is cheap.

## When we get to building it

The remake itself starts tomorrow with a fresh BeebAsm project +
some infrastructure work — this RLE tool isn't the first thing
to land. When we do come back to it, the sketch is:

1. **`tools/sprite_rle.py`** — library + CLI with both schemes,
   the same column-bounded encoders that produced the numbers
   above. API:

   ```python
   def encode_5_3_c1(buf, n_cols, n_lines, sprite_size, flag) -> bytes
   def decode_5_3_c1(enc, flag) -> bytes
   def best_flag_5_3_c1(buf, n_cols, n_lines, sprite_size) -> tuple[int, int]

   def encode_alt(buf, n_cols, n_lines, sprite_size, min_run=4) -> bytes
   def decode_alt(enc, target_len) -> bytes
   ```

   CLI subcommands: `survey`, `encode`, `decode`, `test`.
   Reuse `LEVD1_LOAD` / `LEVD2_LOAD` / `SPRITE_W_COLS` etc.
   from `tools/render_level.py` rather than duplicating constants.

2. **Output blob format**:
   * Scheme A: `[flag<<3][LO][HI][data...]`
   * Scheme B: `[LO][HI][alternating count/data...]`

3. **Tests**: round-trip every set under both schemes
   byte-identical; assert no run in the encoded stream crosses
   a column or sprite boundary; reproduce the per-set table
   above to the byte.

## Open questions to chew on

These are useful to have an answer to before we commit a binary
format, even before the encoder lands:

* **Per-sprite vs per-set blobs.** Do we ship each 128-byte
  sprite as its own RLE-compressed entry (with its own
  length/flag header), or one blob per 14-/18-sprite set?
  Per-set is simpler and slightly more compressible (literal
  blocks can run across sprite boundaries in scheme B).
  Per-sprite makes random access easier (decompress just the
  sprites the engine actually needs this frame, skipping unused
  ones in the catalog). Cost vs benefit depends on how the
  remake's draw path is organised — TBD once the BeebAsm
  scaffolding is in place.
* **Per-palette LUT vs global LUT.** The 2bpp→4bpp conversion
  uses a 256-entry LUT (or two 256-entry LUTs, one for each
  4bpp output byte). If the palette is fixed at level load, one
  global LUT is fine. If we want arbitrary per-sprite
  recolouring (e.g. for power-ups, blink states), each palette
  needs its own LUT — 256-512 bytes per palette.
* **Other sprite categories not surveyed.** The numbers above
  only cover tiles + hazards. Other categories:
  * **Enemies** — 4×24 = 96 B per frame; 4 normal + 3 hit
    frames per scenario. Different column height (24 instead of
    32). Schemes apply unchanged.
  * **Player sprite** — 6×22 = 132 B.
  * **Player explosion** — 4×32 = 128 B × 6 frames.
  * **GRAPHIX sprites** — pod frames (12×24), ball frames
    (2×24), flame (32×8), missiles (5×8), pickups (8×16),
    icons (4×8), text strings (various).
  Worth running the survey against all of them once the tool
  exists, so we know the total compressed footprint.
* **End-of-stream signalling.** Both schemes currently use a
  length header (LO, HI) in the blob. A sentinel-byte
  alternative (e.g. count=0 followed by something) would let
  the decoder bail without checking the count — saves a few
  cycles per stream but loses a value from the count space.
  Probably stick with the length header.

## Related files

* `/home/rich/.claude/plans/nested-inventing-zebra.md` — the
  full approved plan from this session (same design, slightly
  different framing).
* `tools/render_level.py` — has the authoritative
  `LEVD1_LOAD` / `LEVD2_LOAD` / `SPRITE_*` constants and the
  `build_sprite_inventory()` / `build_hazard_blocks(stage)`
  functions that define "what bytes are a sprite". The RLE
  survey should reuse those when the tool lands.
* `docs/engine_overview.md` — context on what each sprite
  category is used for in the original engine.
