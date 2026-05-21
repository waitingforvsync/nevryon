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


def encode_sprite(sprite: bytes, flag: int | None = None
                  ) -> tuple[int, bytes, list[int]]:
    """Encode one 128-byte (or NxSPRITE_COL_BYTES) sprite. Returns
    (flag, encoded_stream, col_offsets) — stream does NOT include the
    leading flag header byte. col_offsets[c] = offset within
    encoded_stream where column c's data starts (col_offsets[0] is
    always 0). Encoding is per-column (no runs cross column
    boundaries)."""
    if flag is None:
        flag = pick_flag(sprite)
    flag_byte = flag << 3
    out = bytearray()
    n_cols = len(sprite) // SPRITE_COL_BYTES
    assert len(sprite) == n_cols * SPRITE_COL_BYTES
    col_offsets = []
    for c in range(n_cols):
        col_offsets.append(len(out))
        col = sprite[c * SPRITE_COL_BYTES:(c + 1) * SPRITE_COL_BYTES]
        out.extend(encode_column(col, flag_byte))
    return flag, bytes(out), col_offsets


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


# Per-sprite on-disk / in-RAM metadata, per Rich's spec:
#   { flag_byte, base_addr (lo, hi), col_offset[0..3] }
# = 1 + 2 + 4 = 7 bytes per sprite.
SPRITE_META_BYTES = 1 + 2 + SPRITE_W_COLS


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
        flag, enc, _col_offsets = encode_sprite(data)
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
    print("Per-sprite metadata = { flag, base_addr, col_offsets[4] } = "
          f"{SPRITE_META_BYTES} bytes.")
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
    survey()
