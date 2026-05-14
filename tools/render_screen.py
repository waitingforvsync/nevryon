#!/usr/bin/env python3
"""Render a BBC Micro MODE 1 or MODE 5 screen buffer to a PNG (or PPM if
Pillow is unavailable).

Pixel encoding (BBC Micro MODE 1/5):
  Screen RAM is laid out as char cells. A char cell is 8 scanlines tall.
  Each row of cells occupies a contiguous block of memory:
    cell_row_bytes = bytes_per_line * 8
  Cells run left-to-right; within a cell the 8 scanlines are stored as
  8 sequential bytes (cell row 0 first).

MODE 1: 320 x 256, 4 colours, 2 bpp, 80 bytes/line, 40 char cells/row.
        Each char cell is 2 bytes wide.
MODE 5: 160 x 256, 4 colours, 2 bpp, 40 bytes/line, 20 char cells/row.
        Each char cell is 1 byte wide.

Pixel bit layout within a byte (4 pixels per byte, both MODE 1 and 5):
  Pixel n (left-to-right, n = 0..3) uses:
    bit (7 - n)  → high colour bit
    bit (3 - n)  → low  colour bit
  So pixel 0 is bits 7,3; pixel 1 is bits 6,2; pixel 2 is bits 5,1;
     pixel 3 is bits 4,0.
"""

from __future__ import annotations

import argparse
import os
import sys


# Default BBC 4-colour logical-to-physical palette used by MODE 1/5 at
# power-on: 0=black, 1=red, 2=yellow, 3=white. This is good for first-pass
# rendering; later we'll override per-game.
DEFAULT_PALETTE = [
    (0, 0, 0),        # 0 black
    (255, 0, 0),      # 1 red
    (255, 255, 0),    # 2 yellow
    (255, 255, 255),  # 3 white
]


# BBC physical colours (8-colour set used by MODE 1/5 VDU 19)
BBC_PHYSICAL = [
    (0, 0, 0),        # 0 black
    (255, 0, 0),      # 1 red
    (0, 255, 0),      # 2 green
    (255, 255, 0),    # 3 yellow
    (0, 0, 255),      # 4 blue
    (255, 0, 255),    # 5 magenta
    (0, 255, 255),    # 6 cyan
    (255, 255, 255),  # 7 white
]


# MODE 2's 16-colour set: 0-7 are the solid BBC physical colours, 8-15
# are flashing colours that alternate between the first 8 and their
# negative. For a static image we just render flashing colours as their
# "first-phase" colour (which is identical to the corresponding base
# colour 0-7).
MODE2_DEFAULT_PALETTE = BBC_PHYSICAL + BBC_PHYSICAL


def palette_from_mapping(logical_to_physical: dict[int, int]) -> list[tuple[int, int, int]]:
    pal = list(DEFAULT_PALETTE)
    for logical, physical in logical_to_physical.items():
        pal[logical] = BBC_PHYSICAL[physical]
    return pal


# Nevryon in-game palettes — one per scenario. The mechanism:
#
# A split-screen palette IRQ in GRAPHIX (irq_palette_split at &4900)
# writes &493F[0..11] to the Video ULA palette latch (&FE21) at vsync
# (top-half/playfield palette) and &494F[0..11] mid-frame at a User
# VIA T1 IRQ (bottom-half/scoreboard palette).
#
# Per-scenario palette override lives in Loader2 BASIC (lines 940-1200):
#   PROCLV12 (L%=1,2): no-op  → use the lev1 palette shipped in GRAPHIX
#   PROCL34  (L%=3,4): POKEs DATA from line 1160 → blue/cyan
#   PROCL56  (L%=5,6): POKEs DATA from line 1180 → red/green
#   PROCL78  (L%=7,8): POKEs DATA from line 1200 → red/magenta
# Each PROC runs `FOR T%=0 TO 15: READ T%?&493F: NEXT` to fill the
# top palette table before Loader3 hands control to the game CODE.
#
# MODE 5 effective mapping: pixel value V (0..3) selects palette
# latch entry E where E = [0, 3, 12, 15][V] (the BBC ULA bit-
# replicates the 2-bit pixel into a 4-bit palette index). So the four
# MODE 5 "logical" colors correspond to palette[0,3,12,15]; entry 0
# is always black, entry 15 is always white, and entries 3 and 12
# carry the scenario-specific primary and secondary colors.
NEVRYON_LEVEL_PALETTES = {
    1: palette_from_mapping({0: 0, 1: 1, 2: 3, 3: 7}),   # red/yellow/white
    2: palette_from_mapping({0: 0, 1: 4, 2: 6, 3: 7}),   # blue/cyan/white
    3: palette_from_mapping({0: 0, 1: 1, 2: 2, 3: 7}),   # red/green/white
    4: palette_from_mapping({0: 0, 1: 1, 2: 5, 3: 7}),   # red/magenta/white
}

# Default to scenario 1 for tools that don't pick a level
NEVRYON_GAME_PALETTE = NEVRYON_LEVEL_PALETTES[1]

# Loader-screen palette (Loader2 line 990 sets logical 2 to physical 6
# = cyan; used by OPSC, scoreboard, title etc. before gameplay).
NEVRYON_LOADER_PALETTE = palette_from_mapping({0: 0, 1: 1, 2: 6, 3: 7})


def palette_for_level(level: int) -> list[tuple[int, int, int]]:
    """Return the in-game MODE 5 palette for the given scenario (1-4)."""
    return NEVRYON_LEVEL_PALETTES[level]


def decode_byte(b: int) -> list[int]:
    """MODE 1/5: return the 4 logical colours (0..3) for one byte."""
    out = []
    for n in range(4):
        hi = (b >> (7 - n)) & 1
        lo = (b >> (3 - n)) & 1
        out.append((hi << 1) | lo)
    return out


def decode_byte_mode2(b: int) -> list[int]:
    """MODE 2: 4 bpp = 2 pixels per byte. Pixel n (n=0,1) uses bits
    (7-n), (5-n), (3-n), (1-n) — the BBC's interleaved layout extended
    to 4 bits.
    """
    out = []
    for n in range(2):
        c3 = (b >> (7 - n)) & 1
        c2 = (b >> (5 - n)) & 1
        c1 = (b >> (3 - n)) & 1
        c0 = (b >> (1 - n)) & 1
        out.append((c3 << 3) | (c2 << 2) | (c1 << 1) | c0)
    return out


def render_mode5(data: bytes, width_chars: int = 20, height_chars: int = 32,
                 palette=DEFAULT_PALETTE) -> bytes:
    """Render raw MODE 5 buffer, return RGB pixel bytes (row-major).

    MODE 5: 160px × 256px, char cell = 2 bytes wide (8 pixels), 8 tall.
    Same memory layout as MODE 1, just half the horizontal byte count.
    """
    width_px = width_chars * 8        # 160
    height_px = height_chars * 8      # 256
    cell_bytes_x = 2                   # 2 bytes per char-cell scanline
    bytes_per_line = width_chars * cell_bytes_x  # 40
    bytes_per_char_row = bytes_per_line * 8       # 320

    img = bytearray(width_px * height_px * 3)
    for cy in range(height_chars):
        for sub in range(8):
            for cx in range(width_chars):
                # Each char cell is 16 bytes: 8 for left column, 8 for right
                left_off = cy * bytes_per_char_row + cx * 16 + sub
                right_off = left_off + 8
                for half_idx, byte_off in enumerate((left_off, right_off)):
                    if byte_off >= len(data):
                        continue
                    b = data[byte_off]
                    pixels = decode_byte(b)
                    y = cy * 8 + sub
                    x_base = cx * 8 + half_idx * 4
                    for px in range(4):
                        col = pixels[px]
                        r, g, bl = palette[col]
                        idx = (y * width_px + x_base + px) * 3
                        img[idx] = r
                        img[idx + 1] = g
                        img[idx + 2] = bl
    return bytes(img), width_px, height_px


def render_mode1(data: bytes, width_chars: int = 40, height_chars: int = 32,
                 palette=DEFAULT_PALETTE) -> bytes:
    """Render raw MODE 1 buffer, return RGB pixel bytes (row-major).

    MODE 1: 320px × 256px, char cell = 2 bytes wide (8 pixels), 8 tall.
    """
    width_px = width_chars * 8        # 320
    height_px = height_chars * 8      # 256
    cell_bytes_x = 2                  # 2 bytes per char-cell row
    bytes_per_line = width_chars * cell_bytes_x  # 80

    img = bytearray(width_px * height_px * 3)
    for cy in range(height_chars):
        for sub in range(8):
            for cx in range(width_chars):
                # 16 bytes per char cell: 8 lines × 2 bytes
                cell_off = cy * bytes_per_line * 8 + cx * (cell_bytes_x * 8)
                line_off = cell_off + sub * cell_bytes_x  # nope; off-by-arrangement
                # Actually the BBC layout puts 8 scanlines of left half byte
                # contiguous, then 8 scanlines of right half byte. So:
                left_off = cy * bytes_per_line * 8 + cx * 16 + sub
                right_off = left_off + 8
                for half_idx, byte_off in enumerate((left_off, right_off)):
                    if byte_off >= len(data):
                        continue
                    b = data[byte_off]
                    pixels = decode_byte(b)
                    y = cy * 8 + sub
                    x_base = cx * 8 + half_idx * 4
                    for px in range(4):
                        col = pixels[px]
                        r, g, bl = palette[col]
                        idx = (y * width_px + x_base + px) * 3
                        img[idx] = r
                        img[idx + 1] = g
                        img[idx + 2] = bl
    return bytes(img), width_px, height_px


def render_mode2(data: bytes, width_chars: int = 20, height_chars: int = 32,
                 palette=MODE2_DEFAULT_PALETTE) -> tuple[bytes, int, int]:
    """Render raw MODE 2 buffer to RGB pixel bytes.

    MODE 2: 160 px × 256 px, 16 colours, 4 bpp.
            80 bytes per scanline, 2 pixels per byte.
            Char cell = 8 px wide (= 4 bytes per scanline) × 8 lines tall
            = 32 bytes per cell. Memory layout: each cell stores its 8
            scanlines as 4 sequential 8-byte groups (left-to-right within
            each scanline), with the 8-line groupings being contiguous per
            byte-column position. Concretely: each cell is 4 byte-columns,
            and the 32 bytes are arranged as 8 bytes per byte-column,
            byte-columns laid out left-to-right within the cell.
    """
    width_px = width_chars * 8
    height_px = height_chars * 8
    cell_bytes_x = 4
    bytes_per_line = width_chars * cell_bytes_x      # = 80 for 20 chars
    bytes_per_char_row = bytes_per_line * 8           # = 640

    img = bytearray(width_px * height_px * 3)
    for cy in range(height_chars):
        for sub in range(8):
            for cx in range(width_chars):
                cell_base = cy * bytes_per_char_row + cx * 32
                # 4 byte-columns within a cell; each byte-column is 8 bytes
                for bc in range(cell_bytes_x):
                    byte_off = cell_base + bc * 8 + sub
                    if byte_off >= len(data):
                        continue
                    pixels = decode_byte_mode2(data[byte_off])
                    y = cy * 8 + sub
                    x_base = cx * 8 + bc * 2
                    for p in range(2):
                        col = palette[pixels[p]]
                        idx = (y * width_px + x_base + p) * 3
                        img[idx] = col[0]
                        img[idx + 1] = col[1]
                        img[idx + 2] = col[2]
    return bytes(img), width_px, height_px


def write_ppm(path: str, rgb: bytes, w: int, h: int):
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
        f.write(rgb)


def write_png(path: str, rgb: bytes, w: int, h: int):
    try:
        from PIL import Image
    except ImportError:
        # Fallback: write PPM with .png extension swapped
        alt = os.path.splitext(path)[0] + ".ppm"
        write_ppm(alt, rgb, w, h)
        print(f"(no Pillow; wrote {alt} instead)", file=sys.stderr)
        return
    img = Image.frombytes("RGB", (w, h), rgb)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="raw BBC screen buffer")
    ap.add_argument("output", help="output PNG path")
    ap.add_argument("--mode", type=int, choices=[1, 2, 5], default=5)
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=0,
                    help="byte offset in input to start at")
    ap.add_argument("--width-chars", type=int, default=None,
                    help="width in char cells (default 20 for M5, 40 for M1)")
    ap.add_argument("--height-chars", type=int, default=None,
                    help="height in char cells (default 32)")
    args = ap.parse_args()

    with open(args.input, "rb") as f:
        data = f.read()
    data = data[args.offset:]

    if args.mode == 5:
        w = args.width_chars or 20
        h = args.height_chars or 32
        rgb, wpx, hpx = render_mode5(data, w, h)
    elif args.mode == 2:
        w = args.width_chars or 20
        h = args.height_chars or 32
        rgb, wpx, hpx = render_mode2(data, w, h)
    else:
        w = args.width_chars or 40
        h = args.height_chars or 32
        rgb, wpx, hpx = render_mode1(data, w, h)

    write_png(args.output, rgb, wpx, hpx)
    print(f"wrote {args.output} ({wpx}x{hpx})")


if __name__ == "__main__":
    main()
