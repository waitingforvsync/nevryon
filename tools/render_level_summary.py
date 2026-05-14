#!/usr/bin/env python3
"""Render a full level summary: 160-px playfield strip with mirrored
upper tiles, gap, lower tiles, and enemy sprites pinned at their
spawn columns and Y-rows.

LEVD2 spawn data (decoded from CODE.beebasm spawn_check_step at L208A):
  &7B00 + i  : spawn-column   (sorted ascending; &FF = terminator)
  &7B80 + i  : attribute byte
    - bits 0-4: type (dispatched by enemy_type_dispatch L22B2)
                7 = force-field (procedural via LFSR + sideways ROM)
                others: index into &7A80/&7AC0 sprite ptr table
    - bits 5-6: Y row class — 0=&DF, 1=&BF, 2=&9F, 3=&7F
                (after calc_screen_addr inversion → char rows 4, 8, 12, 16)
    - bit 7:    VERTICAL flip flag — drives zp_sprite_dir_flag via
                &206E,X = ~bit7. Used to pair top/bottom decoration
                sprites (e.g. arch curves hang from ceiling = flipped;
                their floor counterparts at y_row=2 use the same
                sprite data un-flipped).

We produce two stacked strips per level:
  - Top half:    LEVD2 spawns over the LEVD2 map
  - Bottom half: LEVD3 spawns over the LEVD3 map (when 4.LEVD3 has its
                 own map tables, or LEVD2's tables if LEVD3 only
                 overlays enemies — true for scenarios 1-3)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE, palette_for_level, write_png
from render_sprite import render_column_major
from render_map import (render_map, MAP_COLUMNS, PLAYFIELD_HEIGHT_PX,
                        TILE_HEIGHT)
from extract_enemies import resolve_addr, ADDRESS_REGIONS, load_files


ENEMY_W_COLS = 4
ENEMY_H = 32
MAP_PX_PER_COL = ENEMY_W_COLS * 4   # 16 px per column

# Per-spawn Y row → top-of-sprite Y in pixels (calc_screen_addr inverts
# the raw Y byte before turning it into a char-row index).
# raw Y bytes are &DF, &BF, &9F, &7F → inverted: &20, &40, &60, &80
# → char rows 4, 8, 12, 16 → pixel Y 32, 64, 96, 128.
Y_ROW_TO_PX = {0: 32, 1: 64, 2: 96, 3: 128}


def render_summary(level: int, scale: int = 2, both_halves: bool = True):
    files = load_files(level)
    levd2 = files["LEVD2"]
    try:
        levd3 = open(f"extracted/{level}.LEVD3", "rb").read()
    except FileNotFoundError:
        levd3 = None

    palette = palette_for_level(level)

    # Map from LEVD1 + LEVD2 tables (playfield mode, 160 px tall)
    map_rgb, map_w, map_h = render_map(files["LEVD1"], levd2, MAP_COLUMNS,
                                        palette,
                                        playfield=True)

    # LEVD3 may have its own map tables — for 4.LEVD3 it does
    # (3200 bytes, full overlay). For 1-3 LEVD3 it's only 2176 bytes,
    # leaves &7E10/&7F10 from LEVD2 untouched. Choose source accordingly.
    map_rgb_3 = None
    if levd3 is not None and len(levd3) >= 0xC80:
        # 3200-byte LEVD3 covers map tables too
        map_rgb_3, _, _ = render_map(files["LEVD1"], levd3, MAP_COLUMNS,
                                      palette,
                                      playfield=True)
    elif levd3 is not None:
        # Reuse LEVD2 map for the bottom strip
        map_rgb_3 = map_rgb

    # Enemy pointer table — comes from whichever overlay is active
    def get_sprite_factory(table_lo, table_hi, ref_files):
        def get(idx: int):
            if idx >= len(table_lo):
                return None
            addr = (table_hi[idx] << 8) | table_lo[idx]
            if addr == 0:
                return None
            resolved = resolve_addr(addr, ref_files)
            if resolved is None:
                return None
            data, off = resolved
            rgb, w, h = render_column_major(data, off, ENEMY_W_COLS, ENEMY_H,
                                            palette,
                                            bg=(20, 20, 30))
            return rgb, w, h
        return get

    get_levd2 = get_sprite_factory(levd2[0x700:0x740], levd2[0x740:0x780],
                                   files)

    # For LEVD3, switch the "LEVD2" file in the resolve dict to LEVD3 so
    # &7380-&7BFF pointers resolve against the LEVD3 enemy graphics.
    if levd3 is not None:
        files_l3 = dict(files)
        files_l3["LEVD2"] = levd3
        get_levd3 = get_sprite_factory(levd3[0x700:0x740], levd3[0x740:0x780],
                                       files_l3)
    else:
        get_levd3 = None

    img_w = map_w
    strip_h = map_h  # 160 px playfield height
    gap_h = 12       # gap between top and bottom strips
    img_h = strip_h + gap_h + strip_h if levd3 is not None else strip_h

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

    # Blit the top map strip
    blit(map_rgb, map_w, map_h, 0, 0)
    # Blit the bottom map strip (LEVD3) if present
    bottom_y = strip_h + gap_h
    if levd3 is not None and map_rgb_3 is not None:
        blit(map_rgb_3, map_w, map_h, 0, bottom_y)

    def draw_spawns(spawn_data: bytes, attr_data: bytes, strip_top: int,
                    get_sprite):
        for i in range(len(spawn_data)):
            col = spawn_data[i]
            if col == 0xFF:
                break
            attr = attr_data[i] if i < len(attr_data) else 0
            type_field = attr & 0x1F
            y_row = (attr >> 5) & 0x03
            v_flip = (attr & 0x80) != 0   # bit 7 → ~zp_sprite_dir_flag

            is_force_field = (type_field == 0x07)
            sprite_idx = type_field

            x = col * MAP_PX_PER_COL
            y_offset = Y_ROW_TO_PX.get(y_row, 32)
            y = strip_top + y_offset

            if is_force_field:
                # 2-byte-col × 32-line vertical strip (= 8 px × 32 px)
                # rendered as yellow-tinted noise to suggest the procedural fill
                for yy in range(ENEMY_H):
                    for xx in range(8):
                        px = x + xx
                        py = y + yy
                        if 0 <= px < img_w and 0 <= py < img_h:
                            di = (py * img_w + px) * 3
                            n = (xx * 17 + yy * 31 + col * 7) & 0xFF
                            img[di] = 180 + (n & 0x3F)
                            img[di + 1] = 180 + (n & 0x3F)
                            img[di + 2] = 30 + (n & 0x1F)
                continue

            spr = get_sprite(sprite_idx)
            if spr is None:
                # Unknown -> magenta pin
                for yy in range(4):
                    for xx in range(4):
                        px = x + xx
                        py = y + yy
                        if 0 <= px < img_w and 0 <= py < img_h:
                            di = (py * img_w + px) * 3
                            img[di] = 255
                            img[di + 1] = 0
                            img[di + 2] = 255
                continue

            rgb, w, h = spr
            if v_flip:
                # Vertical flip — matches zp_sprite_dir_flag=0 path in
                # the engine, which reads the column-major source bytes
                # in reverse.
                flipped = bytearray(len(rgb))
                for yy in range(h):
                    src_y = h - 1 - yy
                    for xx in range(w):
                        src_i = (src_y * w + xx) * 3
                        dst_i = (yy * w + xx) * 3
                        flipped[dst_i:dst_i+3] = rgb[src_i:src_i+3]
                rgb = bytes(flipped)
            blit(rgb, w, h, x, y)

    draw_spawns(levd2[0x780:0x800], levd2[0x800:0x880], 0, get_levd2)
    if levd3 is not None and get_levd3 is not None:
        draw_spawns(levd3[0x780:0x800], levd3[0x800:0x880],
                    bottom_y, get_levd3)

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
