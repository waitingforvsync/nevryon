#!/usr/bin/env python3
"""Emit BeebAsm source for one tile catalog, encoded with sprite RLE
scheme C (see ../../docs/sprite_rle_notes.md).

Reads 18 tile PNGs from --src (tile_00.png .. tile_17.png), each
16x32 pixels using exactly four colours given by --palette. Each
pixel is mapped back to a 2bpp value 0..3 against the palette,
packed column-major into a 128-byte sprite, then compressed with
scheme C. Round-trip is verified for every sprite via the local
sprite_rle.decode_sprite (the spec decoder -- our smart encoder
still produces a spec-valid stream).

Usage:
  encode_tiles.py --src DIR --out FILE --palette C0,C1,C2,C3
                  [--label TEXT] [--expected-bytes N]

Palette colours are comma-separated; each is either a 6-digit hex
code (e.g. "ff0000" or "#ff0000") or a BBC physical colour name:
black, red, green, yellow, blue, magenta, cyan, white. The first
entry is pixel-value 0 (always black for Nevryon's MODE 5 sprites).

If a PNG contains an off-palette pixel the script errors out with
its coordinates so it's easy to spot in an editor.

Designed for build-script invocation: one call per level, with all
paths + palette passed explicitly. No hardcoded level table.
"""

from __future__ import annotations

import argparse
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
sys.path.insert(0, str(HERE))
from sprite_rle import decode_sprite, pick_flag  # noqa: E402


TILE_COUNT    = 18
SPRITE_W_COLS = 4         # 4 byte-columns -> 16 pixels wide
SPRITE_H      = 32        # 32 scanlines
SPRITE_W_PX   = SPRITE_W_COLS * 4
SPRITE_BYTES  = SPRITE_W_COLS * SPRITE_H


# BBC Micro physical-colour set (MODE 1/2/5 8-colour set). Used by the
# palette parser to accept human-friendly names alongside hex codes.
BBC_PHYSICAL_NAMES: dict[str, tuple[int, int, int]] = {
    'black':   (0,   0,   0),
    'red':     (255, 0,   0),
    'green':   (0,   255, 0),
    'yellow':  (255, 255, 0),
    'blue':    (0,   0,   255),
    'magenta': (255, 0,   255),
    'cyan':    (0,   255, 255),
    'white':   (255, 255, 255),
}


EQUB_PER_LINE = 16


def parse_colour(spec: str) -> tuple[int, int, int]:
    """Parse one colour: either a BBC physical name or a 6-digit hex
    (with or without leading '#')."""
    s = spec.strip().lower().lstrip('#')
    if s in BBC_PHYSICAL_NAMES:
        return BBC_PHYSICAL_NAMES[s]
    if len(s) == 6 and all(c in '0123456789abcdef' for c in s):
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    raise SystemExit(
        f'invalid colour {spec!r}: expected 6-digit hex or one of '
        f'{sorted(BBC_PHYSICAL_NAMES)}.')


def parse_palette(spec: str) -> list[tuple[int, int, int]]:
    """Parse a 4-colour comma-separated palette spec."""
    parts = [p.strip() for p in spec.split(',') if p.strip()]
    if len(parts) != 4:
        raise SystemExit(
            f'palette must have exactly 4 colours, got {len(parts)} '
            f'in {spec!r}.')
    return [parse_colour(p) for p in parts]


def load_tile_png(path: Path,
                  palette: list[tuple[int, int, int]]) -> bytes:
    """Load tile_NN.png and return the 128 column-major 2bpp source bytes.

    The image must be exactly SPRITE_W_PX x SPRITE_H pixels and use
    only colours from `palette`. Off-palette pixels error with their
    coordinates so they're easy to find in an editor.
    """
    rgb_to_pixel = {rgb: idx for idx, rgb in enumerate(palette)}

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
            if rgb not in rgb_to_pixel:
                raise SystemExit(
                    f'{path.name}: off-palette pixel at ({x},{y}) = {rgb}. '
                    f'Allowed: {palette}.')
            pix2bpp[y][x] = rgb_to_pixel[rgb]

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


def encode_tile_catalog(src_dir: Path, out_path: Path,
                        palette: list[tuple[int, int, int]],
                        label: str
                        ) -> tuple[int, int, int,
                                   list[tuple[int, int, int, int]]]:
    """Encode 18 tiles from src_dir into out_path.

    Returns (enc_total, raw_total, coalesced_columns_saved,
    per_tile_stats) where each per_tile_stats entry is (tid, flag_byte,
    enc_bytes, n_unique_cols)."""
    lines: list[str] = []
    lines.append(rf'\\ Nevryon Ultimate -- {label} tile catalog')
    lines.append(rf'\\ Auto-generated by tools/encode_tiles.py from {src_dir}/*.png.')
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
        png_path = src_dir / f'tile_{tid:02d}.png'
        sprite = load_tile_png(png_path, palette)

        flag, col_streams = encode_sprite_columns(sprite)

        # Round-trip: concatenate per-column streams and decode via the
        # spec decoder. The smart encoder still produces a spec-valid
        # stream (just biased toward more runs).
        if decode_sprite(flag, b''.join(col_streams)) != sprite:
            raise SystemExit(f'{label} tile {tid:02d}: round-trip FAILED')

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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(lines) + '\n')

    return enc_total, raw_total, coalesced_columns_saved, per_tile_stats


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description='Encode one tile catalog into a BeebAsm source file.')
    ap.add_argument('--src', type=Path, required=True,
                    help='directory containing tile_00.png .. tile_17.png')
    ap.add_argument('--out', type=Path, required=True,
                    help='output .6502 file path')
    ap.add_argument('--palette', required=True,
                    help='four colours, comma-separated. Each is either a '
                         '6-digit hex code (e.g. "ff0000") or a BBC physical '
                         'name: black/red/green/yellow/blue/magenta/cyan/white. '
                         'The first entry is pixel value 0.')
    ap.add_argument('--label', default=None,
                    help='label used in the output file header comment. '
                         'Defaults to the --src directory name.')
    ap.add_argument('--expected-bytes', type=int, default=None,
                    help='if set, error out unless the encoded total equals N. '
                         'For build-script regression checks.')
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    palette = parse_palette(args.palette)
    label = args.label if args.label is not None else args.src.name

    enc_total, raw_total, coalesced, stats = encode_tile_catalog(
        args.src, args.out, palette, label)

    pct = enc_total * 100 // raw_total
    print(f'wrote {args.out}')
    print(f'  {TILE_COUNT} tiles, {enc_total} B encoded / {raw_total} B raw '
          f'({pct}%); {coalesced} duplicate columns coalesced')

    # Compact per-tile table: t<id>=&<flag>:<bytes>[ x<unique-cols>]
    rows = []
    for tid, flag_byte, enc_len, n_unique in stats:
        tag = '' if n_unique == SPRITE_W_COLS else f' x{n_unique}'
        rows.append(f't{tid:02d}=&{flag_byte:02X}:{enc_len}{tag}')
    for i in range(0, len(rows), 6):
        print('  ' + '   '.join(rows[i:i + 6]))

    if args.expected_bytes is not None and enc_total != args.expected_bytes:
        raise SystemExit(
            f'encoded size {enc_total} != expected {args.expected_bytes}. '
            f'If you intentionally changed the artwork or the encoder, '
            f'update the --expected-bytes value in the caller.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
