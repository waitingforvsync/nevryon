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

(An earlier per-set 5+3 scheme with a `c + 1` literal-escape
extension is dropped — scheme C below subsumes it. The
breadcrumb: per-set flag selection fails on 4 of 12 sprite sets
because they exhaust the 32 possible 5-bit prefixes; the c+1
trick worked around it but was per-set bookkeeping nobody
needed. Per-sprite flag selection (scheme C) never has that
problem, so the c+1 extension goes away.)

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

### Scheme C — per-sprite 5+3 with XOR encoding

Two combined ideas:

1. **Per-sprite FLAG**, not per-set. Each 128-byte sprite picks
   its OWN unused 5-bit prefix. This is empirically always
   possible (see "Per-sprite feasibility" below) — no
   escape-the-escape path needed.

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

`B` = scheme B (per-set, alt-block).
`C-data` = scheme C compressed stream only (no per-sprite headers).
`C+hdr` = scheme C with one flag-byte per sprite added.

| Set            | Raw    | Scheme B | Scheme C (data) | Scheme C (+1B/sprite hdr) |
|----------------|-------:|---------:|----------------:|--------------------------:|
| L1 tiles       |  2 304 |  1 437   |  1 442          | 1 460                     |
| L2 tiles       |  2 304 |  1 099   |  1 139          | 1 157                     |
| L3 tiles       |  2 304 |  1 356   |  1 347          | 1 365                     |
| L4 tiles       |  2 304 |  1 524   |  1 534          | 1 552                     |
| L1S1 hazards   |  1 792 |  1 391   |  1 331          | 1 345                     |
| L1S2 hazards   |  1 792 |  1 524   |  1 440          | 1 454                     |
| L2S1 hazards   |  1 792 |  1 533   |  1 466          | 1 480                     |
| L2S2 hazards   |  1 792 |  1 485   |  1 413          | 1 427                     |
| L3S1 hazards   |  1 792 |  1 421   |  1 361          | 1 375                     |
| L3S2 hazards   |  1 792 |  1 466   |  1 341          | 1 355                     |
| L4S1 hazards   |  1 792 |  1 600   |  1 489          | 1 503                     |
| L4S2 hazards   |  1 792 |  1 446   |  1 371          | 1 385                     |
| **TOTAL**      | 23 552 | 17 282 (73.4 %) | **16 674** (70.8 %) | 16 858 (71.6 %) |

* **Scheme C data** is **608 bytes smaller** than scheme B
  (-2.6 %), and **+1B header per sprite** is **424 bytes
  smaller than scheme B** (-1.8 %).
* **Tiles** under scheme B win 3 of 4 by a handful of bytes
  thanks to no per-byte FLAG overhead in the long zero-pad
  regions.
* **Hazards** favour scheme C by +60 to +125 bytes per set —
  they're denser (more short runs, more isolated literals →
  more per-block framing overhead in B).
* Scheme C's per-sprite flag selection works universally (no
  set or sprite needs escape-the-escape).

## 2bpp → 4bpp expansion (Rich's design)

This is the per-source-byte cost that *both* schemes pay
inside their unpack loops on frame 1 of the remake's
three-frame game tick. The expansion converts each MODE 5
source byte (4 pixels × 2 bpp) into two MODE 2 output bytes
(2 pixels × 4 bpp each).

```
.init_colour_lut       ; runs ONCE per palette change
    ; A = MODE 2 byte that turns the right pixel into colour 1
    ; X = ... colour 2
    ; Y = ... colour 3
    STA &02 / STX &20 / STY &22
    ASL A : STA &04 : EOR &02 : STA &06
    TXA : ASL A : STA &40 : EOR &20 : STA &60
    TYA : ASL A : STA &44 : EOR &22 : STA &66
    ; …six more entries for the cross-colour combos…
    RTS

.convert2bpp4bpp
    ; A = MODE 5 source byte; emits two MODE 2 bytes
    TAX                   ; 2  save source
    AND #&CC              ; 2  mask the left 2 pixels' bits
    LSR A                 ; 2  shift to bits 6,5,2,1
    STA zp_sm1+1          ; 3  self-mod the LDA operand
    LDA $00 (self-mod'd)  ; 3  read the 4bpp value from the LUT
    STA (zp_dst),Y / INC  ; 6+5
    TXA                   ; 2  restore source
    AND #&33              ; 2  mask the right 2 pixels' bits
    ASL A                 ; 2
    STA zp_sm2+1          ; 3
    LDA $00 (self-mod'd)  ; 3
    STA (zp_dst),Y / INC  ; 6+5
```

The LUT lives in zero page at 16 specific addresses derived from
the bit pattern of (left-pixel-colour-bits, right-pixel-colour-
bits). Sparse — only those 16 addresses out of 256 hold useful
data, but the self-mod-and-LDA-zp pattern means we never need a
full 256-byte LUT.

**Per-source-byte cost of the bare expansion: 46 cyc.**

This is the floor — both schemes B and C inherit this. Anything
the RLE framing adds is on top.

## Decode-speed estimate with expansion folded in

Combined per-source-byte costs (RLE framing + expansion):

| Path                                  | Scheme B    | Scheme C (EOR per byte) | Scheme C (LUT pre-XORed) |
|---------------------------------------|------------:|------------------------:|-------------------------:|
| Literal source byte                   | **64 cyc**  | 66 cyc                  | **64 cyc**               |
| Run-body source byte (inside loop)    | 33 cyc      | 33 cyc                  | 33 cyc                   |
| Run setup (one-time per run)          | ~46 cyc     | ~69 cyc                 | ~67 cyc                  |

The literal-byte costs converge: scheme C with the LUT
pre-XOR optimisation (see below) matches scheme B exactly at
64 cyc. Scheme C with per-byte EOR is +2 cyc/literal — noise
on this scale of expansion overhead.

**LUT pre-XOR optimisation for scheme C**: at decode-start,
XOR every entry in the colour LUT with `FLAG_BYTE`. The
per-byte `EOR #FLAG_BYTE` then drops out — the LUT delivers
the un-XOR'd value directly. Cost: one 16-entry sweep (~ 200
cyc once per sprite) instead of 2 cyc per source byte
(amortises at sprite size ≥ 100 source bytes, which is always
true for the 128-byte sprites here).

### Per-sprite total cost (estimated)

Weighted by the literal/run ratio from the run-length histogram:

| Sprite category | Scheme B | Scheme C (LUT XOR) | C/B ratio |
|-----------------|---------:|-------------------:|----------:|
| Tile sprite     | ~5 870 cyc | ~6 000 cyc       | +2 % |
| Hazard sprite   | ~6 770 cyc | ~6 990 cyc       | +3 % |

Hazards are slightly more expensive because they have shorter
runs (avg ~6 vs ~14 for tiles), which means more run-setup
overhead. The C-vs-B difference per sprite is in the noise.

### Multi-sprite update — the real differentiator

The user's frame-1 budget is one vsync = 32 000 cyc (2 MHz BBC).
"Expanding multiple hazard sprites in their entirety each
update" means decoding only the sprites that actually need
updating that game tick (the animating ones — `hazard_anim_advance`
runs ~50 % of frames on the original engine, so typically
2-5 sprites per tick of the 14 in the pool).

| | Scheme B (per-set blob) | Scheme C (per-sprite blob) |
|---|---|---|
| Decode 1 hazard sprite | must decode whole blob to reach it (~95 k cyc) | **~7 k cyc** |
| Decode 4 hazards       | same ~95 k cyc | **~28 k cyc** (~0.9 frame) |
| Decode 7 hazards       | same ~95 k cyc | **~49 k cyc** (~1.5 frames) |
| Decode all 14          | ~95 k cyc | ~98 k cyc |

Scheme B as a **per-set blob** is a non-starter for sub-set
updates — variable-length runs make seeking impossible, so you
have to decode every preceding sprite to reach any one of them.
That's ~3 vsync frames per refresh.

Scheme B could be re-encoded as **per-sprite blobs** to get the
same random access — but then it loses the literal-block-spans-
sprites benefit, and the compressed size would creep closer to
scheme C's. We didn't measure this variant; scheme C's
per-sprite framing comes natively.

## Recommendation — scheme C

For the MODE 2 remake's frame-1 unpack with multi-sprite-per-
tick updates, **scheme C** is the right choice:

* Best compression — 16 858 B with per-sprite headers
  (vs B at 17 282 B).
* Per-sprite random access for free — decode only the sprites
  you need this tick.
* Matches scheme B on raw per-byte unpack speed (with the LUT
  pre-XOR optimisation).
* Self-contained blob per sprite simplifies the level-data
  loader (each sprite is a flag-byte plus its stream; no
  per-set length tables required).

Scheme B remains a reasonable fallback if we end up always
unpacking the entire set at once (e.g. tile catalog, which is
typically decompressed once at level load and reused). Worth
keeping the encoder in the toolset for that case.

## When we get to building it

The remake itself starts today with a fresh BeebAsm project +
infrastructure work — this RLE tool isn't the first thing to
land. When we come back to it:

1. **`tools/sprite_rle.py`** — library + CLI with both
   surviving schemes, the same column-bounded encoders that
   produced the numbers above. API:

   ```python
   # Scheme B (per-set alternating block) — kept as fallback for
   # bulk-unpack-once cases like the tile catalog at level load.
   def encode_alt(buf, n_cols, n_lines, sprite_size, min_run=4) -> bytes
   def decode_alt(enc, target_len) -> bytes

   # Scheme C (per-sprite 5+3 with XOR encoding) — the primary
   # path for per-frame sprite unpack.
   def encode_per_sprite(sprite, n_cols, n_lines, flag) -> bytes
   def decode_per_sprite(enc, flag) -> bytes
   def best_flag_per_sprite(sprite, n_cols, n_lines) -> tuple[int, int]
   ```

   CLI subcommands: `survey`, `encode`, `decode`, `test`.
   Reuse `LEVD1_LOAD` / `LEVD2_LOAD` / `SPRITE_W_COLS` etc.
   from `tools/render_level.py` rather than duplicating constants.

2. **Output blob format**:
   * Scheme B: `[LO][HI][alternating count/data...]`
   * Scheme C: per-sprite `[flag<<3][stream...]` — length is
     implicit (always 128 B for tile/hazard sprites). For a
     multi-sprite set, ship back-to-back blobs preceded by a
     small directory (sprite count + start offsets) so
     random-access decode works.

3. **Tests**: round-trip every sprite under both schemes
   byte-identical; assert no run in the encoded stream crosses
   a column or sprite boundary; reproduce the per-set / per-
   sprite table above to the byte.

## Open questions to chew on

* **Per-palette LUT pre-XOR.** The recommendation banks on
  baking FLAG_BYTE into the 2bpp→4bpp LUT once per sprite at
  decode-start. Worth confirming the LUT is in writable RAM (it
  is — it's in zero page per Rich's `init_colour_lut`), and
  that the ~200-cyc setup is small relative to the typical
  per-sprite decode (~7 000 cyc). Done — confirmed.
* **Directory format for multi-sprite scheme C blobs.** Options:
  * Fixed per-sprite stride (waste a few bytes per sprite but
    O(1) addressing — encoder pads short sprites to the maximum
    length).
  * Variable layout + a per-sprite start-offset table at the
    head of the blob (14 × 2 bytes for hazards = 28 B
    directory, exact sizes per sprite, O(1) addressing).
  * No directory, just back-to-back blobs and a per-sprite
    length byte embedded in each. Cheapest in storage but
    requires sequential scan to find sprite N.
  The variable-offset table is the natural fit — 28 B per
  hazard-set is nothing.
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
