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

## Three scheme candidates — all prototyped, round-trip verified

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

### Scheme C — per-sprite 5+3 with XOR encoding (Rich's morning-after refinement)

The killer simplification of scheme A. Two combined ideas:

1. **Per-sprite FLAG**, not per-set. Each 128-byte sprite picks
   its OWN unused 5-bit prefix. This is empirically always
   possible (see "Per-sprite feasibility" below) so we never
   need the `c + 1` escape-the-escape path.

2. **Store bytes XORed with FLAG_BYTE** (where `FLAG_BYTE =
   FLAG << 3`). After the XOR:
   * A byte whose top 5 bits matched FLAG (= a run-code) has
     top 5 bits zero → encoded value is 0..7.
   * Any other byte has at least one of its top 5 bits flipped
     → encoded value is ≥ 8.

   The decoder distinguishes the two with a single `CMP #8 /
   BCS`. No mask, no equality test against the flag.

Encoded blob shape (per sprite):

```
+0:    flag-byte (FLAG << 3; bottom 3 bits zero)
+1..:  encoded stream
         each stream byte b:
             b < 8   →  run code. count = b + 3 (= 3..10).
                        next byte d follows; emit (d XOR FLAG_BYTE)
                        `count` times.
             b ≥ 8   →  literal. emit (b XOR FLAG_BYTE) once.
```

(Uncompressed length is always 128 per sprite, so no length
header is needed inline. If we ship a per-set blob containing
multiple sprites, a per-set sprite-count + per-sprite start
offsets in a small directory work — TBD when the binary layout
lands.)

**Decoder**:

```asm
.decode_sprite
    LDA sprite_flag_byte   ; the +0 header
    STA .lit_eor + 1       ; self-mod the EOR operands
    STA .run_eor + 1
    LDY #0
.decode_loop
    LDA (zp_src),Y         ; encoded byte
    INC zp_src             ; (16-bit carry handling elided here)
    CMP #8
    BCS .literal
    ; A < 8: run code. count = A + 3.
    CLC : ADC #3
    TAX                    ; X = repeat count (3..10)
    LDA (zp_src),Y         ; the value byte
    INC zp_src
.run_eor
    EOR #00                ; self-modified to FLAG_BYTE
.run_loop
    ; ... wire the 2bpp→4bpp LUT here ...
    STA (zp_dst),Y / INC zp_dst
    STA (zp_dst),Y / INC zp_dst    ; two output bytes per source
    DEX / BNE .run_loop
    JMP .decode_loop
.literal
.lit_eor
    EOR #00                ; self-modified to FLAG_BYTE
    ; ... LUT here ...
    STA (zp_dst),Y / INC zp_dst
    STA (zp_dst),Y / INC zp_dst
    JMP .decode_loop
```

Decoder code ≈ 35 bytes (with the LUT lookups it's a bit larger
than the bare scheme).

Per source byte:
* Literal: `LDA / INC / CMP / BCS / EOR / LUT / 2×STA / 2×INC /
  JMP` ≈ **~22 cyc / literal source byte** — about 4 cyc
  faster per literal than scheme A.
* Run-body: same as scheme A (~15 cyc/source-byte amortised).

### Per-sprite feasibility (scheme C)

Direct check of all 184 sprites (72 tiles + 112 hazards) shows
**every sprite has at least one unused 5-bit prefix**. Stats:

| min unused | max unused | mean | sprites with ≤ 5 unused |
|---:|---:|---:|---:|
|  3 | 31 | 16.1 | 4 (= 2 %) |

So per-sprite scheme C works universally with no special cases.

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

`A` = scheme A (per-set, 5+3 c+1). `B` = scheme B (per-set,
alt-block). `C-data` = scheme C compressed stream only (no
per-sprite headers). `C+hdr` = scheme C with one flag-byte per
sprite added.

| Set            | Raw    | A      | B      | C-data | C+hdr  |
|----------------|-------:|-------:|-------:|-------:|-------:|
| L1 tiles       |  2 304 | 1 442  | 1 437  | 1 442  | 1 460  |
| L2 tiles       |  2 304 | 1 139  | 1 099  | 1 139  | 1 157  |
| L3 tiles       |  2 304 | 1 347  | 1 356  | 1 347  | 1 365  |
| L4 tiles       |  2 304 | 1 536  | 1 524  | 1 534  | 1 552  |
| L1S1 hazards   |  1 792 | 1 331  | 1 391  | 1 331  | 1 345  |
| L1S2 hazards   |  1 792 | 1 440  | 1 524  | 1 440  | 1 454  |
| L2S1 hazards   |  1 792 | 1 471  | 1 533  | 1 466  | 1 480  |
| L2S2 hazards   |  1 792 | 1 418  | 1 485  | 1 413  | 1 427  |
| L3S1 hazards   |  1 792 | 1 361  | 1 421  | 1 361  | 1 375  |
| L3S2 hazards   |  1 792 | 1 341  | 1 466  | 1 341  | 1 355  |
| L4S1 hazards   |  1 792 | 1 493  | 1 600  | 1 489  | 1 503  |
| L4S2 hazards   |  1 792 | 1 373  | 1 446  | 1 371  | 1 385  |
| **TOTAL**      | 23 552 | **16 692** (70.9 %) | 17 282 (73.4 %) | **16 674** (70.8 %) | 16 858 (71.6 %) |

* **Scheme C data** is **18 bytes smaller** than scheme A —
  per-sprite optimisation can pick a better flag for each
  sprite, and the 4 sets that needed `c+1` collisions in scheme
  A no longer pay that cost in scheme C (every individual
  sprite has an unused prefix).
* **With per-sprite headers**: scheme C costs +166 bytes
  vs scheme A (≈ 1 %). Negligible.
* **Tiles** under scheme B win 3 of 4 vs scheme A by a handful
  of bytes thanks to no per-byte FLAG overhead in the long
  zero-pad regions.
* **Hazards** favour scheme A (and C) by +60 to +125 bytes per
  set vs scheme B because they're denser (more short runs, more
  isolated literals → more per-block framing overhead in B).
* Scheme A's chosen flag per set:
    * L1 tiles `&12`, L2 tiles `&12`, L3 tiles `&0B`, L4 tiles `&17`
    * L1S1 `&13`, L1S2 `&0D`, L2S1 `&08`, L2S2 `&07`
    * L3S1 `&0A`, L3S2 `&0F`, L4S1 `&05`, L4S2 `&05`
* Scheme A's L4 sets all needed the `c + 1` literal-escape path
  (2-6 collision bytes each — no fully-unused 5-bit prefix
  exists in those sets). The refinement absorbed those at
  effectively zero overhead. Scheme C side-steps the issue
  entirely by picking flags per-sprite.

## Decode-speed estimate for the frame-1 unpack pipeline

Cycle estimates with the 2bpp→4bpp LUT folded into the emit
loop. Per **source** byte (each source byte emits two 4bpp
output bytes):

| Path                          | Scheme A    | Scheme B    | Scheme C    |
|-------------------------------|------------:|------------:|------------:|
| Decide literal vs escape      | ~17 cyc (LDA/AND/CMP/Bxx) | per-block, amortises away | ~9 cyc (CMP/BCS) |
| Literal: LUT lookup + 2 STAs  | +~25 cyc    | ~25 cyc     | EOR + ~25 cyc |
| **Per literal source byte**   | **~42 cyc** | **~25 cyc** | **~36 cyc** |
| Run body (LUT once, copy N)   | ~15 cyc     | ~15 cyc     | ~15 cyc     |

Scheme C's literal path beats scheme A by ~6 cyc/byte (the
`CMP #8 / BCS` is cheaper than `AND / CMP / BEQ`) but still
costs the EOR per byte — so scheme B remains the fastest of
the three on the literal path.

Weighted by the actual data:

* **Hazards** (52 % length-1 literals):
  * A ≈ 0.52·42 + 0.48·15 ≈ **29 cyc/source-byte**
  * B ≈ 0.52·25 + 0.48·15 ≈ **20 cyc/source-byte** (~31 % faster)
  * C ≈ 0.52·36 + 0.48·15 ≈ **26 cyc/source-byte** (~10 % faster)
* **Tiles** (35 % literals):
  * A ≈ 0.35·42 + 0.65·15 ≈ **25 cyc/source-byte**
  * B ≈ 0.35·25 + 0.65·15 ≈ **19 cyc/source-byte** (~24 % faster)
  * C ≈ 0.35·36 + 0.65·15 ≈ **22 cyc/source-byte** (~12 % faster)

Per game-tick budget: a 32 000-cycle vsync frame (BBC 2 MHz)
can unpack roughly **1 500** source bytes under scheme A,
**2 000** under scheme B, or **1 700** under scheme C for
hazard-shaped data.

## Recommendation — pick B for raw speed, C for the cleanest binary

For the MODE 2 remake's hot path, the choice is now between B
and C — scheme A is dominated by both. Trade-off:

| | Scheme B | Scheme C |
|---|---|---|
| Compressed size            | 17 282 B (73.4 %) | **16 858 B (71.6 %)** |
| Per-literal cycle cost     | **~25 cyc** | ~36 cyc |
| Per-set parameter          | none | 1 flag byte per sprite |
| Decoder code size          | ~25 bytes | ~35 bytes |
| Per-byte branch in loop    | none | one `CMP #8 / BCS` |
| Per-sprite random access   | needs scan to find sprite boundary | trivial (each sprite is its own blob) |
| LUT pre-XOR opportunity    | n/a | yes — bake FLAG into the LUT once per sprite, eliminating the per-byte EOR |

That last row is the kicker. With scheme C we can **pre-XOR
the per-byte 2bpp→4bpp LUT** with FLAG_BYTE once at decode-
start (a single 256-byte XOR sweep, or compile the LUT twice
to a memory page and switch via self-modified base address).
Then the EOR drops out of the inner loop and scheme C's
literal cost drops to ~25 cyc — matching scheme B exactly.

With that optimisation in place:

* Scheme C ties scheme B on speed.
* Scheme C compresses **424 bytes better** than scheme B (1.8 %).
* Scheme C gives free per-sprite random access (each sprite is
  a self-contained blob), which is useful if the engine only
  needs to decompress a subset of sprites per frame.

→ **Lean toward scheme C** unless we discover that per-sprite
random access isn't needed AND the LUT-prepare cost amortises
poorly. Scheme B is the close second.

## When we get to building it

The remake itself starts today with a fresh BeebAsm project +
infrastructure work — this RLE tool isn't the first thing to
land. When we come back to it:

1. **`tools/sprite_rle.py`** — library + CLI with all three
   schemes, the same column-bounded encoders that produced the
   numbers above. API:

   ```python
   # Scheme A (per-set 5+3 with c+1 literal-escape)
   def encode_5_3_c1(buf, n_cols, n_lines, sprite_size, flag) -> bytes
   def decode_5_3_c1(enc, flag) -> bytes
   def best_flag_5_3_c1(buf, n_cols, n_lines, sprite_size) -> tuple[int, int]

   # Scheme B (per-set alternating block)
   def encode_alt(buf, n_cols, n_lines, sprite_size, min_run=4) -> bytes
   def decode_alt(enc, target_len) -> bytes

   # Scheme C (per-sprite 5+3 with XOR encoding)
   def encode_per_sprite(sprite, n_cols, n_lines, flag) -> bytes
   def decode_per_sprite(enc, flag) -> bytes
   def best_flag_per_sprite(sprite, n_cols, n_lines) -> tuple[int, int]
   ```

   CLI subcommands: `survey`, `encode`, `decode`, `test`.
   Reuse `LEVD1_LOAD` / `LEVD2_LOAD` / `SPRITE_W_COLS` etc.
   from `tools/render_level.py` rather than duplicating constants.

2. **Output blob format**:
   * Scheme A: `[flag<<3][LO][HI][data...]`
   * Scheme B: `[LO][HI][alternating count/data...]`
   * Scheme C: per-sprite `[flag<<3][stream...]` — length is
     implicit (always 128 B); for a multi-sprite set we ship
     either back-to-back blobs preceded by a small directory
     (sprite count + start offsets) OR back-to-back blobs with
     a fixed per-sprite stride if we want O(1) addressing.

3. **Tests**: round-trip every sprite under all three schemes
   byte-identical; assert no run in the encoded stream crosses
   a column or sprite boundary; reproduce the per-set / per-
   sprite table above to the byte.

## Open questions to chew on

These are useful to have an answer to before we commit a binary
format, even before the encoder lands:

* **Per-sprite vs per-set blobs.** Scheme C inherently picks
  per-sprite. Schemes A/B can go either way. Per-sprite makes
  random access easy (decompress just the sprites the engine
  needs this frame); per-set is slightly simpler if we always
  unpack the whole set at level load. Per-sprite costs 1 flag
  byte per sprite for scheme C (+184 B / 1 % total in this
  corpus). For schemes A/B the difference is in the noise.
* **End-of-stream signalling.** Schemes A/B use a length
  header (LO, HI) in the blob. Scheme C uses an implicit
  fixed length (= 128 B per sprite). A sentinel-byte
  alternative (e.g. for schemes A/B, a `count=0` followed by
  something) would let the decoder bail without a counter —
  saves a few cycles per stream but burns a count value.
  Probably stick with the length header for A/B and the
  implicit length for C.
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
