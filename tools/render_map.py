#!/usr/bin/env python3
"""Render a Nevryon level map from LEVD1 (tile catalog) + LEVD2 or LEVD3
(column tables).

Decoded structure (from $.CODE disassembly at L13D1 and L127B):
  - Tile catalog: starts at &4F00 in LEVD1 (offset &500 in the file).
    Each tile is 4 byte-columns × 32 scanlines column-major
    = 128 bytes = 16 px wide × 32 px tall.
  - Map column tables in LEVD2 (loaded at &7380):
      &7F10 (file offset &B90): UPPER tile-id per column
      &7E10 (file offset &A90): LOWER tile-id per column
    Scroll column index `&80` ranges 0..&F0 (240 columns), wrapping at &F1.

The tile draw routine at L127B:
  - UPPER tile: drawn at screen char rows 0-3 (Y=&FF → row 0), with
    zp_sprite_dir_flag = 0 → sprite is rendered with the inner X
    counter starting from height-1 and decrementing. This is a
    *vertical flip* of the source bytes — the tile appears mirrored
    upside-down, used as a ceiling.
  - LOWER tile: drawn at screen char rows 16-19 (Y=&7F → row 16),
    with zp_sprite_dir_flag = 1 → normal forward rendering.
  - The 96-px gap between (rows 4-15) is the playable middle band
    where enemies, force-fields, the player ship and any per-column
    decoration sprites are drawn.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import (decode_byte, NEVRYON_GAME_PALETTE, DEFAULT_PALETTE,
                           palette_for_level, write_png)
from render_sprite import render_column_major


TILE_CATALOG_OFFSET = 0x500     # &4F00 - &4A00 (LEVD1 base)
TILE_WIDTH_COLS = 4              # 4 byte-columns = 16 pixels
TILE_HEIGHT = 32                  # scanlines
TILE_BYTES = TILE_WIDTH_COLS * TILE_HEIGHT  # 128

UPPER_TABLE_OFFSET = 0xB90       # &7F10 - &7380 (LEVD2 base)
LOWER_TABLE_OFFSET = 0xA90       # &7E10 - &7380

MAP_COLUMNS = 0xF0                # 240 columns; index wraps at &F1


PLAYFIELD_HEIGHT_PX = 20 * 8        # 160 px (MODE 5 playfield rows 0-19)
UPPER_TILE_Y = 0                     # screen row 0
LOWER_TILE_Y = 16 * 8                # screen row 16


def render_map(levd1: bytes, levd23: bytes, num_columns: int = MAP_COLUMNS,
               palette=NEVRYON_GAME_PALETTE,
               draw_grid: bool = False,
               playfield: bool = True) -> tuple[bytes, int, int]:
    """Render the full scrolling map by indexing tiles from levd1 with the
    upper/lower index tables from levd23.

    playfield=True (default): renders at full 160 px playfield height,
        with upper tile vertically mirrored at rows 0-3, lower tile
        normal at rows 16-19, and a 96 px gap between. This matches
        what the game actually draws.
    playfield=False: legacy compact mode — upper and lower tiles
        stacked, 64 px total. Useful for inspecting the raw tile
        sources without the gap.
    """
    px_per_col = TILE_WIDTH_COLS * 4  # 16 px wide per column
    map_w = num_columns * px_per_col
    map_h = PLAYFIELD_HEIGHT_PX if playfield else 2 * TILE_HEIGHT

    img = bytearray(map_w * map_h * 3)

    upper_table = levd23[UPPER_TABLE_OFFSET:UPPER_TABLE_OFFSET + num_columns]
    lower_table = levd23[LOWER_TABLE_OFFSET:LOWER_TABLE_OFFSET + num_columns]

    upper_y = UPPER_TILE_Y if playfield else 0
    lower_y = LOWER_TILE_Y if playfield else TILE_HEIGHT

    for col in range(num_columns):
        u_id = upper_table[col] if col < len(upper_table) else 0
        l_id = lower_table[col] if col < len(lower_table) else 0
        u_off = TILE_CATALOG_OFFSET + u_id * TILE_BYTES
        l_off = TILE_CATALOG_OFFSET + l_id * TILE_BYTES

        u_rgb, _, _ = render_column_major(levd1, u_off, TILE_WIDTH_COLS,
                                          TILE_HEIGHT, palette, bg=(0, 0, 0))
        l_rgb, _, _ = render_column_major(levd1, l_off, TILE_WIDTH_COLS,
                                          TILE_HEIGHT, palette, bg=(0, 0, 0))
        # Blit upper — vertically flipped (the engine renders it as a ceiling)
        for y in range(TILE_HEIGHT):
            src_y = TILE_HEIGHT - 1 - y
            for x in range(px_per_col):
                src_i = (src_y * px_per_col + x) * 3
                dst_x = col * px_per_col + x
                dst_y = upper_y + y
                dst_i = (dst_y * map_w + dst_x) * 3
                img[dst_i] = u_rgb[src_i]
                img[dst_i + 1] = u_rgb[src_i + 1]
                img[dst_i + 2] = u_rgb[src_i + 2]
        # Blit lower — normal orientation, at row 16 in playfield mode
        for y in range(TILE_HEIGHT):
            for x in range(px_per_col):
                src_i = (y * px_per_col + x) * 3
                dst_x = col * px_per_col + x
                dst_y = lower_y + y
                dst_i = (dst_y * map_w + dst_x) * 3
                img[dst_i] = l_rgb[src_i]
                img[dst_i + 1] = l_rgb[src_i + 1]
                img[dst_i + 2] = l_rgb[src_i + 2]

    if draw_grid:
        sep = (255, 255, 0)
        grid_rows = (upper_y + TILE_HEIGHT, lower_y) if playfield else (TILE_HEIGHT,)
        for y in (0, map_h - 1, *grid_rows):
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
    ap.add_argument("--level", type=int, default=1,
                    help="scenario 1-4 for palette selection")
    args = ap.parse_args()

    with open(args.levd1, "rb") as f:
        levd1 = f.read()
    with open(args.levd23, "rb") as f:
        levd23 = f.read()

    palette = palette_for_level(args.level)
    rgb, w, h = render_map(levd1, levd23, args.columns, palette,
                            draw_grid=args.grid)
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
