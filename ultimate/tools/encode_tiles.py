#!/usr/bin/env python3
"""Emit BeebAsm source for level 1's tile catalog, encoded with
sprite RLE scheme C (see ../../docs/sprite_rle_notes.md).

Reads source artwork from `assets/level1/tile_NN.png` (18 files,
each 16x32 pixels = 4x32 MODE 5 byte-columns, scenario-1 palette
{black, red, yellow, white}). Pixel values are mapped back to 2bpp
0..3, packed column-major into a 128-byte sprite, then compressed
with scheme C. Round-trip is verified for every sprite.

Output (`tiles_level1.6502`):

    tile_NN_rle_flag = &XX            \\ FLAG_BYTE = FLAG << 3
    .tile_NN_col_0
        EQUB ..., ...
    .tile_NN_col_1
        EQUB ...
    .tile_NN_col_2
        EQUB ...
    .tile_NN_col_3
        EQUB ...

Runs do NOT cross sprite-column boundaries, so each `.tile_NN_col_M`
label points at the first encoded byte of one MODE 5 column (32
source bytes). The user builds the per-column / per-sprite offset
tables on top of these labels.

If a tile PNG contains an off-palette colour the script errors out
with the pixel coordinates so it's easy to spot in an editor.

Run from anywhere -- paths resolve from the script's location.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

# Round-trip decoder + flag picker from the local sprite_rle module
# (which mirrors the parent repo's spec-exact implementation -- the one
# that produced the survey numbers in ../../docs/sprite_rle_notes.md).
# The column-encoder below is a remake-specific override with two
# optimisations the spec encoder doesn't apply:
#
#   1. All-RLE long-run split. The spec encoder caps runs at 10 and
#      lets the residue spill as literals (e.g. 32 zeros -> three runs
#      of 10 + two literals). The remake decoder pays ~56 cyc per
#      literal vs ~26 cyc per run-body byte, so we prefer to close
#      every long run with another RLE block. For run_len = 10q+r
#      with r in {1, 2}, we emit (q-1) runs of 10 then (r+7, 3)
#      instead of (q runs of 10 + r literals).
#
#   2. Within-sprite column coalescing. If two or more columns of a
#      sprite encode to the exact same byte stream (e.g. tile_06,
#      the blank all-zero slot; tile_02, the repeating-pattern slot),
#      we emit the stream once and stack the .tile_NN_col_M labels
#      so they all resolve to the same address.
#
# Both transformations preserve correctness -- the per-column stream
# is decoded identically by the spec decoder. We still round-trip
# every sprite through `sprite_rle.decode_sprite` before emitting.
HERE = Path(__file__).resolve().parent
ULTIMATE_DIR = HERE.parent
REPO_ROOT = ULTIMATE_DIR.parent

sys.path.insert(0, str(HERE))
from sprite_rle import decode_sprite, pick_flag  # noqa: E402


ASSETS_DIR  = ULTIMATE_DIR / 'assets' / 'level1'
OUTPUT_PATH = ULTIMATE_DIR / 'data' / 'level1' / 'tiles.6502'

TILE_COUNT    = 18
SPRITE_W_COLS = 4         # 4 byte-columns -> 16 pixels wide
SPRITE_H      = 32        # 32 scanlines
SPRITE_W_PX   = SPRITE_W_COLS * 4
SPRITE_BYTES  = SPRITE_W_COLS * SPRITE_H

# Regression baseline for the emitted encoded data, level -> bytes.
# This is the byte count AFTER both the all-RLE long-run split and
# the within-sprite column coalescing (see comment above the imports).
# It will differ from the "Scheme C (data)" survey numbers in
# ../docs/sprite_rle_notes.md (which doesn't apply either
# transformation) -- the survey gave 1763 B for level 1; we land
# lower thanks to coalescing. If a re-paint of the artwork changes
# the byte count, update this constant alongside the change.
EXPECTED_ENCODED_BYTES = {
    1: 1547,    # vs survey's 1763 B: saves 216 B via column coalescing
                # (-220 B) minus a handful of bytes added by the
                # all-RLE long-run split.
}

# Level-1 (scenario 1, Battle Cruiser) MODE 5 palette. Pixel value
# 0..3 -> RGB. Mirrors NEVRYON_LEVEL_PALETTES[1] in ../tools/render_screen.py.
LEVEL1_PALETTE_RGB: list[tuple[int, int, int]] = [
    (0,   0,   0),    # 0 black
    (255, 0,   0),    # 1 red
    (255, 255, 0),    # 2 yellow
    (255, 255, 255),  # 3 white
]
RGB_TO_PIXEL = {rgb: idx for idx, rgb in enumerate(LEVEL1_PALETTE_RGB)}

EQUB_PER_LINE = 16


def load_tile_png(path: Path) -> bytes:
    """Load tile_NN.png and return the 128 column-major 2bpp source bytes.

    The image must be exactly SPRITE_W_PX x SPRITE_H pixels and use
    only colours from LEVEL1_PALETTE_RGB. The PNG is sampled at its
    native pixel grid -- any upscaling done by render_sprite.py
    earlier in the pipeline (its --scale flag) was disabled when the
    assets/ copies were produced, so the assets here ARE at native
    resolution. (If you re-export, keep --scale 1.)
    """
    im = Image.open(path).convert('RGB')
    if im.size != (SPRITE_W_PX, SPRITE_H):
        raise SystemExit(
            f'{path.name}: expected {SPRITE_W_PX}x{SPRITE_H} px, got '
            f'{im.size[0]}x{im.size[1]} -- re-export at native scale.')

    px = im.load()

    # Per-pixel 0..3, row-major first, then re-pack column-major into bytes.
    pix2bpp = [[0] * SPRITE_W_PX for _ in range(SPRITE_H)]
    for y in range(SPRITE_H):
        for x in range(SPRITE_W_PX):
            rgb = px[x, y]
            if rgb not in RGB_TO_PIXEL:
                raise SystemExit(
                    f'{path.name}: off-palette pixel at ({x},{y}) = {rgb}. '
                    f'Allowed: {LEVEL1_PALETTE_RGB}.')
            pix2bpp[y][x] = RGB_TO_PIXEL[rgb]

    # MODE 5 byte layout: pixel n (n=0..3 left-to-right) uses
    # bit (7-n) for the high bit of its 2bpp value and bit (3-n) for
    # the low bit. See render_screen.decode_byte for the forward path.
    out = bytearray(SPRITE_BYTES)
    for c in range(SPRITE_W_COLS):
        for y in range(SPRITE_H):
            b = 0
            for p in range(4):
                v = pix2bpp[y][c * 4 + p]   # 0..3
                hi = (v >> 1) & 1
                lo = v & 1
                b |= hi << (7 - p)
                b |= lo << (3 - p)
            out[c * SPRITE_H + y] = b
    return bytes(out)


def format_equb(data: bytes, width: int = EQUB_PER_LINE,
                indent: str = '    ') -> list[str]:
    out = []
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        out.append(indent + 'EQUB ' + ', '.join(f'&{b:02X}' for b in chunk))
    return out


def encode_column(col: bytes, flag_byte: int) -> bytes:
    """Scheme C column encoder with the all-RLE long-run policy.

    For run_len <= 10: same as the spec encoder.
    For run_len  > 10: split into runs of size 3..10 only (never let
    the tail spill as literals). Choice rule, given run_len = 10*q + r:
        r == 0      -> q runs of 10
        r in 3..9   -> q runs of 10 + one run of r
        r in {1,2}  -> (q-1) runs of 10 + one run of (r+7) + one run of 3
    The (r+7, 3) split is the only legal 2-run partition of 11/12 with
    both pieces in [3, 10] and is byte-equivalent or 1 byte worse than
    leaving (r) literals, but lets the decoder skip its slower literal
    path entirely for the tail.
    """
    out = bytearray()
    i = 0
    n = len(col)
    while i < n:
        # walk the full run starting at i (uncapped; we'll split below)
        j = i
        while j < n and col[j] == col[i]:
            j += 1
        run_len = j - i
        value = col[i]
        if run_len < 3:
            # 1 or 2 isolated identical bytes -- have to go via literals
            for _ in range(run_len):
                out.append(value ^ flag_byte)
        elif run_len <= 10:
            out.append(run_len - 3)
            out.append(value)
        else:
            q, r = divmod(run_len, 10)
            if r == 0:
                blocks = [10] * q
            elif r >= 3:
                blocks = [10] * q + [r]
            else:                           # r in {1, 2}
                blocks = [10] * (q - 1) + [r + 7, 3]
            for bsz in blocks:
                out.append(bsz - 3)
                out.append(value)
        i = j
    return bytes(out)


def encode_sprite_columns(sprite: bytes) -> tuple[int, list[bytes]]:
    """Encode a 4x32 column-major sprite. Returns (flag, [stream_per_column]).
    Each column stream is independent -- runs never cross a column
    boundary -- so the streams can be concatenated for spec-decoder
    round-trip OR labelled separately for the BeebAsm output."""
    assert len(sprite) == SPRITE_BYTES
    flag = pick_flag(sprite)
    flag_byte = flag << 3
    streams = [
        encode_column(sprite[c * SPRITE_H:(c + 1) * SPRITE_H], flag_byte)
        for c in range(SPRITE_W_COLS)
    ]
    return flag, streams


def main() -> int:
    lines: list[str] = []
    lines.append(r'\\ Nevryon Ultimate -- Level 1 tile catalog')
    lines.append(r'\\ Auto-generated by tools/encode_tiles.py from assets/level1/*.png.')
    lines.append(r'\\ Do not edit by hand -- edit the PNGs and re-run the encoder.')
    lines.append(r'\\')
    lines.append(r'\\ 18 tile sprites, raw shape 4 cols x 32 lines, column-major,')
    lines.append(r'\\ MODE 5 2bpp source bytes (= 16x32 pixels at MODE 5 resolution).')
    lines.append(r'\\')
    lines.append(r'\\ Compressed with sprite RLE scheme C (../docs/sprite_rle_notes.md),')
    lines.append(r'\\ with two remake-specific optimisations:')
    lines.append(r'\\   * stream byte b <  8: run code. count = b + 3 (3..10). Next byte')
    lines.append(r"\\                          is the run value, shipped RAW (NOT eor'd).")
    lines.append(r'\\   * stream byte b >= 8: literal. emit (b EOR flag_byte) once.')
    lines.append(r'\\   * FLAG_BYTE = FLAG << 3, picked so no source byte has top-5-bits')
    lines.append(r'\\     == FLAG. Carried per-sprite in tile_NN_rle_flag.')
    lines.append(r'\\   * Runs never cross a column boundary, so each .tile_NN_col_M label')
    lines.append(r'\\     starts a fresh decoder state for one 32-source-byte column.')
    lines.append(r'\\   * Long runs (>10) are split into all-RLE pieces (3..10 each); the')
    lines.append(r'\\     decoder never falls into its slower literal path for run tails.')
    lines.append(r'\\   * Columns that encode to identical bytes share their stream: their')
    lines.append(r'\\     .tile_NN_col_M labels are stacked at the same address.')
    lines.append('')

    raw_total = 0
    enc_total = 0
    coalesced_columns_saved = 0
    per_tile_stats: list[tuple[int, int, int, int]] = []   # (tid, flag, bytes, n_unique_cols)

    for tid in range(TILE_COUNT):
        png_path = ASSETS_DIR / f'tile_{tid:02d}.png'
        sprite = load_tile_png(png_path)

        flag, col_streams = encode_sprite_columns(sprite)

        # Round-trip: concatenate per-column streams and decode via the
        # parent's spec decoder. Catches any encoder bug; the smart
        # encoder still produces a spec-valid stream (just biased toward
        # more runs).
        if decode_sprite(flag, b''.join(col_streams)) != sprite:
            raise SystemExit(f'round-trip FAILED for tile {tid:02d}')

        # Within-sprite column coalescing. Walk columns 0..3 in order;
        # the first column to use a given stream owns it (gets emitted
        # first), later columns with the same stream stack their label
        # on top.
        unique_streams: list[bytes] = []
        column_groups: list[list[int]] = []
        for c in range(SPRITE_W_COLS):
            stream = col_streams[c]
            for gi, us in enumerate(unique_streams):
                if stream == us:
                    column_groups[gi].append(c)
                    break
            else:
                unique_streams.append(stream)
                column_groups.append([c])

        sprite_bytes = sum(len(s) for s in unique_streams)
        n_unique = len(unique_streams)
        coalesced_columns_saved += SPRITE_W_COLS - n_unique

        flag_byte = flag << 3
        raw_total += SPRITE_BYTES
        enc_total += sprite_bytes
        per_tile_stats.append((tid, flag_byte, sprite_bytes, n_unique))

        pct = sprite_bytes * 100 // SPRITE_BYTES
        coalesce_note = f', {n_unique} unique col' + ('s' if n_unique != 1 else '')
        coalesce_note = '' if n_unique == SPRITE_W_COLS else coalesce_note
        lines.append(
            f'\\\\ tile_{tid:02d}: {sprite_bytes} bytes '
            f'({pct}% of raw 128 B{coalesce_note})')
        lines.append(f'tile_{tid:02d}_rle_flag = &{flag_byte:02X}')
        for stream, cols in zip(unique_streams, column_groups):
            for c in cols:
                lines.append(f'.tile_{tid:02d}_col_{c}')
            lines.extend(format_equb(stream))
        lines.append('')

    pct_total = enc_total * 100 // raw_total
    lines.append(
        f'\\\\ ---- totals: {enc_total} encoded / {raw_total} raw '
        f'({pct_total}%); {coalesced_columns_saved} duplicate columns coalesced ----')

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text('\n'.join(lines) + '\n')

    expected = EXPECTED_ENCODED_BYTES.get(1)
    if expected is None:
        print('NOTE: EXPECTED_ENCODED_BYTES[1] is None -- update the constant '
              f'to {enc_total} to lock this in as the regression baseline.')
    elif enc_total != expected:
        raise SystemExit(
            f'encoded size {enc_total} != expected {expected}. If you '
            f'intentionally changed the artwork or the encoder, update '
            f'EXPECTED_ENCODED_BYTES[1] in tools/encode_tiles.py.')

    print(f'Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}')
    print(f'  {TILE_COUNT} tiles, {enc_total} bytes encoded / {raw_total} raw'
          f' ({pct_total}%); {coalesced_columns_saved} duplicate columns coalesced')
    print()
    print(f'  {"tile":>4}  {"flag":>4}  {"enc":>4}  {"%raw":>5}  {"#cols":>5}')
    for tid, flag_byte, enc_len, n_unique in per_tile_stats:
        print(f'  {tid:>4}  &{flag_byte:02X}   {enc_len:>4}  '
              f'{enc_len * 100 // SPRITE_BYTES:>4}%  {n_unique:>5}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
