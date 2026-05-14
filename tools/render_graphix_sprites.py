#!/usr/bin/env python3
"""Render the catalog of confirmed GRAPHIX sprites to work/graphix_<addr>_<name>.png.

The list below is the current state of our knowledge of what lives in
$.GRAPHIX. Each entry is (start_addr, name, w_cols, h_lines, count). If
count > 1 the bytes are rendered as a horizontal strip of `count` sprites,
each of (w_cols × h_lines) col-major bytes.

Where the boundaries are still uncertain ("gap" entries), the bytes are
dumped as a long debugging strip at 16 lines tall — useful for visual
inspection.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image


GRAPHIX_BASE = 0x3680
SCALE = 6

# (addr, name, w_cols, h_lines, count)
CATALOG = [
    (0x3680, "muzzle_flash_frame0", 4, 16, 1),
    (0x36C0, "muzzle_flash_frame1", 4, 16, 1),
    (0x3700, "enemy_slot15",         4, 32, 1),
    (0x3780, "enemy_slot16",         4, 32, 1),
    (0x3800, "text_wow",             6, 16, 1),
    (0x3860, "sprite_helix",         6, 16, 1),
    # 0x38C0..0x3A1F: 352-byte gap — purpose still TBD
    # 0x3A00 first column = 1×32 padding strip
    (0x3A20, "small_chars_first12",  1,  8, 12),
    (0x3A80, "small_chars_next16",   1,  8, 16),
    (0x3B00, "small_chars_last3",    1,  8, 3),
    # 0x3B18 .. 0x3BBF: three 28×8 flame frames
    (0x3B18, "flame_frame0",         7,  8, 1),
    (0x3B50, "flame_frame1",         7,  8, 1),
    (0x3B88, "flame_frame2",         7,  8, 1),
    # text + decorations from 0x3BC0..0x435F (8×16 column-major chars)
    (0x3BC0, "text_press_space",     2, 16, 12),
    (0x3D40, "logo_4thdim_inset",    2, 16, 5),
    (0x3DE0, "text_score_last_high_at", 2, 16, 15),
    (0x3FC0, "small_sprite_3FC0",    2, 16, 1),
    (0x3FE0, "text_gpr_90",          2, 16, 7),
    (0x40C0, "text_dots",            2, 16, 2),
    (0x4100, "shape_circle_red",     2, 16, 1),
    (0x4120, "shape_circle_yellow",  2, 16, 1),
    (0x4140, "shape_circle_checker", 2, 16, 1),
    (0x4160, "small_sprite_4160",    2, 16, 1),
    (0x4180, "text_get_ready_game",  2, 16, 14),
    (0x4340, "trailing_3char_4340",  2, 16, 1),
    (0x4360, "enemy_slot19",         4, 32, 1),
    # 0x43E0 .. 0x4900: 1312-byte trailing region — still TBD
]


def render_strip(data, base_addr, name, w_cols, h_lines, count, scale=SCALE):
    cw, ch = w_cols * 4, h_lines
    pad = 1
    img_w = count * (cw + pad) + pad
    img_h = ch + pad * 2
    buf = bytearray(img_w * img_h * 3)
    for i in range(img_w * img_h):
        buf[i * 3] = 30
        buf[i * 3 + 1] = 30
        buf[i * 3 + 2] = 60

    for k in range(count):
        addr = base_addr + k * w_cols * h_lines
        off = addr - GRAPHIX_BASE
        if off + w_cols * h_lines > len(data):
            break
        rgb, w, hh = render_column_major(data, off, w_cols, h_lines,
                                          NEVRYON_GAME_PALETTE)
        ox = pad + k * (cw + pad)
        for y in range(hh):
            for x in range(w):
                si = (y * w + x) * 3
                di = ((pad + y) * img_w + (ox + x)) * 3
                buf[di] = rgb[si]
                buf[di + 1] = rgb[si + 1]
                buf[di + 2] = rgb[si + 2]

    im = Image.frombytes("RGB", (img_w, img_h), bytes(buf))
    if scale > 1:
        im = im.resize((img_w * scale, img_h * scale), Image.NEAREST)
    out = f"work/graphix_{base_addr:04X}_{name}.png"
    im.save(out)
    return out


def render_gap(data, start_addr, end_addr, name, h=16):
    """Render an unknown region as a long 16-line-tall column-major strip."""
    n_cols = (end_addr - start_addr) // h
    if n_cols <= 0:
        return None
    off = start_addr - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, n_cols, h, NEVRYON_GAME_PALETTE)
    im = Image.frombytes("RGB", (w, hh), rgb).resize(
        (w * SCALE, hh * SCALE), Image.NEAREST)
    out = f"work/graphix_{start_addr:04X}_gap_{name}.png"
    im.save(out)
    return out


def main():
    data = open("extracted/$.GRAPHIX", "rb").read()
    print(f"GRAPHIX size: {len(data)} bytes\n")
    print("Catalog:")
    for addr, name, w, h, count in CATALOG:
        out = render_strip(data, addr, name, w, h, count)
        size = w * h * count
        print(f"  &{addr:04X} ({size:>4}B) {w}×{h}×{count:>2} → {out}")
    print()
    print("Gaps (still unidentified):")
    render_gap(data, 0x38C0, 0x3A20, "between_helix_and_smallchars")
    print(f"  &38C0..&3A1F ({0x3A20-0x38C0:>4}B) → work/graphix_38C0_gap_between_helix_and_smallchars.png")
    render_gap(data, 0x43E0, 0x4900, "trailing_to_irq")
    print(f"  &43E0..&48FF ({0x4900-0x43E0:>4}B) → work/graphix_43E0_gap_trailing_to_irq.png")


if __name__ == "__main__":
    main()
