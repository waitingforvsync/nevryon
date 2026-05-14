#!/usr/bin/env python3
"""Render a Nevryon level map from LEVD1 (tile catalog) + LEVD2 or LEVD3
(column tables).

Decoded structure (from $.CODE disassembly at L13D1):
  - Tile catalog: starts at &4F00 in LEVD1 (offset &500 in the file).
    Each tile is 4 byte-columns × 32 scanlines column-major
    = 128 bytes = 16 px wide × 32 px tall.
  - Map column tables in LEVD2 (loaded at &7380):
      &7F10 (file offset &B90): UPPER tile-id per column
      &7E10 (file offset &A90): LOWER tile-id per column
    Scroll column index `&80` ranges 0..&F0 (240 columns), wrapping at &F1.

The drawing routine at L13D1 walks sprite_src forward by &80 bytes
`(tile_id + 1)` times — i.e. tile_id 0 → tile at &4F00, tile_id 1 → &4F80,
tile_id 2 → &5000, etc. Tile_id N picks tile at offset &500 + N * &80
within LEVD1.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import (decode_byte, NEVRYON_GAME_PALETTE, DEFAULT_PALETTE,
                           write_png)
from render_sprite import render_column_major


TILE_CATALOG_OFFSET = 0x500     # &4F00 - &4A00 (LEVD1 base)
TILE_WIDTH_COLS = 4              # 4 byte-columns = 16 pixels
TILE_HEIGHT = 32                  # scanlines
TILE_BYTES = TILE_WIDTH_COLS * TILE_HEIGHT  # 128

UPPER_TABLE_OFFSET = 0xB90       # &7F10 - &7380 (LEVD2 base)
LOWER_TABLE_OFFSET = 0xA90       # &7E10 - &7380

MAP_COLUMNS = 0xF0                # 240 columns; index wraps at &F1


def render_map(levd1: bytes, levd23: bytes, num_columns: int = MAP_COLUMNS,
               palette=NEVRYON_GAME_PALETTE,
               draw_grid: bool = False) -> tuple[bytes, int, int]:
    """Render the full scrolling map by indexing tiles from levd1 with the
    upper/lower index tables from levd23."""
    px_per_col = TILE_WIDTH_COLS * 4  # 16 px wide per column
    map_w = num_columns * px_per_col
    map_h = 2 * TILE_HEIGHT            # upper + lower tile stacked = 64 px

    img = bytearray(map_w * map_h * 3)

    upper_table = levd23[UPPER_TABLE_OFFSET:UPPER_TABLE_OFFSET + num_columns]
    lower_table = levd23[LOWER_TABLE_OFFSET:LOWER_TABLE_OFFSET + num_columns]

    for col in range(num_columns):
        u_id = upper_table[col] if col < len(upper_table) else 0
        l_id = lower_table[col] if col < len(lower_table) else 0
        u_off = TILE_CATALOG_OFFSET + u_id * TILE_BYTES
        l_off = TILE_CATALOG_OFFSET + l_id * TILE_BYTES

        u_rgb, _, _ = render_column_major(levd1, u_off, TILE_WIDTH_COLS,
                                          TILE_HEIGHT, palette, bg=(0, 0, 0))
        l_rgb, _, _ = render_column_major(levd1, l_off, TILE_WIDTH_COLS,
                                          TILE_HEIGHT, palette, bg=(0, 0, 0))
        # Blit upper
        for y in range(TILE_HEIGHT):
            for x in range(px_per_col):
                src_i = (y * px_per_col + x) * 3
                dst_x = col * px_per_col + x
                dst_y = y
                dst_i = (dst_y * map_w + dst_x) * 3
                img[dst_i] = u_rgb[src_i]
                img[dst_i + 1] = u_rgb[src_i + 1]
                img[dst_i + 2] = u_rgb[src_i + 2]
        # Blit lower (stacked below upper)
        for y in range(TILE_HEIGHT):
            for x in range(px_per_col):
                src_i = (y * px_per_col + x) * 3
                dst_x = col * px_per_col + x
                dst_y = TILE_HEIGHT + y
                dst_i = (dst_y * map_w + dst_x) * 3
                img[dst_i] = l_rgb[src_i]
                img[dst_i + 1] = l_rgb[src_i + 1]
                img[dst_i + 2] = l_rgb[src_i + 2]

    if draw_grid:
        sep = (255, 255, 0)
        for y in (0, TILE_HEIGHT, map_h - 1):
            for x in range(map_w):
                idx = (y * map_w + x) * 3
                img[idx] = sep[0]
                img[idx + 1] = sep[1]
                img[idx + 2] = sep[2]
        for col in range(num_columns + 1):
            x = col * px_per_col
            if x >= map_w:
                continue
            for y in range(map_h):
                idx = (y * map_w + x) * 3
                # Only mark every 8 columns to avoid clutter
                if col % 8 == 0:
                    img[idx] = sep[0]
                    img[idx + 1] = sep[1]
                    img[idx + 2] = sep[2]

    return bytes(img), map_w, map_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("levd1", help="path to N.LEVD1")
    ap.add_argument("levd23", help="path to N.LEVD2 or N.LEVD3")
    ap.add_argument("--output", "-o", required=True)
    ap.add_argument("--columns", type=int, default=MAP_COLUMNS)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--grid", action="store_true")
    args = ap.parse_args()

    with open(args.levd1, "rb") as f:
        levd1 = f.read()
    with open(args.levd23, "rb") as f:
        levd23 = f.read()

    rgb, w, h = render_map(levd1, levd23, args.columns, draw_grid=args.grid)
    if args.scale > 1:
        from PIL import Image
        im = Image.frombytes("RGB", (w, h), rgb).resize(
            (w * args.scale, h * args.scale), Image.NEAREST)
        im.save(args.output)
        print(f"wrote {args.output} ({w*args.scale}x{h*args.scale}, map {w}x{h})")
    else:
        write_png(args.output, rgb, w, h)
        print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
