#!/usr/bin/env python3
"""Render a full level summary: map strip + enemy sprites pinned at their
spawn columns. One image per scenario.

LEVD2 spawn data:
  &7B00 + i  : spawn-column   (sorted ascending; &FF = terminator)
  &7B80 + i  : attribute byte (bit 7 = mirror; low 5 bits = sprite-index
                              into the enemy-ptr table at &7A80/&7AC0;
                              bits 5-6 carry type flags — bit 6 (val &40)
                              and type-byte &07 indicate force-fields)

We render:
  - The full 240-column map strip (16 px wide per col, 64 px tall).
  - Above and below the strip, a "lane" annotated with each enemy
    sprite drawn at its spawn column position.
  - Force-field markers ("‖") for any attribute byte where the type
    field marks a force field.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE, write_png
from render_sprite import render_column_major
from render_map import render_map, MAP_COLUMNS
from extract_enemies import resolve_addr, ADDRESS_REGIONS, load_files


ENEMY_W_COLS = 4
ENEMY_H = 32
MAP_PX_PER_COL = ENEMY_W_COLS * 4   # 16 px per column


def render_summary(level: int, scale: int = 2, both_halves: bool = True):
    files = load_files(level)
    levd2 = files["LEVD2"]
    try:
        levd3 = open(f"extracted/{level}.LEVD3", "rb").read()
    except FileNotFoundError:
        levd3 = None

    # Map from LEVD1 + LEVD2 tables
    map_rgb, map_w, map_h = render_map(files["LEVD1"], levd2, MAP_COLUMNS,
                                        NEVRYON_GAME_PALETTE)

    # Enemy pointer table (used by both halves)
    table_lo = levd2[0x700:0x740]
    table_hi = levd2[0x740:0x780]

    def get_enemy_sprite(idx: int):
        addr = (table_hi[idx] << 8) | table_lo[idx]
        if addr == 0:
            return None
        resolved = resolve_addr(addr, files)
        if resolved is None:
            return None
        data, off = resolved
        rgb, w, h = render_column_major(data, off, ENEMY_W_COLS, ENEMY_H,
                                        NEVRYON_GAME_PALETTE,
                                        bg=(20, 20, 30))
        return rgb, w, h

    enemy_lane_h = ENEMY_H + 8
    img_w = map_w
    # layout: top lane = LEVD2 spawns, map, bottom lane = LEVD3 spawns
    img_h = enemy_lane_h + map_h + enemy_lane_h + 20  # +20 for label strip

    img = bytearray(img_w * img_h * 3)
    # Background dark grey
    for i in range(img_w * img_h):
        img[i * 3] = 20
        img[i * 3 + 1] = 20
        img[i * 3 + 2] = 28

    def blit(rgb: bytes, w: int, h: int, dx: int, dy: int):
        for yy in range(h):
            for xx in range(w):
                si = (yy * w + xx) * 3
                px = dx + xx
                py = dy + yy
                if px < 0 or py < 0 or px >= img_w or py >= img_h:
                    continue
                di = (py * img_w + px) * 3
                img[di] = rgb[si]
                img[di + 1] = rgb[si + 1]
                img[di + 2] = rgb[si + 2]

    # Blit the map in the middle
    map_y = enemy_lane_h
    blit(map_rgb, map_w, map_h, 0, map_y)

    def draw_spawns(spawn_data: bytes, attr_data: bytes, lane_y: int,
                    label: str, label_y: int):
        # Pre-render label as block letters? Skip — just colored marker.
        # Iterate spawn schedule.
        for i in range(len(spawn_data)):
            col = spawn_data[i]
            if col == 0xFF:
                break
            attr = attr_data[i] if i < len(attr_data) else 0
            sprite_idx = attr & 0x1F
            mirror = (attr & 0x80) != 0
            type_field = (attr >> 5) & 0x03  # bits 5-6

            # Force-field detection: low 5 bits == 7 OR type bits set?
            # We tentatively treat sprite_idx == 7 as force-field, since
            # the disasm dispatch at L22D6 keys on a separate "type" byte
            # that we haven't fully identified yet. Try the simple test.
            is_force_field = (sprite_idx == 0x07)

            x = col * MAP_PX_PER_COL
            if is_force_field:
                # Draw a yellow vertical bar marker
                for yy in range(ENEMY_H):
                    for xx in range(8):
                        px = x + xx
                        py = lane_y + yy
                        if 0 <= px < img_w and 0 <= py < img_h:
                            di = (py * img_w + px) * 3
                            img[di] = 255
                            img[di + 1] = 255
                            img[di + 2] = 0
                continue

            spr = get_enemy_sprite(sprite_idx)
            if spr is None:
                # Unknown -> magenta pin
                for yy in range(4):
                    for xx in range(4):
                        px = x + xx
                        py = lane_y + yy
                        if 0 <= px < img_w:
                            di = (py * img_w + px) * 3
                            img[di] = 255
                            img[di + 1] = 0
                            img[di + 2] = 255
                continue
            rgb, w, h = spr
            blit(rgb, w, h, x, lane_y)

    # Top lane: LEVD2 spawns
    draw_spawns(levd2[0x780:0x800], levd2[0x800:0x880], 0, "first half", 0)
    # Bottom lane: LEVD3 spawns (when available)
    if levd3 is not None and len(levd3) >= 0x880:
        draw_spawns(levd3[0x780:0x800], levd3[0x800:0x880],
                    map_y + map_h, "second half", map_y + map_h)
    else:
        draw_spawns(b"\xFF", b"\x00", map_y + map_h, "n/a", map_y + map_h)

    if scale > 1:
        from PIL import Image
        im = Image.frombytes("RGB", (img_w, img_h), bytes(img)).resize(
            (img_w * scale, img_h * scale), Image.NEAREST)
        return im, img_w * scale, img_h * scale
    else:
        return bytes(img), img_w, img_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, required=True,
                    help="scenario number 1..4")
    ap.add_argument("--output", "-o", required=True)
    ap.add_argument("--scale", type=int, default=1)
    args = ap.parse_args()

    result = render_summary(args.level, args.scale)
    if args.scale > 1:
        im, w, h = result
        im.save(args.output)
    else:
        rgb, w, h = result
        write_png(args.output, rgb, w, h)
    print(f"wrote {args.output} ({w}x{h})")


if __name__ == "__main__":
    main()
