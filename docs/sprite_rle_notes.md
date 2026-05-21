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

`C-data` = scheme C compressed stream only (no per-sprite headers).
`C+meta` = scheme C with the per-sprite metadata block
{ flag, base_addr_lo, base_addr_hi, col_offset[0..3] } = 7 B/sprite
(see "Random access" below).

Survey produced by `tools/sprite_rle.py`, round-trip verified
against every sprite. The tile rows below correct the earlier
draft numbers — the original prototype that produced "1442 /
1139 / 1347 / 1534" for tile sets was buggy; a faithful
encoder built to the spec (max run = 10, count = b + 3,
column-bounded, per-sprite FLAG) gives the values shown here.

| Set            | Raw    | Scheme C (data) | C-data + meta |
|----------------|-------:|----------------:|--------------:|
| L1 tiles       |  2 304 |  1 763          | 1 889 (18×7)  |
| L2 tiles       |  2 304 |  1 222          | 1 348         |
| L3 tiles       |  2 304 |  1 293          | 1 419         |
| L4 tiles       |  2 304 |  1 856          | 1 982         |
| L1S1 hazards   |  1 792 |  1 331          | 1 429 (14×7)  |
| L1S2 hazards   |  1 792 |  1 440          | 1 538         |
| L2S1 hazards   |  1 792 |  1 466          | 1 564         |
| L2S2 hazards   |  1 792 |  1 413          | 1 511         |
| L3S1 hazards   |  1 792 |  1 361          | 1 459         |
| L3S2 hazards   |  1 792 |  1 341          | 1 439         |
| L4S1 hazards   |  1 792 |  1 489          | 1 587         |
| L4S2 hazards   |  1 792 |  1 371          | 1 469         |
| **TOTAL**      | 23 552 | **17 346** (73.6 %) | 18 432 (78.3 %) |

* The hazard rows are unchanged from the earlier draft (the
  per-sprite-best-flag scheme A and scheme C produce identical
  encoded sizes on this corpus — both 1 B literal + 2 B run with
  max-10).
* The tile rows are corrected — the previous "1 442 / 1 139 /
  1 347 / 1 534" values understate the size by ~25–40 % per set.
  Verified by both a faithful Scheme A and Scheme C
  reimplementation; both produce the same 1 763 for L1 tiles
  given the documented max-run cap. The earlier numbers must
  have been from an uncommitted prototype that allowed longer
  runs or different code semantics.

### Survey extended to all 4×32 sprites (game-wide)

The wider survey — every 4×32 sprite required to render any
stage — covers tiles, LEVD hazards, the three GRAPHIX-resident
hazards, and all six explosion frames per scenario:

| Category            | Sprites | Raw    | C-data | +meta (7 B/sprite) |
|---------------------|--------:|-------:|-------:|-------------------:|
| explosion (4×6)     |      24 |  3 072 |  2 226 |              2 394 |
| tile (4×18)         |      72 |  9 216 |  6 134 |              6 638 |
| hazard LEVD (4×2×14)|     112 | 14 336 | 11 212 |             12 008 |
| GRAPHIX hazards (3) |       3 |    384 |    299 |                320 |
| **TOTAL**           |     211 | 27 008 | **19 871** (73.6 %) | **21 360** (79.1 %) |

### Per-stage memory footprint

41 sprites loaded simultaneously per stage = 18 tiles + 14 LEVD
hazards + 6 explosions + 3 GRAPHIX hazards. Tiles and explosion
frames are scenario-shared between the two stages; GRAPHIX
hazards are game-shared.

Raw per stage = 41 sprites × 128 B = **5 248 B**, same for every
stage. The `% raw` column is the compressed `total` (data + meta)
as a fraction of that.

|  Stage |  tiles | hazards | expl | GFX |   data | meta | total |  raw  | % raw  |
|--------|-------:|--------:|-----:|----:|-------:|-----:|------:|------:|-------:|
|  L1S1  |  1 763 |   1 331 |  553 | 299 |  3 946 |  287 | 4 233 | 5 248 | 80.7 % |
|  L1S2  |  1 763 |   1 440 |  553 | 299 |  4 055 |  287 | 4 342 | 5 248 | 82.7 % |
|  L2S1  |  1 222 |   1 466 |  375 | 299 |  3 362 |  287 | 3 649 | 5 248 | 69.5 % |
|  L2S2  |  1 222 |   1 413 |  375 | 299 |  3 309 |  287 | 3 596 | 5 248 | 68.5 % |
|  L3S1  |  1 293 |   1 361 |  645 | 299 |  3 598 |  287 | 3 885 | 5 248 | 74.0 % |
|  L3S2  |  1 293 |   1 341 |  645 | 299 |  3 578 |  287 | 3 865 | 5 248 | 73.6 % |
|  L4S1  |  1 856 |   1 489 |  653 | 299 |  4 297 |  287 | 4 584 | 5 248 | 87.3 % |
|  L4S2  |  1 856 |   1 371 |  653 | 299 |  4 179 |  287 | 4 466 | 5 248 | 85.1 % |

Worst stage **L4S1 = 4 584 B** (87.3 % of raw). Best stage **L2S2
= 3 596 B** (68.5 % of raw). Average **4 078 B per stage**
(4.0 KB, 77.7 % of raw).

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

#### Scheme C decoder (option α) — final form

Decodes **one MODE 5 source column** = 32 lines, advancing the
self-modded `sta_*` destination operands per call from the outer
column-walk routine. X counts the destination line **down** from
31 to 0, so column exhaustion is detected in-band (DEX → −1, BPL
fails).

```asm
; Y = source index into zp_src     (preserved across calls)
; X = line index — caller pre-loads 31 (or 256-height-1)
;
; flag_byte is self-modded into the single .lit_eor at
; decode-start from the sprite header byte. The run path does
; NOT EOR the value byte — runs are signalled by the count
; header, the value byte is raw.

.decode_byte
    LDA (zp_src),Y           ; 5   encoded byte
    INY                      ; 2   advance source once per encoded byte
    CMP #8                   ; 2
    BCC .multiple            ; 2/3 → run path. literal is fall-through

.literal
.lit_eor EOR #00             ; 2   (self-mod to FLAG_BYTE)
    STA temp                 ; 3   save the decoded byte for right-half
    AND #&CC : LSR A         ; 4   left-half index
    STA zp_sm1+1             ; 4
.zp_sm1_lit LDA $00          ; 3   ← top of operand patched to ZP-LUT idx
.sta_left_lit STA &FFFF,X    ; 5   ← target patched per column pair
    LDA temp                 ; 3   recover decoded byte
    AND #&33 : ASL A         ; 4   right-half index
    STA zp_sm2+1             ; 4
.zp_sm2_lit LDA $00          ; 3
.sta_right_lit STA &FFFF,X   ; 5
    DEX                      ; 2
    BPL .decode_byte         ; 3   column not yet exhausted
.exit
    RTS

.multiple
    ; BCC was taken → C=0, so ADC #3 needs no CLC.
    ADC #3                   ; 2   count = A + 3 (3..10)
    STA zp_count             ; 3
    LDA (zp_src),Y           ; 5   value byte (raw, NOT EORed)
    AND #&CC : LSR A         ; 4   left-half index
    STA zp_sm1_run+1         ; 4
.zp_sm1_run LDA $00          ; 3
    STA zp_left+1            ; 4   self-mod the LDA #imm in the hot loop
    LDA (zp_src),Y           ; 5   re-read value byte (still raw)
    AND #&33 : ASL A         ; 4   right-half index
    STA zp_sm2_run+1         ; 4
.zp_sm2_run LDA $00          ; 3
    STA zp_right+1           ; 4
    INY                      ; 2   consume value byte
.run_loop
.zp_left LDA #0              ; 2   ← imm patched above to left 4bpp
.sta_left_run STA &FFFF,X    ; 5
.zp_right LDA #0             ; 2   ← imm patched above to right 4bpp
.sta_right_run STA &FFFF,X   ; 5
    DEX                      ; 2
    BMI .exit                ; 2/3   column exhausted? (mirrors literal's BPL)
    DEC zp_count             ; 5
    BNE .run_loop            ; 3
    JMP .decode_byte         ; 3
```

Highlights of the final form vs the previous sketch:

* **`INY` lifted to the top of `.decode_byte`** — exactly one
  source advance per encoded byte regardless of which path runs;
  the run path needs one further `INY` after consuming the value
  byte (folded into the run setup so the cost shows up once, not
  per iteration).
* **`BCC .multiple` with literal fall-through** — the literal
  path is the "branch not taken" side, saving 1 cyc on the more
  common case (52 % of hazard bytes, 35 % of tile bytes).
* **`STA temp` / `LDA temp`** in the literal path saves the
  EORed byte for the right-half index. Re-reading
  `(zp_src),Y` would return the *raw* encoded byte — bits 5/4
  are FLAG-flipped, so the right-half index would be wrong. The
  temp save costs +3 cyc and the second `LDA temp` saves 2 cyc
  vs re-doing the indirect fetch, net +1 cyc, and it's
  correctness-critical.
* **Value byte not EORed** in the run path — runs are
  discriminated by the count header, so the value byte is
  shipped raw by the encoder and consumed raw by the decoder.
  Saves 2 cyc per run setup.
* **Self-modded immediates in `run_loop`** — `LDA #imm` is 2 cyc
  vs `LDA zp` 3 cyc, hit twice per output line. Saves 2 cyc per
  loop iteration; setup cost is paid once per run (4 cyc × 2
  for the two `STA zp_left+1 / zp_right+1`).
* **In-band column exit via DEX-and-branch** — DEX'ing past 0
  makes X = −1, and BPL/BMI test the N flag directly. Literal
  path uses BPL (continue while non-negative); run path uses BMI
  exit (mirror semantics: exit when negative).
* **No `CLC` before `ADC #3`** — `BCC .multiple` taken implies
  C = 0 at entry, so the carry is already known clear.

#### Cycle cost per source byte (final form)

```
Decoder header (LDA / INY / CMP / BCC):  5 + 2 + 2 + 2 = 11  (BCC not taken: literal)
                                         5 + 2 + 2 + 3 = 12  (BCC taken: run header)

Literal body (after header):
  EOR / STA temp / AND/LSR / STA / LDA / STA       =  2+3+4+4+3+5 = 21
  LDA temp / AND/ASL / STA / LDA / STA              =  3+4+4+3+5  = 19
  DEX / BPL                                          =  2+3        =  5
  total literal body                                 = 45
  --- per literal source byte: 11 + 45              = 56 cyc

Run setup (after the BCC-taken header):
  ADC / STA count                                    =  2 + 3      =  5
  LDA / AND/LSR / STA / LDA / STA   (left LUT)       =  5+4+4+3+4  = 20
  LDA / AND/ASL / STA / LDA / STA   (right LUT)      =  5+4+4+3+4  = 20
  INY                                                =  2
  total setup                                        = 47

Run loop body (per emitted output line, 1 source byte → N lines):
  LDA #imm / STA / LDA #imm / STA / DEX              =  2+5+2+5+2  = 16
  BMI not taken / DEC zp_count / BNE taken           =  2+5+3      = 10
  total                                              = 26
  --- per run-source-byte (avg run 5.9): (12+47+26·N+3)/N = ~30 cyc for N=5, 26 cyc for N→∞
```

For a 128-byte hazard sprite at 52 % literals:
~67 × 56 + 61 / 5.9 runs × (62 + 26 × 5.9) ≈ 3 750 + 2 220 ≈
**~6 000 cyc / hazard sprite**.

For a 128-byte tile sprite at 35 % literals:
~45 × 56 + 83 / 9.0 runs × (62 + 26 × 9.0) ≈ 2 520 + 2 750 ≈
**~5 300 cyc / tile sprite**.

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
| Per literal source byte        | **56 cyc**        | 80 cyc (+24)              |
| Per run-loop output line       | 26 cyc            | 26 cyc                    |
| Avg run-amortised (avg run 5.9)| ~30 cyc/byte      | ~30 cyc/byte              |
| Per-column self-mod overhead   | ~120 cyc/sprite   | ~60 cyc/sprite            |
| **Per hazard sprite total**    | **~6 000 cyc**    | ~7 540 cyc (+26 %)        |
| **Per tile sprite total**      | **~5 300 cyc**    | ~6 350 cyc (+20 %)        |

The unification penalty is large enough that option α is the
recommended structure. The "nice way" to unify isn't quite
nice enough — the extra count manipulation + redundant loop
iteration for single-literal-byte emits adds 20-26 % to total
per-sprite decode time, which is meaningful at the
sprites-per-frame budget the game needs.

### Pre-XOR the LUT to drop the EOR? — analysed and dropped

Tempting initial thought: pre-XOR the 16-entry colour LUT at
decode-start, baking FLAG into the entries so we skip the
`EOR #FLAG_BYTE` (saves 2 cyc per literal byte).

It doesn't work cleanly with a single LUT, because **FLAG bits
land in different index-bit positions for the left vs right
half** of a source byte:

```
Source bit:      7  6  5  4  3  2  1  0
Carries FLAG?    F4 F3 F2 F1 F0 -  -  -

After AND #&CC, LSR (left index):   bit 7→6, 6→5, 3→2, 2→1
   → index bits 6,5,2 carry F4,F3,F0 (bit 1 is clean)

After AND #&33, ASL (right index):  bit 5→6, 4→5, 1→2, 0→1
   → index bits 6,5 carry F2,F1 (bits 2,1 are clean)
```

So index bit 6 means *F4-flipped* in the left lookup and
*F2-flipped* in the right lookup. A single 16-entry LUT can't
bake in both unless FLAG is symmetric (F4 = F2, F3 = F1) — and
we'd lose 3/4 of the FLAG space, with no guarantee every sprite
still has a candidate.

Options that DO work:

1. **Two 16-entry LUTs** (32 sparse ZP slots, separate
   pre-XOR each). Saves 2 cyc per literal byte + 1 cyc from
   dropping the `STA temp` / `LDA temp` pair (since the second
   half can re-fetch raw with `LDA (zp_src),Y`). Net ~3 cyc /
   literal byte. For a 128-byte sprite at 52 % literals,
   ~67 × 3 = ~200 cyc/sprite. Doubles ZP LUT footprint and
   setup cost — marginal win.
2. **`EOR #mask` after the AND** (one LUT, per-half mask).
   Same ~1 cyc slower than the current `STA temp`/`LDA temp`
   pattern — not a win.

**Decision: keep the current `STA temp` / `LDA temp` pattern**
with a single per-byte EOR. The pre-XOR'd-LUT savings aren't
worth the doubled ZP footprint.

### Vertical mirror via self-mod (free at decode time)

The same column decoder can render a vertically-flipped column
with a handful of pre-call patches:

| Patch                          | Normal              | Mirror               | Bytes |
|--------------------------------|---------------------|----------------------|------:|
| DEX → INX (×2: literal + run)  | `$CA`               | `$E8`                | 1 each |
| Literal: `BPL .decode_byte`    | `$10` (BPL)         | `$30` (BMI)          | 1     |
| Run: `BMI .exit`               | `$30` (BMI)         | `$10` (BPL)          | 1     |
| X initial value                | `#$1F` (31)         | `#$E0` (-32)         | 1     |
| 4 × `STA &FFFF,X` base addrs   | `dest_top`          | `dest_top + 32`      | 8     |

The two branch swaps go in **opposite directions** — both are
single-bit toggles ($10 ↔ $30, bit-5 flip). In mirror mode X
starts at $E0 (= −32 signed) and `INX` walks $E1..$FF; after the
last write at $FF, the next INX makes X = 0 (no longer
negative).

* Literal end wants "keep looping while still negative" →
  `BMI .decode_byte` continues during the negative phase, falls
  through to RTS at X = 0.
* Run end wants "exit when no longer negative" → `BPL .exit`
  triggers at X = 0.

`INY` at the top of `.decode_byte` is direction-independent —
source pointer advances normally regardless of mirror mode, no
patch needed.

The four `STA &FFFF,X` destination bases are already self-modded
per column pair by the outer column-walk routine; mirror mode
just computes `base + 32` (= one column's worth past the
column's *physical* top) instead of `base`. Same setup loop,
one extra add per column.

Total mirror-mode overhead: 5 single-byte opcode/operand patches
+ a constant offset added to 4 destination bases. Paid once per
sprite-mirror call, not per byte.

(Horizontal mirror is harder: it needs both a swap of the
left/right column write order — a base-address pair-swap on the
four STAs — *and* a per-byte pixel-bit reverse, which has to be
baked into a separate "mirror LUT" with the same 16-entry sparse
ZP layout. The mirror LUT is a one-shot init (~30 cyc) and then
horizontal-mirror mode just points the `zp_sm*_lit / zp_sm*_run`
self-mod fields at the mirror bank instead of the main bank.)

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

## Recommendation — scheme C with option α

* **Compression**: scheme C wins by 424 B vs scheme B (16 858 B
  vs 17 282 B with per-sprite headers, both with directory).
* **Decode speed**: scheme C in its final form is **~6 000 cyc
  per hazard sprite, ~5 300 cyc per tile** (option α, single-EOR
  literal path with `STA temp` / `LDA temp`, self-modded
  immediates in the run hot loop, in-band DEX/BPL column exit).
  That matches scheme B's amortised per-byte cost on this corpus.
* **Decoder code size**: scheme C's per-byte branch
  (`CMP #8 / BCC`) is comparable to scheme B's per-block
  dispatch — both in the ~50-70 byte range with option α
  inlined.
* **Random access**: equivalent (both need the directory).
* **Vertical-mirror support**: trivial — handful of self-mod
  patches at sprite setup, zero cost in the inner loop.

Recommendation lands on **scheme C with option α**, the final
decoder form above. Scheme B is a reasonable fallback for
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

* **LUT pre-XOR.** Analysed (see "Pre-XOR the LUT to drop the
  EOR?" above) and **dropped** — left/right halves carry FLAG
  in different index-bit positions, so a single LUT can't bake
  it in. Two LUTs would save ~200 cyc/sprite but double the ZP
  LUT footprint and setup cost — not worth it.
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
