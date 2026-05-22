#!/usr/bin/env python3
"""Sprite RLE — scheme C (per-sprite 5+3 with XOR encoding).

Scheme C, per docs/sprite_rle_notes.md:
* Each 128-byte 4x32 sprite picks its own 5-bit FLAG such that no
  byte in the sprite has top-5-bits = FLAG.
* The encoded stream consists of bytes b where:
    b < 8   →  run code, count = b + 3 (= 3..10), next byte is the
               run value (raw).
    b >= 8  →  literal, emit (b XOR FLAG_BYTE) once.
  (FLAG_BYTE = FLAG << 3.)
* Runs do NOT cross sprite-column (32-byte) or sprite (128-byte)
  boundaries.

Per-sprite blob: [FLAG_BYTE][encoded stream...]. Uncompressed length
is implicit (always 128 B for the 4x32 sprites).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_level import (
    LEVD1_LOAD, LEVD2_LOAD, GRAPHIX_LOAD,
    LEVD1_EXPLOSION_OFF, LEVD1_EXPLOSION_COUNT,
    TILE_CATALOG_OFF, TILE_COUNT,
    LEVD2_HAZARD_OFF, LEVD2_HAZARD_COUNT,
    HAZARD_A_OFF, HAZARD_B_OFF,
    SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
)


SPRITE_COL_BYTES = SPRITE_H_LINES   # 32 — one MODE 5 column
assert SPRITE_W_COLS * SPRITE_COL_BYTES == SPRITE_SIZE


# ---------------------------------------------------------------------------
# Scheme C encoder / decoder
# ---------------------------------------------------------------------------

def pick_flag(sprite: bytes) -> int:
    """Pick a 5-bit FLAG such that no source byte has top-5-bits = FLAG.

    Returns the first such FLAG in 0..31. Raises ValueError if the
    sprite uses all 32 possible 5-bit prefixes (which empirically never
    happens — every 128-byte sprite in the survey has at least 3 free
    prefixes)."""
    used = {b >> 3 for b in sprite}
    for f in range(32):
        if f not in used:
            return f
    raise ValueError("sprite uses all 32 possible 5-bit prefixes — no FLAG available")


def encode_column(col: bytes, flag_byte: int) -> bytes:
    """Encode one 32-byte column with scheme C. Runs are 3..10 bytes,
    bounded to the column."""
    out = bytearray()
    i = 0
    n = len(col)
    while i < n:
        # find current run length (capped at 10, bounded by column end)
        j = i
        while j < n and j - i < 10 and col[j] == col[i]:
            j += 1
        run_len = j - i
        if run_len >= 3:
            # run code: count = run_len, encode as (run_len - 3) in 0..7
            out.append(run_len - 3)
            out.append(col[i])
            i = j
        else:
            # literal: emit one byte XORed with flag_byte
            out.append(col[i] ^ flag_byte)
            i += 1
    return bytes(out)


def encode_sprite(sprite: bytes, w_cols: int = SPRITE_W_COLS,
                  h_lines: int = SPRITE_H_LINES,
                  flag: int | None = None
                  ) -> tuple[int, bytes, list[int]]:
    """Encode a column-major sprite of shape w_cols x h_lines. Returns
    (flag, encoded_stream, col_offsets) — stream does NOT include the
    leading flag header byte. col_offsets[c] = offset within
    encoded_stream where column c's data starts (col_offsets[0] is
    always 0). Encoding is per-column (no runs cross column
    boundaries)."""
    assert len(sprite) == w_cols * h_lines, (len(sprite), w_cols, h_lines)
    if flag is None:
        flag = pick_flag(sprite)
    flag_byte = flag << 3
    out = bytearray()
    col_offsets = []
    for c in range(w_cols):
        col_offsets.append(len(out))
        col = sprite[c * h_lines:(c + 1) * h_lines]
        out.extend(encode_column(col, flag_byte))
    return flag, bytes(out), col_offsets


def trim_borders(sprite: bytes, w_cols: int, h_lines: int
                 ) -> tuple[bytes, int, int, tuple[int, int, int, int]]:
    """Strip fully-zero outer columns and rows from a column-major sprite.
    Returns (trimmed_bytes, w_new, h_new, (left, right, top, bottom)) where
    (left, right, top, bottom) is the number of cols/rows stripped from
    each edge. The trimmed sprite is the inner rectangle, still
    column-major. An all-zero sprite returns (b'', 0, 0, (w, 0, h, 0))."""
    assert len(sprite) == w_cols * h_lines

    def col_blank(c):
        return all(sprite[c * h_lines + r] == 0 for r in range(h_lines))

    left = 0
    while left < w_cols and col_blank(left):
        left += 1
    if left == w_cols:
        return b'', 0, 0, (w_cols, 0, h_lines, 0)
    right = w_cols
    while right > left and col_blank(right - 1):
        right -= 1

    def row_blank(r):
        return all(sprite[c * h_lines + r] == 0 for c in range(left, right))

    top = 0
    while top < h_lines and row_blank(top):
        top += 1
    bottom = h_lines
    while bottom > top and row_blank(bottom - 1):
        bottom -= 1

    w_new = right - left
    h_new = bottom - top
    out = bytearray()
    for c in range(left, right):
        out.extend(sprite[c * h_lines + top:c * h_lines + bottom])
    return bytes(out), w_new, h_new, (left, w_cols - right, top, h_lines - bottom)


def decode_column(stream: bytes, flag_byte: int, target_len: int = SPRITE_COL_BYTES
                  ) -> tuple[bytes, int]:
    """Decode one column from `stream`. Returns (decoded, bytes_consumed)."""
    out = bytearray()
    i = 0
    while len(out) < target_len:
        b = stream[i]
        i += 1
        if b < 8:
            count = b + 3
            value = stream[i]      # raw — encoder ships raw
            i += 1
            out.extend([value] * count)
        else:
            out.append(b ^ flag_byte)
    if len(out) != target_len:
        raise ValueError(f"column decode overshot: got {len(out)} of {target_len}")
    return bytes(out), i


def decode_sprite(flag: int, stream: bytes, n_cols: int = SPRITE_W_COLS,
                  col_bytes: int = SPRITE_COL_BYTES) -> bytes:
    flag_byte = flag << 3
    out = bytearray()
    i = 0
    for _ in range(n_cols):
        col, consumed = decode_column(stream[i:], flag_byte, col_bytes)
        out.extend(col)
        i += consumed
    return bytes(out)


# Per-sprite metadata layout (Rich's spec, updated 2026-05-22).
#
# Source bytes are ALWAYS 2bpp MODE 5 — both the RLE and the raw paths
# feed every source byte through the 2bpp->4bpp LUT in frame 1 to
# produce the 4bpp MODE 2 unpacked buffer. RLE just skips the per-byte
# "is this a run code" branch + the EOR. So both paths need the
# palette bytes to set up the LUT.
#
# Metadata is stored in SEPARATE per-type tables indexed by sprite id
# (tile_number / hazard_number / enemy_frame / etc.).
#
# Trim + RLE path — per sprite:
#   * flag byte               1 B    (XOR byte for the RLE literal path)
#   * base_addr               2 B    (where this sprite's compressed
#                                     stream lives)
#   * column-start offsets    W B    (W = trimmed col count; one
#                                     parallel table per column
#                                     position; sprites of width >= N
#                                     populate col_offset_table[N].)
#   * 3 palette colour bytes  3 B    ({A, X, Y} for init_colour_lut;
#                                     each sprite picks its own 3
#                                     non-background colours, also
#                                     gives free white-flash-on-hit
#                                     variants via palette swap.)
# = 6 + W bytes/sprite.
#
# Trim (or raw), no RLE — per sprite:
#   * base_addr               2 B
#   * 3 palette colour bytes  3 B
# = 5 bytes/sprite. No flag, no col_offsets (column stride = h_trim,
# known from the per-type shape table).
SPRITE_META_FIXED = 1 + 2 + 3      # RLE path: flag + base_addr + palette
SPRITE_META_NO_RLE = 0 + 2 + 3     # raw / trim-only path: base_addr + palette
def sprite_meta_bytes(w_cols: int) -> int:
    return SPRITE_META_FIXED + w_cols

SPRITE_META_BYTES = sprite_meta_bytes(SPRITE_W_COLS)   # = 10 for 4x32


# ---------------------------------------------------------------------------
# Sprite-source enumeration
# ---------------------------------------------------------------------------

def load_files():
    """Returns dict {('LEVD1', level): bytes, ('LEVD2', level): bytes,
    ('LEVD3', level): bytes, 'GRAPHIX': bytes}."""
    out = {}
    for level in (1, 2, 3, 4):
        out[('LEVD1', level)] = open(f'extracted/{level}.LEVD1', 'rb').read()
        out[('LEVD2', level)] = open(f'extracted/{level}.LEVD2', 'rb').read()
        out[('LEVD3', level)] = open(f'extracted/{level}.LEVD3', 'rb').read()
    out['GRAPHIX'] = open('extracted/$.GRAPHIX', 'rb').read()
    return out


# Per the docs:
#   * Tiles: LEVD1 +TILE_CATALOG_OFF, 18 × 128 B per scenario.
#   * Stage-1 hazards: LEVD2 +LEVD2_HAZARD_OFF, 14 × 128 B per scenario.
#   * Stage-2 hazards: LEVD3 same offsets (LEVD3 overlays LEVD2 hazards).
#   * Explosions 0..3: LEVD1 +LEVD1_EXPLOSION_OFF, 4 × 128 B per scenario.
#   * Explosions 4..5: LEVD2 +HAZARD_A_OFF / +HAZARD_B_OFF, 2 × 128 B
#     per scenario.
#   * GRAPHIX hazard slots: &3700, &3780, &4360 — 3 × 128 B, shared.
GRAPHIX_HAZARD_ADDRS = (0x3700, 0x3780, 0x4360)


def enumerate_sprites(files):
    """Yields (category, label, bytes_128) for every 4x32 sprite in the
    "all tiles + all hazards (LEVD + GRAPHIX) + all explosions"
    survey scope. 128 B each."""
    for level in (1, 2, 3, 4):
        levd1 = files[('LEVD1', level)]
        levd2 = files[('LEVD2', level)]
        levd3 = files[('LEVD3', level)]

        # explosion frames 0..3
        for fr in range(LEVD1_EXPLOSION_COUNT):
            off = LEVD1_EXPLOSION_OFF + fr * SPRITE_SIZE
            yield ('explosion', f'L{level}_explosion_{fr:02d}',
                   levd1[off:off + SPRITE_SIZE])

        # explosion frames 4, 5
        yield ('explosion', f'L{level}_explosion_04',
               levd2[HAZARD_A_OFF:HAZARD_A_OFF + SPRITE_SIZE])
        yield ('explosion', f'L{level}_explosion_05',
               levd2[HAZARD_B_OFF:HAZARD_B_OFF + SPRITE_SIZE])

        # tile catalog
        for tid in range(TILE_COUNT):
            off = TILE_CATALOG_OFF + tid * SPRITE_SIZE
            yield ('tile', f'L{level}_tile_{tid:02d}',
                   levd1[off:off + SPRITE_SIZE])

        # stage-1 hazards (LEVD2)
        for hid in range(LEVD2_HAZARD_COUNT):
            off = LEVD2_HAZARD_OFF + hid * SPRITE_SIZE
            yield ('hazard', f'L{level}S1_hazard_{hid:02d}',
                   levd2[off:off + SPRITE_SIZE])

        # stage-2 hazards (LEVD3 overlays the same offsets)
        for hid in range(LEVD2_HAZARD_COUNT):
            off = LEVD2_HAZARD_OFF + hid * SPRITE_SIZE
            yield ('hazard', f'L{level}S2_hazard_{hid:02d}',
                   levd3[off:off + SPRITE_SIZE])

    # GRAPHIX hazard sprites — shared across all scenarios, count once
    graphix = files['GRAPHIX']
    for addr in GRAPHIX_HAZARD_ADDRS:
        off = addr - GRAPHIX_LOAD
        yield ('graphix_hazard', f'graphix_&{addr:04X}',
               graphix[off:off + SPRITE_SIZE])


# Variable-shape sprite categories (non-4x32):
#   * Player ship: LEVD1 +PLAYER_OFF, 6×22 (132 B) per scenario.
#   * Small flying enemy + hit frames: LEVD1, 4×24 (96 B each) per
#     scenario. 4 normal frames + 3 hit frames; adjacent frames share
#     a column on disk, but each frame is treated as its own sprite.
#   * Engine flame: GRAPHIX &3B00/&3B40/&3B80, 8×8 (64 B each).
#   * Pickups: GRAPHIX &4060/&4090/&40C0/&4750, 2×16 (32 B each).
PLAYER_W_COLS  = 6
PLAYER_H_LINES = 22
PLAYER_SIZE    = PLAYER_W_COLS * PLAYER_H_LINES  # 132 B

ENEMY_W_COLS_  = 4
ENEMY_H_LINES_ = 24
ENEMY_SIZE_    = ENEMY_W_COLS_ * ENEMY_H_LINES_  # 96 B

# Per-scenario LEVD1 offsets for the 4 enemy + 3 enemy-hit frames
# (matches render_level.py's ENEMY_ANIM_OFFS — kept inline so the RLE
# tool can run standalone).
LEVD1_PLAYER_OFF = 0x480
ENEMY_FRAME_OFFS = [
    (0x220, 'enemy_hit_01'),
    (0x268, 'enemy_hit_02'),
    (0x2B0, 'enemy_hit_03'),
    (0x300, 'enemy_00'),
    (0x348, 'enemy_01'),
    (0x3B0, 'enemy_02'),
    (0x410, 'enemy_03'),
]

FLAME_W_COLS  = 8
FLAME_H_LINES = 8
FLAME_SIZE    = FLAME_W_COLS * FLAME_H_LINES   # 64 B
FLAME_ADDRS   = (0x3B00, 0x3B40, 0x3B80)

PICKUP_W_COLS  = 2
PICKUP_H_LINES = 16
PICKUP_SIZE    = PICKUP_W_COLS * PICKUP_H_LINES  # 32 B
PICKUP_ADDRS_LABELS = [
    (0x4060, 'pickup_red'),
    (0x4090, 'pickup_yellow'),
    (0x40C0, 'pickup_checker'),
    (0x4750, 'pickup_white'),
]


def enumerate_other_sprites(files):
    """Yields (category, label, w_cols, h_lines, bytes) for sprites
    outside the 4x32 main survey: player, small enemies, enemy-hit,
    engine flame, pickups."""
    # Per-scenario (LEVD1): player, enemy, enemy_hit
    for level in (1, 2, 3, 4):
        levd1 = files[('LEVD1', level)]
        # player
        yield ('player', f'L{level}_player_sprite',
               PLAYER_W_COLS, PLAYER_H_LINES,
               levd1[LEVD1_PLAYER_OFF:LEVD1_PLAYER_OFF + PLAYER_SIZE])
        # 7 enemy / enemy_hit frames
        for off, lab in ENEMY_FRAME_OFFS:
            cat = 'enemy_hit' if lab.startswith('enemy_hit') else 'enemy'
            yield (cat, f'L{level}_{lab}',
                   ENEMY_W_COLS_, ENEMY_H_LINES_,
                   levd1[off:off + ENEMY_SIZE_])

    # Game-wide (GRAPHIX): flames, pickups. The 3 GRAPHIX hazards
    # (slots 15/16/19) are stationary plotted obstacles — they stay at
    # the 16x32 (4x32 byte) plot envelope so their position remains
    # consistent, so they live in the main 4x32 survey only and are
    # NOT trimmed here. (Trim is only applied to animating / moving
    # sprites where saving border bytes is worth the offset bookkeeping.)
    graphix = files['GRAPHIX']
    for addr in FLAME_ADDRS:
        off = addr - GRAPHIX_LOAD
        yield ('flame', f'flame_&{addr:04X}',
               FLAME_W_COLS, FLAME_H_LINES,
               graphix[off:off + FLAME_SIZE])
    for addr, lab in PICKUP_ADDRS_LABELS:
        off = addr - GRAPHIX_LOAD
        yield ('pickup', f'{lab}_&{addr:04X}',
               PICKUP_W_COLS, PICKUP_H_LINES,
               graphix[off:off + PICKUP_SIZE])


def survey_other():
    """Survey the variable-shape sprites with border-trimming."""
    files = load_files()
    rows = []
    for cat, label, w, h, data in enumerate_other_sprites(files):
        raw = len(data)
        trimmed, w_t, h_t, (L, R, T, B) = trim_borders(data, w, h)
        trim_raw = len(trimmed)
        if trim_raw == 0:
            enc_len = 0
        else:
            flag, enc, _ = encode_sprite(trimmed, w_t, h_t)
            # round-trip
            rt = decode_sprite(flag, enc, w_t, h_t)
            assert rt == trimmed, f"round-trip FAILED for {label}"
            enc_len = len(enc)
        rows.append((cat, label, w, h, raw,
                     w_t, h_t, trim_raw, enc_len, (L, R, T, B)))

    # ---- per-sprite table
    print("=" * 96)
    print("Sprite RLE — variable-shape sprites with border trim")
    print("Per-sprite meta = { flag + base_addr + col_offsets[W_trim] "
          "+ palette[3] } = 6 + W_trim bytes")
    print("=" * 96)
    print(f"\n{'Category':<14} {'Label':<24} "
          f"{'shape':>8} {'raw':>5} {'trim':>8} {'t-raw':>6} "
          f"{'enc':>4} {'meta':>5} {'tot':>5} {'%raw':>6}")
    print("-" * 96)
    for cat, lab, w, h, raw, wt, ht, traw, enc, (L, R, T, B) in rows:
        shape = f'{w}x{h}'
        trim = f'{wt}x{ht}'
        meta = sprite_meta_bytes(wt) if wt else 0
        tot = enc + meta
        pct = tot / raw * 100 if raw else 0
        print(f"{cat:<14} {lab:<24} {shape:>8} {raw:>5} {trim:>8} "
              f"{traw:>6} {enc:>4} {meta:>5} {tot:>5} {pct:>5.1f}%")

    # ---- per-category aggregates
    print()
    print("-" * 96)
    print("Per-category totals (with meta):")
    print(f"\n  {'Category':<14} {'Sprites':>8} {'Raw':>7} "
          f"{'Trim-raw':>9} {'Enc':>6} {'Meta':>5} "
          f"{'Total':>7} {'%raw':>6}")
    print("  " + "-" * 80)
    bycat = {}
    for cat, lab, w, h, raw, wt, ht, traw, enc, _ in rows:
        if cat not in bycat:
            bycat[cat] = [0, 0, 0, 0, 0]   # n, raw, traw, enc, meta
        bycat[cat][0] += 1
        bycat[cat][1] += raw
        bycat[cat][2] += traw
        bycat[cat][3] += enc
        bycat[cat][4] += sprite_meta_bytes(wt) if wt else 0
    for cat, (n, raw, traw, enc, meta) in bycat.items():
        tot = enc + meta
        pct_raw = tot / raw * 100
        print(f"  {cat:<14} {n:>8} {raw:>7} {traw:>9} {enc:>6} "
              f"{meta:>5} {tot:>7} {pct_raw:>5.1f}%")
    tot_raw = sum(b[1] for b in bycat.values())
    tot_trim = sum(b[2] for b in bycat.values())
    tot_enc = sum(b[3] for b in bycat.values())
    tot_meta = sum(b[4] for b in bycat.values())
    n_total = sum(b[0] for b in bycat.values())
    print("  " + "-" * 80)
    print(f"  {'TOTAL':<14} {n_total:>8} {tot_raw:>7} {tot_trim:>9} "
          f"{tot_enc:>6} {tot_meta:>5} {tot_enc + tot_meta:>7} "
          f"{(tot_enc + tot_meta)/tot_raw*100:>5.1f}%")

    # ---- per-stage footprint
    #
    # Per stage:
    #   * 41 untrimmed 4x32 sprites: 18 tiles + 14 LEVD hazards
    #     + 6 explosion frames + 3 GRAPHIX hazards (game-shared).
    #   * 15 trimmed variable-shape sprites: 1 player + 4 enemy +
    #     3 enemy_hit (per-scenario) + 3 flame + 4 pickup (game-shared).
    # Tiles, explosions, the 3 GRAPHIX hazards are stationary plot
    # envelopes and stay at 4x32. Only animating / moving sprites get
    # the border trim.
    enc_by_label = {lab: enc for _, lab, _, _, _, _, _, _, enc, _ in rows}
    meta_by_label = {lab: sprite_meta_bytes(wt) if wt else 0
                     for _, lab, _, _, _, wt, _, _, _, _ in rows}

    def trim_total(label):
        return enc_by_label[label] + meta_by_label[label]

    game_flame  = sum(trim_total(f'flame_&{a:04X}') for a in FLAME_ADDRS)
    game_pickup = sum(trim_total(f'{lab}_&{a:04X}') for a, lab in PICKUP_ADDRS_LABELS)
    print()
    print("Per-scenario extra (player + enemy + enemy_hit; shared S1/S2):")
    print(f"  {'Scenario':>10}  {'player':>7}  {'enemy×4':>8}  "
          f"{'hit×3':>7}  {'subtotal':>9}")
    for level in (1, 2, 3, 4):
        p  = trim_total(f'L{level}_player_sprite')
        en = sum(trim_total(f'L{level}_enemy_0{i}') for i in range(4))
        eh = sum(trim_total(f'L{level}_enemy_hit_0{i}') for i in range(1, 4))
        print(f"  {'L'+str(level):>10}  {p:>7}  {en:>8}  {eh:>7}  "
              f"{p+en+eh:>9}")
    print(f"\nGame-shared variable sprites (3 flame + 4 pickup):")
    print(f"  flames:  {game_flame} B")
    print(f"  pickups: {game_pickup} B")
    print(f"  shared TOTAL: {game_flame + game_pickup} B")

    # ---- 4x32 main bucket (re-includes the 3 GRAPHIX hazards untrimmed)
    print()
    print("Per-stage TOTAL footprint (data + meta everywhere):")
    print(f"  {'Stage':<6} {'4x32 main':>10} {'+player':>8} "
          f"{'+enemy':>7} {'+hit':>5} {'+flame':>7} {'+pickup':>8} "
          f"{'total':>8} {'raw':>6} {'%raw':>6}")
    print("  " + "-" * 84)
    files2 = load_files()
    M = sprite_meta_bytes(SPRITE_W_COLS)   # = 10 for 4-col main sprites
    main_per_stage = {}
    for level in (1, 2, 3, 4):
        for stage in (1, 2):
            tile_data = sum(
                len(encode_sprite(files2[('LEVD1', level)][TILE_CATALOG_OFF + tid*SPRITE_SIZE:
                                                            TILE_CATALOG_OFF + (tid+1)*SPRITE_SIZE],
                                  SPRITE_W_COLS, SPRITE_H_LINES)[1])
                for tid in range(TILE_COUNT))
            src_haz = files2[('LEVD2', level)] if stage == 1 else files2[('LEVD3', level)]
            haz_data = sum(
                len(encode_sprite(src_haz[LEVD2_HAZARD_OFF + hid*SPRITE_SIZE:
                                          LEVD2_HAZARD_OFF + (hid+1)*SPRITE_SIZE],
                                  SPRITE_W_COLS, SPRITE_H_LINES)[1])
                for hid in range(LEVD2_HAZARD_COUNT))
            ex_data = sum(
                len(encode_sprite(files2[('LEVD1', level)][LEVD1_EXPLOSION_OFF + i*SPRITE_SIZE:
                                                            LEVD1_EXPLOSION_OFF + (i+1)*SPRITE_SIZE],
                                  SPRITE_W_COLS, SPRITE_H_LINES)[1])
                for i in range(LEVD1_EXPLOSION_COUNT))
            ex_data += len(encode_sprite(files2[('LEVD2', level)][HAZARD_A_OFF:HAZARD_A_OFF+SPRITE_SIZE],
                                          SPRITE_W_COLS, SPRITE_H_LINES)[1])
            ex_data += len(encode_sprite(files2[('LEVD2', level)][HAZARD_B_OFF:HAZARD_B_OFF+SPRITE_SIZE],
                                          SPRITE_W_COLS, SPRITE_H_LINES)[1])
            gfx_haz_data = sum(
                len(encode_sprite(files2['GRAPHIX'][a - GRAPHIX_LOAD:
                                                     a - GRAPHIX_LOAD + SPRITE_SIZE],
                                  SPRITE_W_COLS, SPRITE_H_LINES)[1])
                for a in GRAPHIX_HAZARD_ADDRS)
            n_main = TILE_COUNT + LEVD2_HAZARD_COUNT + 6 + 3   # 41
            main_per_stage[(level, stage)] = (tile_data + haz_data + ex_data
                                              + gfx_haz_data + n_main * M)

    raw_per_stage = ((TILE_COUNT + LEVD2_HAZARD_COUNT + 6 + 3) * SPRITE_SIZE  # 41 × 128
                     + PLAYER_SIZE
                     + 7 * ENEMY_SIZE_                                         # 4 enemy + 3 enemy_hit
                     + 3 * FLAME_SIZE
                     + 4 * PICKUP_SIZE)
    for level in (1, 2, 3, 4):
        for stage in (1, 2):
            main_d = main_per_stage[(level, stage)]
            p  = trim_total(f'L{level}_player_sprite')
            en = sum(trim_total(f'L{level}_enemy_0{i}') for i in range(4))
            eh = sum(trim_total(f'L{level}_enemy_hit_0{i}') for i in range(1, 4))
            tot = main_d + p + en + eh + game_flame + game_pickup
            pct = tot / raw_per_stage * 100
            print(f"  L{level}S{stage}   {main_d:>10}  {p:>8}  {en:>7}  "
                  f"{eh:>5}  {game_flame:>7}  {game_pickup:>8}  "
                  f"{tot:>8}  {raw_per_stage:>6}  {pct:>5.1f}%")

    n_per_stage = (TILE_COUNT + LEVD2_HAZARD_COUNT + 6 + 3              # 41 main
                   + 1 + 4 + 3 + 3 + 4)                                 # 15 trimmed
    print(f"\n  {n_per_stage} sprites per stage = 41 (4x32 main, untrimmed) "
          f"+ 15 (trimmed variable-shape)")
    print(f"  Raw per stage = {raw_per_stage} B "
          f"({raw_per_stage/1024:.2f} KB)")


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------

def survey():
    files = load_files()
    sprites = list(enumerate_sprites(files))

    # round-trip check + per-sprite encoded length
    encoded: list[tuple[str, str, int, int]] = []   # (category, label, raw_len, enc_len)
    for category, label, data in sprites:
        assert len(data) == SPRITE_SIZE, (label, len(data))
        flag, enc, _col_offsets = encode_sprite(data, SPRITE_W_COLS, SPRITE_H_LINES)
        roundtrip = decode_sprite(flag, enc)
        if roundtrip != data:
            raise SystemExit(f"round-trip FAILED for {label}")
        encoded.append((category, label, len(data), len(enc)))

    n_sprites = len(encoded)
    total_raw = sum(r[2] for r in encoded)
    total_enc = sum(r[3] for r in encoded)

    # ---- summary by category
    print("=" * 76)
    print("Sprite RLE — Scheme C survey")
    print("All 4x32 sprites across all 4 scenarios / both stages.")
    print("Per-sprite metadata = { flag, base_addr, col_offsets[W], "
          "palette[3] } = 6 + W bytes "
          f"(= {SPRITE_META_BYTES} for the 4-col sprites here).")
    print("=" * 76)
    by_cat = {}
    for cat, lab, raw, enc in encoded:
        by_cat.setdefault(cat, []).append((lab, raw, enc))
    print(f"\n{'Category':<20} {'Sprites':>8} {'Raw':>10} {'C-data':>10} "
          f"{'+meta':>8} {'ratio':>8}")
    print("-" * 68)
    for cat, rows in by_cat.items():
        n = len(rows)
        raw = sum(r[1] for r in rows)
        enc = sum(r[2] for r in rows)
        meta = n * SPRITE_META_BYTES
        print(f"{cat:<20} {n:>8} {raw:>10} {enc:>10} {meta:>8} "
              f"{(enc+meta)/raw*100:>7.1f}%")
    print("-" * 68)
    print(f"{'TOTAL':<20} {n_sprites:>8} {total_raw:>10} {total_enc:>10} "
          f"{n_sprites*SPRITE_META_BYTES:>8} "
          f"{(total_enc + n_sprites*SPRITE_META_BYTES)/total_raw*100:>7.1f}%")

    # ---- per-stage memory footprint (what needs to be loaded simultaneously)
    #
    # Per stage, sprites that must be resident in RAM:
    #   - 18 tiles (per scenario, shared across both stages of the scenario)
    #   - 14 LEVD hazards (per stage — stage 1 = LEVD2, stage 2 = LEVD3)
    #   - 3 GRAPHIX hazards (shared across the whole game)
    #   - 6 explosion frames (per scenario, shared across both stages)
    #   => 41 sprites loaded per stage.
    print("\n" + "=" * 76)
    print("Per-stage memory footprint (sprites loaded simultaneously per stage)")
    print("=" * 76)
    by_label = {lab: enc for _, lab, _, enc in encoded}

    n_per_stage = TILE_COUNT + LEVD2_HAZARD_COUNT + 6 + 3   # 41 sprites
    raw_per_stage = n_per_stage * SPRITE_SIZE              # 5248 B
    print(f"\n  {'Stage':<8} {'tiles':>7} {'hazard':>7} {'expl':>5} {'GFX':>5} "
          f"{'data':>6} {'meta':>5} {'total':>6} {'raw':>6} {'pct':>6}")
    print("  " + "-" * 70)
    grand = []
    for level in (1, 2, 3, 4):
        for stage in (1, 2):
            t = sum(by_label[f'L{level}_tile_{tid:02d}'] for tid in range(TILE_COUNT))
            h = sum(by_label[f'L{level}S{stage}_hazard_{hid:02d}']
                    for hid in range(LEVD2_HAZARD_COUNT))
            e = sum(by_label[f'L{level}_explosion_{i:02d}'] for i in range(6))
            gfx = sum(by_label[f'graphix_&{addr:04X}'] for addr in GRAPHIX_HAZARD_ADDRS)
            meta = n_per_stage * SPRITE_META_BYTES
            data = t + h + e + gfx
            total = data + meta
            pct = total / raw_per_stage * 100
            print(f"  L{level}S{stage}    {t:>7} {h:>7} {e:>5} {gfx:>5} "
                  f"{data:>6} {meta:>5} {total:>6} {raw_per_stage:>6} {pct:>5.1f}%")
            grand.append((f'L{level}S{stage}', total))
    print("  " + "-" * 70)
    avg = sum(x[1] for x in grand) / len(grand)
    print(f"\n  Raw per stage:   {raw_per_stage} B (= 41 sprites × 128 B)")
    print(f"  Worst stage:     {max(grand, key=lambda x: x[1])[0]} = "
          f"{max(grand, key=lambda x: x[1])[1]} B "
          f"({max(grand, key=lambda x: x[1])[1]/raw_per_stage*100:.1f}% of raw)")
    print(f"  Best stage:      {min(grand, key=lambda x: x[1])[0]} = "
          f"{min(grand, key=lambda x: x[1])[1]} B "
          f"({min(grand, key=lambda x: x[1])[1]/raw_per_stage*100:.1f}% of raw)")
    print(f"  Avg per stage:   {avg:.0f} B "
          f"({avg/1024:.1f} KB, {avg/raw_per_stage*100:.1f}% of raw)")
    print(f"\nNote: 41 sprites per stage = 18 tiles + 14 LEVD hazards "
          f"+ 6 explosions + 3 GRAPHIX hazards.")
    print(f"      Tiles and explosions are scenario-shared between the "
          f"two stages.")
    print(f"      GRAPHIX hazards are game-shared (same 3 sprites for "
          f"every stage).")

    # ---- per-scenario breakdown (data only, no meta)
    print("\nPer-scenario / per-category compressed (data only, no meta):")
    print(f"  {'Scenario':>10}  {'tiles':>7}  {'haz S1':>7}  {'haz S2':>7}  "
          f"{'expl':>5}  {'total':>7}")
    for level in (1, 2, 3, 4):
        ts = sum(by_label[f'L{level}_tile_{tid:02d}'] for tid in range(TILE_COUNT))
        s1 = sum(by_label[f'L{level}S1_hazard_{hid:02d}'] for hid in range(LEVD2_HAZARD_COUNT))
        s2 = sum(by_label[f'L{level}S2_hazard_{hid:02d}'] for hid in range(LEVD2_HAZARD_COUNT))
        ex = sum(by_label[f'L{level}_explosion_{i:02d}'] for i in range(6))
        print(f"  {'L'+str(level):>10}  {ts:>7}  {s1:>7}  {s2:>7}  {ex:>5}  {ts+s1+s2+ex:>7}")
    gx = sum(by_label[f'graphix_&{addr:04X}'] for addr in GRAPHIX_HAZARD_ADDRS)
    print(f"  {'GRAPHIX':>10}  {'—':>7}  {'—':>7}  {'—':>7}  {'—':>5}  {gx:>7}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'other':
        survey_other()
    else:
        survey()
        print()
        survey_other()
