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

The hot path inside both decoders. One MODE 5 source byte
(4 pixels × 2 bpp) becomes two MODE 2 output bytes (2 pixels
× 4 bpp), one written to each of two adjacent destination
columns.

The LUT lives in zero page at 16 sparse addresses derived
from the source byte's bit layout. The expansion does AND +
shift to produce the LUT index, then a self-modified `LDA
$00` reads the entry — cheaper than a `LDA tbl,X` because we
get to use plain ZP addressing.

### `init_colour_lut` — run once per palette change

```asm
; The colour bytes are MODE 2 byte values that set the
; RIGHT pixel of a MODE 2 byte to the desired colour.
; (For the LEFT pixel slot, we ASL them.)
;
; A = colour-1 byte    (e.g. yellow)
; X = colour-2 byte    (e.g. cyan)
; Y = colour-3 byte    (e.g. magenta)

.init_colour_lut
    STA &02                       ; right=1, left=0
    STX &20                       ; right=2, left=0
    STY &22                       ; right=3, left=0
    ASL A : STA &04 : EOR &02 : STA &06   ; right=0/1 ×  left=1
    TXA : ASL A : STA &40 : EOR &20 : STA &60   ; left=2 ×  right=0/2
    TYA : ASL A : STA &44 : EOR &22 : STA &66   ; left=3 ×  right=0/3
    TXA : EOR &04 : STA &24       ; left=1, right=2
    TXA : EOR &44 : STA &64       ; left=3, right=2
    TYA : EOR &04 : STA &26       ; left=1, right=3
    TYA : EOR &40 : STA &62       ; left=2, right=3
    LDA &02 : EOR &40 : STA &42   ; left=2, right=1
    LDA &02 : EOR &44 : STA &46   ; left=3, right=1
    RTS
```

The 15 non-zero entries cover all (left × right) colour
combinations of the three non-background colours (colour 0
stays at `&00` = 0, never written).

| addr | left px | right px |     | addr | left px | right px |
|-----:|--------:|---------:|-----|-----:|--------:|---------:|
| `&00`|       0 |        0 |     | `&40`|       2 |        0 |
| `&02`|       0 |        1 |     | `&42`|       2 |        1 |
| `&04`|       1 |        0 |     | `&44`|       3 |        0 |
| `&06`|       1 |        1 |     | `&46`|       3 |        1 |
| `&20`|       0 |        2 |     | `&60`|       2 |        2 |
| `&22`|       0 |        3 |     | `&62`|       2 |        3 |
| `&24`|       1 |        2 |     | `&64`|       3 |        2 |
| `&26`|       1 |        3 |     | `&66`|       3 |        3 |

### `convert2bpp4bpp` — the per-source-byte expansion

```asm
.convert2bpp4bpp
    ; A = MODE 5 source byte to convert
    ; X = current line index inside the destination columns (0..31)
    ; .sta_left and .sta_right are self-modified to point at the
    ; current pair of MODE 2 output columns
    STA zp_save        ; 3   save source
    AND #&CC           ; 2   mask left two pixels' bits
    LSR A              ; 2   shift to bits 6,5,2,1
    STA zp_sm1+1       ; 3   self-mod the LDA operand
.zp_sm1
    LDA $00            ; 3   ← top-byte-of-operand patched to ZP idx
.sta_left
    STA &FFFF,X        ; 5   ← self-mod target = left output column
    LDA zp_save        ; 3   restore source
    AND #&33           ; 2   mask right two pixels' bits
    ASL A              ; 2
    STA zp_sm2+1       ; 3
.zp_sm2
    LDA $00            ; 3
.sta_right
    STA &FFFF,X        ; 5   ← self-mod target = right output column
    INX                ; 2   next line
```

Cost: **38 cyc** for the in-loop body. The `STA zp_save` save/
restore costs 6 cyc total vs a `TAX/TXA` pair (4 cyc), but `X`
has to remain the line-into-column index — so the source byte
must live somewhere other than `X`.

Per column transition (= once per MODE 5 sprite column, of
which there are 4 per sprite), we self-mod the two `STA &FFFF,X`
operands to point at the next pair of MODE 2 output columns.
Cost: ~10 cyc per transition, ~40 cyc per sprite. Negligible.

## Wiring the expansion into B and C — two structural options

The expansion above is a common subroutine; the schemes differ
only in how they feed source bytes to it.

### Option α — separate literal and run code paths (FAST)

The most direct mapping. Literal source bytes flow straight
through `convert2bpp4bpp` once each. Run paths cache the
expansion result in `zp_left / zp_right` and emit it via a
tight inner loop.

This needs **four** self-modified `STA &FFFF,X` instructions
per decoder body — one pair inside the literal path, one pair
inside the run-emit loop — both pairs pointing at the same
output columns and self-modded together at column transitions.

#### Scheme B decoder (option α)

```asm
; --- Outer block-header dispatch -----------------------------
; Y = source index into the sprite's encoded stream (zp_src)
; X = line index (0..31) into the current MODE 2 column pair

.decode_block
    LDA (zp_src),Y       ; 5   literal count
    INY                  ; 2
    BEQ .read_run_count  ; 3/2   empty literal block → straight to run
    STA zp_count
.literal_loop
    LDA (zp_src),Y       ; 5
    INY                  ; 2
    STA zp_save          ; 3   ── inline expansion (left half) ──
    AND #&CC : LSR A : STA zp_sm1+1   ; 7
.zp_sm1 LDA $00          ; 3
.sta_left_lit STA &FFFF,X; 5
    LDA zp_save          ; 3   ── inline expansion (right half) ──
    AND #&33 : ASL A : STA zp_sm2+1   ; 7
.zp_sm2 LDA $00          ; 3
.sta_right_lit STA &FFFF,X ; 5
    INX                  ; 2
    DEC zp_count         ; 5
    BNE .literal_loop    ; 3
.read_run_count
    LDA (zp_src),Y       ; 5   run count
    INY                  ; 2
    BEQ .decode_block    ; 3/2   count=0 = separator, loop back
    STA zp_count
    LDA (zp_src),Y       ; 5   run value byte
    INY                  ; 2
    ; --- Expand the value byte once into zp_left / zp_right ---
    STA zp_save
    AND #&CC : LSR A : STA zp_sm1+1
.zp_sm1_run LDA $00      ; (same ZP target as .zp_sm1, redundant label only)
    STA zp_left
    LDA zp_save
    AND #&33 : ASL A : STA zp_sm2+1
.zp_sm2_run LDA $00
    STA zp_right
.run_loop
    LDA zp_left          ; 3
.sta_left_run STA &FFFF,X; 5
    LDA zp_right         ; 3
.sta_right_run STA &FFFF,X ; 5
    INX                  ; 2
    DEC zp_count         ; 5
    BNE .run_loop        ; 3
    JMP .decode_block    ; 3
```

#### Scheme C decoder (option α)

```asm
; Same Y/X conventions. flag_byte is self-modded into both EORs
; at decode-start from the sprite header byte. (Or pre-XOR the
; LUT to drop the EOR entirely — see below.)

.decode_byte
    LDA (zp_src),Y          ; 5   encoded byte
    INY                     ; 2
    CMP #8                  ; 2
    BCS .literal            ; 2/3

    ; A < 8 → run code: count = A + 3
    CLC : ADC #3             ; 4
    STA zp_count             ; 3
    LDA (zp_src),Y           ; 5   value byte
    INY                      ; 2
.run_eor EOR #00             ; 2   (self-mod to FLAG_BYTE)
    ; Expand into pair
    STA zp_save
    AND #&CC : LSR A : STA zp_sm1+1
.zp_sm1_run LDA $00
    STA zp_left
    LDA zp_save
    AND #&33 : ASL A : STA zp_sm2+1
.zp_sm2_run LDA $00
    STA zp_right
.run_loop
    LDA zp_left              ; 3
.sta_left_run STA &FFFF,X    ; 5
    LDA zp_right             ; 3
.sta_right_run STA &FFFF,X   ; 5
    INX                      ; 2
    DEC zp_count             ; 5
    BNE .run_loop            ; 3
    JMP .decode_byte         ; 3

.literal
.lit_eor EOR #00             ; 2   (self-mod to FLAG_BYTE)
    STA zp_save
    AND #&CC : LSR A : STA zp_sm1+1
.zp_sm1_lit LDA $00          ; 3
.sta_left_lit STA &FFFF,X    ; 5
    LDA zp_save
    AND #&33 : ASL A : STA zp_sm2+1
.zp_sm2_lit LDA $00          ; 3
.sta_right_lit STA &FFFF,X   ; 5
    INX                      ; 2
    JMP .decode_byte         ; 3
```

### Option β — unified through one emit loop (COMPACT, slower)

Both literal and run paths set up `zp_left / zp_right` and a
`zp_count`, then fall through into a single emit loop with
ONE pair of self-modified `STA &FFFF,X`. Literals enter the
loop with count=1.

Pros: only **two** self-mod `STA &FFFF,X` per decoder, single
emit loop. Decoder is ~25 % shorter.

Cons: every literal byte pays full pair-expansion + an extra
LDA #1 / STA zp_count + one loop-body iteration (including the
DEC zp_count / BNE that immediately falls through). Penalty
~24 cyc per literal byte.

### Cost comparison (per hazard sprite, 128 source bytes)

|                                | Option α (4 STAs) | Option β (2 STAs unified) |
|--------------------------------|------------------:|--------------------------:|
| Per literal source byte        | **55 cyc**        | 79 cyc (+24)              |
| Per run-body source byte       | 26 cyc (in loop)  | 26 cyc                    |
| Avg run-amortised (avg run 5.9)| ~36 cyc/byte      | ~36 cyc/byte              |
| Per-column self-mod overhead   | ~120 cyc/sprite   | ~60 cyc/sprite            |
| **Per hazard sprite total**    | **~6 000 cyc**    | ~7 540 cyc (+26 %)        |
| **Per tile sprite total**      | **~5 085 cyc**    | ~6 088 cyc (+20 %)        |

The unification penalty is large enough that option α is the
recommended structure. The "nice way" to unify isn't quite
nice enough — the extra count manipulation + redundant loop
iteration for single-literal-byte emits adds 20-26 % to total
per-sprite decode time, which is meaningful at the
sprites-per-frame budget the game needs.

### LUT pre-XOR for scheme C — drop the per-byte EOR

Scheme C's only per-byte cost over scheme B is the `EOR
#FLAG_BYTE` (2 cyc). It can be eliminated entirely by
pre-XORing the colour LUT at decode-start, baking FLAG into
the 16 LUT entries so we look up the correct pre-XOR'd value
directly from the encoded byte.

Cost: one 16-entry sweep, ~100 cyc per sprite. Per-byte
savings: 2 cyc × ~80 source bytes (avg) = 160 cyc. Roughly
breaks even at sprite size 50; pays off at 128 bytes. The
two `EOR #00` instructions in the scheme C decoder above
just become `NOP NOP` (or are skipped via self-mod of the
branch around them).

With the LUT pre-XOR optimisation, scheme C's per-sprite cost
matches scheme B's: **~6 000 cyc per hazard, ~5 000 per tile**.

## Multi-sprite update — random access

Both schemes produce variable-length per-sprite blobs. To seek
to sprite N out of M, both need a per-sprite-offset directory
at the head of the multi-sprite blob, OR a fixed-stride layout
with padding.

The natural format for either scheme:

```
+0..(2M-1):  directory — M × 2-byte LO/HI of start offset
+(2M)..:     concatenated per-sprite blobs
              scheme B: [LO][HI][alternating count/data...]
              scheme C: [flag][stream...] (length implicit at 128)
```

So scheme B and scheme C support per-sprite random access
equivalently. The earlier "scheme B has to decode the whole
blob" framing was wrong — it only applies if we ship without
a directory, which would be a silly choice given we WANT
random access.

Per-sprite decode is then ~6 k cyc for hazards, ~5 k for tiles
under either scheme. The remake's per-tick budget (one vsync =
32 000 cyc) handles **5 hazard sprite re-unpacks per tick**
comfortably (~30 k cyc).

## Recommendation — scheme C with option α and LUT pre-XOR

* **Compression**: scheme C wins by 424 B vs scheme B (16 858 B
  vs 17 282 B with per-sprite headers, both with directory).
* **Decode speed**: scheme C + LUT pre-XOR matches scheme B
  exactly (~6 000 cyc per hazard sprite).
* **Decoder code size**: scheme C's per-byte branch (`CMP #8 /
  BCS`) is comparable to scheme B's per-block dispatch — both
  in the ~50-70 byte range with option α inlined.
* **Random access**: equivalent (both need the directory).

Recommendation lands on **scheme C with option α** (separate
literal/run paths, 4 self-mod STAs per column transition) and
the LUT pre-XOR trick. Scheme B is a reasonable fallback for
bulk-unpack-once cases (tile catalog at level load) where
decoder simplicity might matter more than the 424 B compression
gap.

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
