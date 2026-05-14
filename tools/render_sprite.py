#!/usr/bin/env python3
"""Render BBC Micro column-major sprites as PNG.

Nevryon sprite-engine format (from $.CODE disassembly):
  - Each sprite is W byte-columns wide × H scanlines tall.
  - A byte-column is 4 pixels wide (1 MODE 5 byte = 4 pixels at 2 bpp).
  - Bytes are stored column-major: byte_index = col_idx * H + scanline.
  - On screen, the sprite occupies (4*W) pixels wide × H pixels tall.
  - The drawing routine increments Y through the destination screen,
    wrapping char-row every 8 scanlines (= advancing screen pointer by
    +320). The SOURCE just walks contiguously through W*H bytes.

This tool can render:
  - One sprite at a specific offset & dimensions
  - A grid of sprites of uniform size, scanning the file
  - A whole file dumped as one tall column-major sprite (debug view)

Usage:
  render_sprite.py FILE OUT.png --offset 0 --width 6 --height 22
  render_sprite.py FILE OUT.png --grid --width 4 --height 16 --cols 16
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import (decode_byte, DEFAULT_PALETTE, NEVRYON_GAME_PALETTE,
                           write_png)


def render_row_major(data: bytes, offset: int, width_cols: int,
                     height: int, palette=DEFAULT_PALETTE,
                     bg=(40, 40, 40)) -> tuple[bytes, int, int]:
    """Render one row-major sprite. Bytes are scanline-by-scanline:
    byte index = scanline * width_cols + col_idx. Common for MODE 5
    font glyphs."""
    px_w = width_cols * 4
    px_h = height
    img = bytearray(px_w * px_h * 3)
    for i in range(px_w * px_h):
        img[i * 3] = bg[0]
        img[i * 3 + 1] = bg[1]
        img[i * 3 + 2] = bg[2]
    for y in range(height):
        for c in range(width_cols):
            byte_off = offset + y * width_cols + c
            if byte_off >= len(data):
                continue
            pixels = decode_byte(data[byte_off])
            for p in range(4):
                col = palette[pixels[p]]
                x = c * 4 + p
                idx = (y * px_w + x) * 3
                img[idx] = col[0]
                img[idx + 1] = col[1]
                img[idx + 2] = col[2]
    return bytes(img), px_w, px_h


def render_column_major(data: bytes, offset: int, width_cols: int,
                        height: int, palette=DEFAULT_PALETTE,
                        bg=(40, 40, 40)) -> tuple[bytes, int, int]:
    """Render one column-major sprite. width_cols = number of 4-pixel byte
    columns. height = number of scanlines. Bytes are arranged as
    col_idx * height + scanline within the source."""
    px_w = width_cols * 4
    px_h = height
    img = bytearray(px_w * px_h * 3)
    # Fill bg
    for i in range(px_w * px_h):
        img[i * 3] = bg[0]
        img[i * 3 + 1] = bg[1]
        img[i * 3 + 2] = bg[2]

    for c in range(width_cols):
        for y in range(height):
            byte_off = offset + c * height + y
            if byte_off >= len(data):
                continue
            b = data[byte_off]
            pixels = decode_byte(b)
            for p in range(4):
                col = palette[pixels[p]]
                x = c * 4 + p
                idx = (y * px_w + x) * 3
                img[idx] = col[0]
                img[idx + 1] = col[1]
                img[idx + 2] = col[2]
    return bytes(img), px_w, px_h


def render_grid(data: bytes, offset: int, sprite_w_cols: int, sprite_h: int,
                cols: int, count: int | None = None, gap: int = 1,
                palette=DEFAULT_PALETTE,
                bg=(20, 20, 30), sep=(80, 80, 110)) -> tuple[bytes, int, int]:
    """Render `count` uniform sprites in a grid `cols` wide."""
    sprite_bytes = sprite_w_cols * sprite_h
    if count is None:
        count = max(0, (len(data) - offset) // sprite_bytes)

    rows = (count + cols - 1) // cols
    cell_w = sprite_w_cols * 4 + gap
    cell_h = sprite_h + gap
    img_w = cols * cell_w + gap
    img_h = rows * cell_h + gap

    img = bytearray(img_w * img_h * 3)
    for i in range(img_w * img_h):
        img[i * 3] = sep[0]
        img[i * 3 + 1] = sep[1]
        img[i * 3 + 2] = sep[2]

    for n in range(count):
        sx = n % cols
        sy = n // cols
        sprite_off = offset + n * sprite_bytes
        sub_rgb, sw, sh = render_column_major(data, sprite_off, sprite_w_cols,
                                              sprite_h, palette, bg)
        # blit
        for yy in range(sh):
            for xx in range(sw):
                px_x = gap + sx * cell_w + xx
                px_y = gap + sy * cell_h + yy
                src_idx = (yy * sw + xx) * 3
                dst_idx = (px_y * img_w + px_x) * 3
                img[dst_idx] = sub_rgb[src_idx]
                img[dst_idx + 1] = sub_rgb[src_idx + 1]
                img[dst_idx + 2] = sub_rgb[src_idx + 2]
    return bytes(img), img_w, img_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--offset", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--width", type=int, default=4,
                    help="sprite width in 4-pixel byte-columns")
    ap.add_argument("--height", type=int, default=16,
                    help="sprite height in scanlines")
    ap.add_argument("--grid", action="store_true",
                    help="render the rest of the file as a grid of uniform sprites")
    ap.add_argument("--cols", type=int, default=16,
                    help="number of sprite columns in --grid mode")
    ap.add_argument("--count", type=int, default=None,
                    help="number of sprites in --grid mode (default: fill file)")
    ap.add_argument("--game-palette", action="store_true")
    ap.add_argument("--scale", type=int, default=2, help="output upscale factor")
    args = ap.parse_args()

    pal = NEVRYON_GAME_PALETTE if args.game_palette else DEFAULT_PALETTE

    with open(args.input, "rb") as f:
        data = f.read()

    if args.grid:
        rgb, w, h = render_grid(data, args.offset, args.width, args.height,
                                args.cols, args.count, palette=pal)
    else:
        rgb, w, h = render_column_major(data, args.offset, args.width,
                                        args.height, palette=pal)

    if args.scale > 1:
        from PIL import Image
        im = Image.frombytes("RGB", (w, h), rgb).resize(
            (w * args.scale, h * args.scale), Image.NEAREST)
        im.save(args.output)
        print(f"wrote {args.output} ({w*args.scale}x{h*args.scale}, sprite {w}x{h})")
    else:
        write_png(args.output, rgb, w, h)
        print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
