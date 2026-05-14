#!/usr/bin/env python3
"""Render the catalog of confirmed GRAPHIX sprites to graphix/<addr>_<name>.png.

The catalog below is the current state of our knowledge of what lives in
$.GRAPHIX. Each entry is one of:

  (start_addr, name, w_cols, h_lines)
      A single column-major sprite of (w_cols × 4) px wide × h_lines tall.

  (start_addr, name_prefix, w_cols, h_lines, items)
      A run of `items` consecutive sprites, each (w_cols × h_lines) bytes.
      `items` is either an int (renders <prefix>_<index>) or a list of
      explicit names (one per sprite, len must match the number of
      sprites; use None to skip).

Where the boundaries are still uncertain, a "gap" block is dumped to
graphix/gap_<addr>.png as a long 16-line-tall column-major strip.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image


GRAPHIX_BASE = 0x3680
SCALE = 1
OUT = "graphix"


# Format: (addr, name, w_cols, h_lines) for a single sprite, OR
#         (addr, name_prefix, w_cols, h_lines, items_or_namelist) for a run.
CATALOG = [
    (0x3680, "muzzle_flash_frame0",  4, 16),
    (0x36C0, "muzzle_flash_frame1",  4, 16),
    (0x3700, "enemy_slot15",          4, 32),
    (0x3780, "enemy_slot16",          4, 32),
    (0x3800, "text_wow",              6, 16),
    (0x3860, "sprite_helix",          6, 16),
    # 0x38C0..0x3A1F: 352-byte gap — purpose still TBD

    # Small chars at &3A20..&3AFF: 28 cells of 4×8 col-major.
    # Non-blank ones (20 total) get their own files; blanks skipped.
    (0x3A20, "small_char", 1, 8, [
        "icon_00", "icon_01", "icon_02", "icon_03",
        "icon_04", "icon_05", "icon_06", "icon_07",
        "digit_0", "digit_1", "digit_2", "digit_3",
        "digit_4", "digit_5", "digit_6", "digit_7",
        "digit_8", "digit_9", "icon_08", "icon_09",
        None, None, None, None, None, None, None, None,
    ]),

    # Flame frames at &3B00..&3BBF: three 8×8 frames (64 B each)
    (0x3B00, "flame_frame0",          8, 8),
    (0x3B40, "flame_frame1",          8, 8),
    (0x3B80, "flame_frame2",          8, 8),

    # Text region: 8×16 chars (& special 32-line logo) between &3BC0 and &4060
    (0x3BC0, "text_press_space",     20, 16),
    (0x3D00, "logo_4thdim",           7, 32),
    (0x3DE0, "text_score",            9, 16),
    (0x3E70, "punct_colon",           1, 16),
    (0x3E80, "text_last",             7, 16),
    (0x3EF0, "text_high",             7, 16),
    (0x3F60, "punct_ampersand",       2, 16),
    (0x3F80, "text_gpr90",           14, 16),

    # Pickups at &4060..&40DF: three 2×16 sprites with 1-col blanks between
    (0x4060, "pickup_red",            2, 16),
    (0x4090, "pickup_yellow",         2, 16),
    (0x40C0, "pickup_checker",        2, 16),

    # 0x40E0..0x435F: still TBD (~640 bytes)
    (0x4360, "enemy_slot19",          4, 32),
    # 0x43E0..0x48FF: trailing gap (~1312 B)
]


def render_one(data, addr, name, w_cols, h_lines, scale=SCALE):
    cw, ch = w_cols * 4, h_lines
    off = addr - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, w_cols, h_lines,
                                      NEVRYON_GAME_PALETTE)
    im = Image.frombytes("RGB", (w, hh), rgb)
    if scale > 1:
        im = im.resize((w * scale, hh * scale), Image.NEAREST)
    out = f"{OUT}/graphix_{addr:04X}_{name}.png"
    im.save(out)
    return out


def render_gap(data, start_addr, end_addr, name, h=16):
    n_cols = (end_addr - start_addr) // h
    if n_cols <= 0:
        return None
    off = start_addr - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, n_cols, h, NEVRYON_GAME_PALETTE)
    im = Image.frombytes("RGB", (w, hh), rgb).resize(
        (w * SCALE, hh * SCALE), Image.NEAREST)
    out = f"{OUT}/gap_{start_addr:04X}_{name}.png"
    im.save(out)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    data = open("extracted/$.GRAPHIX", "rb").read()
    print(f"GRAPHIX size: {len(data)} bytes — rendering to {OUT}/\n")

    count = 0
    for entry in CATALOG:
        if len(entry) == 4:
            addr, name, w, h = entry
            out = render_one(data, addr, name, w, h)
            print(f"  &{addr:04X} {w*4:>3}×{h:<3} {name:<28} → {out}")
            count += 1
        elif len(entry) == 5:
            addr, prefix, w, h, items = entry
            if isinstance(items, int):
                names = [f"{prefix}_{i:02d}" for i in range(items)]
            else:
                names = items
            for i, nm in enumerate(names):
                if nm is None:
                    continue
                child_addr = addr + i * w * h
                out = render_one(data, child_addr, nm, w, h)
                print(f"  &{child_addr:04X} {w*4:>3}×{h:<3} {nm:<28} → {out}")
                count += 1

    print()
    print("Gaps (still unidentified):")
    render_gap(data, 0x38C0, 0x3A20, "between_helix_and_smallchars")
    print(f"  &38C0..&3A1F ({0x3A20-0x38C0} B)")
    render_gap(data, 0x40E0, 0x4360, "between_pickups_and_slot19")
    print(f"  &40E0..&435F ({0x4360-0x40E0} B)")
    render_gap(data, 0x43E0, 0x4900, "trailing_to_irq")
    print(f"  &43E0..&48FF ({0x4900-0x43E0} B)")
    print()
    print(f"Total sprites rendered: {count}")


if __name__ == "__main__":
    main()
