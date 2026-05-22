#!/usr/bin/env python3
"""Encode a directory of column-major MODE 5 sprites into a BeebAsm
source file, compressed with sprite RLE scheme C (see
../../docs/sprite_rle_notes.md).

Source: a directory containing one or more .png files. Each PNG is
W pixels wide x H pixels tall, where W must be a multiple of 4 (one
MODE 5 byte = 4 pixels). Dimensions are auto-detected per PNG; H can
be anything (32 for tile/hazard/explosion sprites, 22 for the
player, 24 for enemies, 8 for flames, etc.).

For each PNG `<name>.png`, the output file contains:

    \\\\ <name>: <W_cols>x<H_px> (<W_px>x<H_px> px), <enc> bytes ...
    <name>_width    = <W_cols>           \\ in MODE 5 byte-columns
    <name>_height   = <H_px>             \\ in pixels (= bytes per col)
    <name>_rle_flag = &XX                \\ FLAG_BYTE = FLAG << 3
    .<name>_col_0
        EQUB ..., ...
    .<name>_col_1
        EQUB ...
    ...
    .<name>_col_<W_cols-1>
        EQUB ...

`<name>` is the PNG's filename stem (`.png` stripped). The stem must
match `[A-Za-z_][A-Za-z0-9_]*` so it is a legal BeebAsm identifier.

Pixels are validated against `--palette`. Off-palette pixels error
with their coordinates. Identical columns within a sprite share
their stream (their `.<name>_col_M` labels are stacked). Long runs
(> 10 bytes) split into all-RLE pieces (no literal tails).

Designed for build-script invocation: one call per sprite set. No
hardcoded names or sizes -- the script discovers everything from
the source directory.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

# Round-trip decoder + flag picker from the local sprite_rle module
# (the spec-exact scheme-C library). The column-encoder below is the
# remake's smart override with two optimisations:
#
#   1. All-RLE long-run split. Runs > 10 bytes never spill as literals
#      (the literal decoder body is ~56 cyc vs ~26 cyc per run-body
#      byte). For run_len = 10q+r with r in {1, 2} we emit (q-1) runs
#      of 10 then (r+7, 3) instead of (q runs of 10 + r literals).
#
#   2. Within-sprite column coalescing. If two or more columns encode
#      to the same byte stream the stream is emitted once and the
#      duplicate column labels are stacked at the same address.
#
# Both transformations preserve correctness; we still round-trip every
# sprite through sprite_rle.decode_sprite before emitting.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sprite_rle import decode_sprite, pick_flag  # noqa: E402


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

# Symbol-name validator. The PNG stem becomes the BeebAsm label prefix
# directly, so it must be a legal identifier.
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

EQUB_PER_LINE = 16


def parse_colour(spec: str) -> tuple[int, int, int]:
    """Parse one colour: BBC physical name or 6-digit hex."""
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
            f'palette must have exactly 4 colours, got {len(parts)} in '
            f'{spec!r}.')
    return [parse_colour(p) for p in parts]


def load_png_to_sprite_bytes(
        path: Path,
        palette: list[tuple[int, int, int]]
        ) -> tuple[bytes, int, int]:
    """Load a PNG and return (sprite_bytes, w_cols, h_px).

    sprite_bytes is column-major MODE 5 2bpp: w_cols * h_px bytes,
    column 0 first (top-to-bottom), then column 1, etc.

    Width must be a multiple of 4 (each MODE 5 byte covers 4 pixels);
    height is unconstrained. Pixels must match `palette` exactly.
    """
    rgb_to_pixel = {rgb: idx for idx, rgb in enumerate(palette)}

    im = Image.open(path).convert('RGB')
    w_px, h_px = im.size
    if w_px % 4 != 0:
        raise SystemExit(
            f'{path.name}: image width {w_px} px is not a multiple of 4. '
            f'MODE 5 needs 4 px per byte.')
    if w_px == 0 or h_px == 0:
        raise SystemExit(f'{path.name}: empty image ({w_px}x{h_px}).')
    w_cols = w_px // 4

    px = im.load()

    # Per-pixel 0..3, row-major, then re-pack column-major into bytes.
    pix2bpp = [[0] * w_px for _ in range(h_px)]
    for y in range(h_px):
        for x in range(w_px):
            rgb = px[x, y]
            if rgb not in rgb_to_pixel:
                raise SystemExit(
                    f'{path.name}: off-palette pixel at ({x},{y}) = {rgb}. '
                    f'Allowed: {palette}.')
            pix2bpp[y][x] = rgb_to_pixel[rgb]

    # MODE 5 byte layout: pixel n (n=0..3 left-to-right within a byte)
    # uses bit (7-n) for the high bit of its 2bpp value and bit (3-n)
    # for the low bit. See render_screen.decode_byte for the forward
    # path.
    out = bytearray(w_cols * h_px)
    for c in range(w_cols):
        for y in range(h_px):
            b = 0
            for p in range(4):
                v = pix2bpp[y][c * 4 + p]   # 0..3
                hi = (v >> 1) & 1
                lo = v & 1
                b |= hi << (7 - p)
                b |= lo << (3 - p)
            out[c * h_px + y] = b
    return bytes(out), w_cols, h_px


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
    the tail spill as literals). Given run_len = 10*q + r:
        r == 0      -> q runs of 10
        r in 3..9   -> q runs of 10 + one run of r
        r in {1,2}  -> (q-1) runs of 10 + one run of (r+7) + one run of 3

    Column boundaries also bound runs (encoder caller calls once per
    column).
    """
    out = bytearray()
    i = 0
    n = len(col)
    while i < n:
        j = i
        while j < n and col[j] == col[i]:
            j += 1
        run_len = j - i
        value = col[i]
        if run_len < 3:
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
            else:                          # r in {1, 2}
                blocks = [10] * (q - 1) + [r + 7, 3]
            for bsz in blocks:
                out.append(bsz - 3)
                out.append(value)
        i = j
    return bytes(out)


def encode_sprite_columns(sprite: bytes, w_cols: int, h_px: int
                          ) -> tuple[int, list[bytes]]:
    """Encode a column-major sprite of `w_cols` x `h_px` bytes. Returns
    (flag, [stream_per_column]). Each column stream is independent."""
    assert len(sprite) == w_cols * h_px, (len(sprite), w_cols, h_px)
    flag = pick_flag(sprite)
    flag_byte = flag << 3
    streams = [
        encode_column(sprite[c * h_px:(c + 1) * h_px], flag_byte)
        for c in range(w_cols)
    ]
    return flag, streams


def emit_sprite(name: str, sprite: bytes, w_cols: int, h_px: int
                ) -> tuple[list[str], int, int, int, int]:
    """Encode one sprite and return (emit_lines, flag_byte, enc_bytes,
    raw_bytes, coalesced_columns)."""
    flag, col_streams = encode_sprite_columns(sprite, w_cols, h_px)

    # Round-trip via the spec decoder. The smart encoder still produces
    # a spec-valid stream (just biased toward more runs).
    decoded = decode_sprite(flag, b''.join(col_streams),
                            n_cols=w_cols, col_bytes=h_px)
    if decoded != sprite:
        raise SystemExit(f'{name}: round-trip FAILED')

    # Within-sprite column coalescing.
    unique_streams: list[bytes] = []
    column_groups: list[list[int]] = []
    for c in range(w_cols):
        stream = col_streams[c]
        for gi, us in enumerate(unique_streams):
            if stream == us:
                column_groups[gi].append(c)
                break
        else:
            unique_streams.append(stream)
            column_groups.append([c])

    raw_bytes = w_cols * h_px
    enc_bytes = sum(len(s) for s in unique_streams)
    n_unique  = len(unique_streams)
    coalesced = w_cols - n_unique
    flag_byte = flag << 3

    pct = enc_bytes * 100 // raw_bytes
    coalesce_note = (f', {n_unique} unique col' + ('s' if n_unique != 1 else '')
                     if n_unique != w_cols else '')

    lines: list[str] = []
    lines.append(
        f'\\\\ {name}: {w_cols}x{h_px} ({w_cols * 4}x{h_px} px), '
        f'{enc_bytes} bytes ({pct}% of raw {raw_bytes} B{coalesce_note})')
    lines.append(f'{name}_width    = {w_cols}')
    lines.append(f'{name}_height   = {h_px}')
    lines.append(f'{name}_rle_flag = &{flag_byte:02X}')
    for stream, cols in zip(unique_streams, column_groups):
        for c in cols:
            lines.append(f'.{name}_col_{c}')
        lines.extend(format_equb(stream))
    lines.append('')

    return lines, flag_byte, enc_bytes, raw_bytes, coalesced


def encode_sprite_set(src_dir: Path, out_path: Path,
                      palette: list[tuple[int, int, int]],
                      label: str
                      ) -> tuple[int, int, int,
                                 list[tuple[str, int, int, int, int, int]]]:
    """Encode every .png in src_dir into out_path.

    Returns (enc_total, raw_total, coalesced_columns_total,
    per_sprite_stats) where each per_sprite_stats entry is
    (name, w_cols, h_px, flag_byte, enc_bytes, raw_bytes).
    """
    png_files = sorted(src_dir.glob('*.png'))
    if not png_files:
        raise SystemExit(f'no .png files found in {src_dir}.')

    # Validate names up front so we don't write a partial output before
    # erroring on a bad filename.
    for p in png_files:
        if not NAME_RE.match(p.stem):
            raise SystemExit(
                f'{p.name}: stem {p.stem!r} is not a valid BeebAsm '
                f'identifier (need [A-Za-z_][A-Za-z0-9_]*).')

    lines: list[str] = []
    lines.append(rf'\\ Nevryon Ultimate -- {label}')
    lines.append(rf'\\ Auto-generated by tools/encode_sprites.py from {src_dir}/*.png.')
    lines.append(r'\\ Do not edit by hand -- edit the PNGs and re-run the encoder.')
    lines.append(r'\\')
    lines.append(rf'\\ {len(png_files)} sprite(s), column-major MODE 5 2bpp.')
    lines.append(r'\\')
    lines.append(r'\\ Compressed with sprite RLE scheme C (../docs/sprite_rle_notes.md),')
    lines.append(r'\\ with two remake-specific optimisations:')
    lines.append(r'\\   * stream byte b <  8: run code. count = b + 3 (3..10). Next byte')
    lines.append(r"\\                          is the run value, shipped RAW (NOT eor'd).")
    lines.append(r'\\   * stream byte b >= 8: literal. emit (b EOR flag_byte) once.')
    lines.append(r'\\   * FLAG_BYTE = FLAG << 3, picked so no source byte has top-5-bits')
    lines.append(r'\\     == FLAG. Carried per-sprite in <name>_rle_flag.')
    lines.append(r'\\   * Runs never cross a column boundary, so each .<name>_col_M label')
    lines.append(r'\\     starts a fresh decoder state for one column (= <name>_height bytes).')
    lines.append(r'\\   * Long runs (>10) are split into all-RLE pieces (3..10 each); the')
    lines.append(r'\\     decoder never falls into its slower literal path for run tails.')
    lines.append(r'\\   * Columns that encode to identical bytes share their stream: their')
    lines.append(r'\\     .<name>_col_M labels are stacked at the same address.')
    lines.append('')

    raw_total = 0
    enc_total = 0
    coalesced_total = 0
    stats: list[tuple[str, int, int, int, int, int]] = []

    for p in png_files:
        sprite, w_cols, h_px = load_png_to_sprite_bytes(p, palette)
        sprite_lines, flag_byte, enc_bytes, raw_bytes, coalesced = \
            emit_sprite(p.stem, sprite, w_cols, h_px)
        lines.extend(sprite_lines)
        raw_total += raw_bytes
        enc_total += enc_bytes
        coalesced_total += coalesced
        stats.append((p.stem, w_cols, h_px, flag_byte, enc_bytes, raw_bytes))

    pct = enc_total * 100 // raw_total if raw_total else 0
    lines.append(
        f'\\\\ ---- totals: {enc_total} encoded / {raw_total} raw '
        f'({pct}%); {coalesced_total} duplicate columns coalesced ----')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('\n'.join(lines) + '\n')
    return enc_total, raw_total, coalesced_total, stats


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description='Encode all PNG sprites in --src into one BeebAsm file.')
    ap.add_argument('--src', type=Path, required=True,
                    help='directory of .png files (top-level only, not recursive)')
    ap.add_argument('--out', type=Path, required=True,
                    help='output .6502 file path')
    ap.add_argument('--palette', required=True,
                    help='four colours, comma-separated. Each is either a '
                         '6-digit hex code (e.g. "ff0000") or a BBC physical '
                         'name: black/red/green/yellow/blue/magenta/cyan/white. '
                         'The first entry is pixel value 0.')
    ap.add_argument('--label', default=None,
                    help='label used in the output file header. Defaults to '
                         'the last two components of --src (e.g. "level1/tiles").')
    ap.add_argument('--expected-bytes', type=int, default=None,
                    help='if set, error out unless the encoded total equals N. '
                         'For build-script regression checks.')
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    palette = parse_palette(args.palette)

    if args.label is not None:
        label = args.label
    else:
        # e.g. assets/level1/tiles -> "level1/tiles"
        parts = args.src.parts[-2:] if len(args.src.parts) >= 2 else args.src.parts
        label = '/'.join(parts)

    enc_total, raw_total, coalesced, stats = encode_sprite_set(
        args.src, args.out, palette, label)

    pct = enc_total * 100 // raw_total if raw_total else 0
    print(f'wrote {args.out}')
    print(f'  {len(stats)} sprite(s), {enc_total} B encoded / {raw_total} B raw '
          f'({pct}%); {coalesced} duplicate columns coalesced')

    # Per-sprite table: <name>  <WxH>  flag=&XX  enc/raw (pct%)
    name_w = max((len(s[0]) for s in stats), default=4)
    for name, w_cols, h_px, flag_byte, enc_bytes, raw_bytes in stats:
        spct = enc_bytes * 100 // raw_bytes if raw_bytes else 0
        print(f'  {name:<{name_w}}  {w_cols}x{h_px:<2}  '
              f'flag=&{flag_byte:02X}  '
              f'{enc_bytes:>4}/{raw_bytes:<4}B ({spct:>3}%)')

    if args.expected_bytes is not None and enc_total != args.expected_bytes:
        raise SystemExit(
            f'encoded size {enc_total} != expected {args.expected_bytes}. '
            f'If you intentionally changed the artwork or the encoder, '
            f'update the --expected-bytes value in the caller.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
