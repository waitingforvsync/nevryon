#!/usr/bin/env python3
"""Render the $.GRAPHIX sprite atlas.

The atlas at &3680-&48FF (file offsets 0x000-0x127F) contains many
sprites of varying dimensions, packed back-to-back with no header.
Sprite source addresses used by the engine come from:

  - The enemy pointer table in LEVD2 (slots 15, 16, 19 = &3700,
    &3780, &4360 — all 4×32 = 128-byte sprites).
  - Inline `LDA #lo / STA &1194 / LDA #hi / STA &1195` pairs in
    CODE / CODE2 / CODE3 that set up the sprite source for a
    specific decoration/effect plot. These give us the start
    addresses of additional sprites.

This tool takes a list of (start_addr, name, width_cols, height)
records, renders each as a column-major sprite, and lays them out
in a grid annotated with their address and label.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import (NEVRYON_GAME_PALETTE, NEVRYON_LOADER_PALETTE,
                           DEFAULT_PALETTE, write_png)
from render_sprite import render_column_major


# Known sprite entries in GRAPHIX. Each is (address, label, w_cols, h_lines).
# Addresses below are derived from scanning CODE/CODE2/CODE3 for
# `LDA #lo;STA &1194; LDA #hi;STA &1195` byte patterns and from the
# LEVD2 enemy pointer tables. Dimensions are best-effort: w/h not
# always recoverable from surrounding LDX/LDY immediates, so default
# to 4×32 (the standard enemy size) where unknown.
SPRITES = [
    (0x3680, "sprite_3680",     4, 32),  # first slot — purpose TBD
    (0x3700, "sprite_3700",     4, 32),  # enemy ptr slot 15 (shared)
    (0x3780, "sprite_3780",     4, 32),  # enemy ptr slot 16 (shared)
    (0x3800, "sprite_3800",     4, 32),  # implied by gap to next ref
    (0x3880, "sprite_3880",     4, 32),
    (0x3900, "sprite_3900",     4, 32),
    (0x3980, "sprite_3980",     4, 32),
    (0x3A00, "sprite_3A00",     4, 32),  # gap up to &3A28 — partial?
    (0x3A28, "sprite_3A28",     4, 32),  # CODE @ &27AC
    (0x3AA8, "sprite_3AA8",     4, 32),
    (0x3B28, "sprite_3B28",     4, 32),
    (0x3BA8, "sprite_3BA8",     2, 16),  # short — fills gap to &3BC0
    (0x3BC0, "sprite_3BC0",     4, 32),  # CODE2 @ &2D77
    (0x3C40, "sprite_3C40",     4, 32),
    (0x3CC0, "sprite_3CC0",     4, 32),
    (0x3D40, "sprite_3D40",     4, 32),
    (0x3DC0, "sprite_3DC0",     4, 32),
    (0x3E40, "sprite_3E40",     4, 32),
    (0x3EC0, "sprite_3EC0",     4, 32),
    (0x3F40, "sprite_3F40",     4, 32),
    (0x3FC0, "sprite_3FC0",     4, 32),
    (0x4040, "sprite_4040",     4, 32),
    (0x40C0, "sprite_40C0",     4, 32),
    (0x4140, "sprite_4140",     4, 32),  # CODE2 @ &2BF3 → 8×16
    (0x41C0, "sprite_41C0",     4, 32),
    (0x4240, "sprite_4240",     4, 32),
    (0x42C0, "sprite_42C0",     4, 32),
    (0x4340, "sprite_4340",     4, 32),
    (0x4360, "sprite_4360",     4, 32),  # enemy ptr slot 19
    (0x43E0, "sprite_43E0",     4, 32),
    (0x4460, "sprite_4460",     4, 32),
    (0x44E0, "sprite_44E0",     4, 32),
    (0x4560, "sprite_4560",     4, 32),
    (0x45E0, "sprite_45E0",     4, 32),
    (0x4660, "sprite_4660",     4, 32),
    (0x46E0, "sprite_46E0",     4, 32),
    (0x4760, "sprite_4760",     4, 32),
    (0x47E0, "sprite_47E0",     4, 32),
    (0x4860, "sprite_4860",     4, 32),
    (0x48E0, "sprite_48E0",     1,  8),  # very small — fills gap to &4900
]


def render_atlas(data: bytes, sprites: list, palette, cols: int = 8,
                 scale: int = 4, base: int = 0x3680):
    """Render all sprites in a grid. Each cell is sized to the largest
    sprite dim so smaller ones leave whitespace."""
    cell_w_px = max(s[2] * 4 for s in sprites)
    cell_h_px = max(s[3] for s in sprites)
    label_h = 9
    cell_w = cell_w_px + 4
    cell_h = cell_h_px + 4 + label_h

    rows = (len(sprites) + cols - 1) // cols
    img_w = cols * cell_w + 4
    img_h = rows * cell_h + 4

    buf = bytearray(img_w * img_h * 3)
    for i in range(img_w * img_h):
        buf[i * 3] = 24
        buf[i * 3 + 1] = 24
        buf[i * 3 + 2] = 36

    def blit(rgb, sw, sh, dx, dy):
        for y in range(sh):
            for x in range(sw):
                si = (y * sw + x) * 3
                di = ((dy + y) * img_w + (dx + x)) * 3
                buf[di] = rgb[si]
                buf[di + 1] = rgb[si + 1]
                buf[di + 2] = rgb[si + 2]

    for n, (addr, name, w, h) in enumerate(sprites):
        sx = n % cols
        sy = n // cols
        off = addr - base
        if off < 0 or off + w * h > len(data):
            continue
        rgb, sw, sh = render_column_major(data, off, w, h, palette,
                                           bg=(40, 0, 0))
        ox = 4 + sx * cell_w
        oy = 4 + sy * cell_h
        blit(rgb, sw, sh, ox, oy)

    from PIL import Image
    im = Image.frombytes("RGB", (img_w, img_h), bytes(buf))
    if scale > 1:
        im = im.resize((img_w * scale, img_h * scale), Image.NEAREST)
    return im


def render_strip(data: bytes, palette, height: int = 32, base: int = 0x3680):
    """Render the entire atlas as one tall-strip column-major image.
    Each byte-column becomes 4 px wide × `height` px tall. Sprite
    boundaries will appear as visible breaks in the pattern."""
    n_cols = len(data) // height
    rgb, w, h = render_column_major(data, 0, n_cols, height, palette,
                                     bg=(20, 0, 0))
    return rgb, w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--output-grid", default="work/graphix_atlas_grid.png")
    ap.add_argument("--output-strip", default="work/graphix_atlas_strip.png")
    args = ap.parse_args()

    data = open("extracted/$.GRAPHIX", "rb").read()
    # Render twice — once with lev1 game palette, once with loader palette
    # — since some sprites are level-specific and others are pre-game.
    atlas_data = data[:0x1280]  # exclude IRQ code + palette tables

    im = render_atlas(atlas_data, SPRITES, NEVRYON_GAME_PALETTE,
                       cols=8, scale=args.scale, base=0x3680)
    im.save(args.output_grid)
    print(f"wrote {args.output_grid} ({im.size})")

    # Strip view: each 32-px-tall column is one byte-column of the atlas.
    rgb, w, h = render_strip(atlas_data, NEVRYON_GAME_PALETTE,
                              height=32, base=0x3680)
    from PIL import Image
    im2 = Image.frombytes("RGB", (w, h), rgb).resize(
        (w * args.scale, h * args.scale), Image.NEAREST)
    im2.save(args.output_strip)
    print(f"wrote {args.output_strip} ({im2.size})")


if __name__ == "__main__":
    main()
