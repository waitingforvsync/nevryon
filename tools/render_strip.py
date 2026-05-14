#!/usr/bin/env python3
"""Render a raw byte stream as a MODE 5 'strip' — treating the bytes as a
linear sequence of 8-line-tall char cells.

This is useful for inspecting sprite/tile data where we don't yet know the
layout: render at various widths, look for vertical alignment of features.

Each char cell:
  - 8 bytes vertical (one per scanline)
  - 1 byte = 4 MODE 5 pixels (2 bpp)
  - so each cell renders as a 4-pixel × 8-line tile.

Width is given in cells. Bytes-per-row = 8 * width_cells.
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from render_screen import decode_byte, DEFAULT_PALETTE, NEVRYON_GAME_PALETTE, write_png


def render_strip(data: bytes, width_cells: int = 32, palette=DEFAULT_PALETTE,
                 grid: bool = False) -> tuple[bytes, int, int]:
    cells_per_row = width_cells
    bytes_per_row = cells_per_row * 8
    num_rows = (len(data) + bytes_per_row - 1) // bytes_per_row

    width_px = cells_per_row * 4
    height_px = num_rows * 8
    img = bytearray(width_px * height_px * 3)

    for row in range(num_rows):
        for cx in range(cells_per_row):
            for sub in range(8):
                off = row * bytes_per_row + cx * 8 + sub
                if off >= len(data):
                    continue
                b = data[off]
                pix = decode_byte(b)
                y = row * 8 + sub
                x_base = cx * 4
                for p in range(4):
                    col = palette[pix[p]]
                    idx = (y * width_px + x_base + p) * 3
                    img[idx] = col[0]
                    img[idx + 1] = col[1]
                    img[idx + 2] = col[2]
    if grid:
        # Draw faint cell separators (every 1 cell = every 4 px horiz, every 8 px vert)
        sep = (50, 50, 80)
        for y in range(0, height_px, 8):
            for x in range(width_px):
                idx = (y * width_px + x) * 3
                # only draw on otherwise-black cells to avoid obscuring data
                if img[idx] == 0 and img[idx + 1] == 0 and img[idx + 2] == 0:
                    img[idx] = sep[0]
                    img[idx + 1] = sep[1]
                    img[idx + 2] = sep[2]
        for x in range(0, width_px, 4):
            for y in range(height_px):
                idx = (y * width_px + x) * 3
                if img[idx] == 0 and img[idx + 1] == 0 and img[idx + 2] == 0:
                    img[idx] = sep[0]
                    img[idx + 1] = sep[1]
                    img[idx + 2] = sep[2]

    return bytes(img), width_px, height_px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--width", type=int, default=32,
                    help="strip width in 4-pixel cells (default 32 → 128 px)")
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--game-palette", action="store_true",
                    help="use Nevryon in-game palette (red/cyan/white) instead of default")
    args = ap.parse_args()

    pal = NEVRYON_GAME_PALETTE if args.game_palette else DEFAULT_PALETTE

    with open(args.input, "rb") as f:
        data = f.read()
    data = data[args.offset:]
    rgb, w, h = render_strip(data, args.width, palette=pal, grid=args.grid)
    write_png(args.output, rgb, w, h)
    print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
