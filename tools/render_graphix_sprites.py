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

    # &40E0..&435F: end-of-game / inter-stage text strings
    # (&40E0..&40FF is a 2-col blank pad before GET READY!)
    (0x4100, "text_get_ready",       16, 16),
    (0x4200, "text_game",             8, 16),
    (0x4280, "text_over",             8, 16),
    (0x4300, "text_on",               6, 16),

    (0x4360, "enemy_slot19",          4, 32),

    # &43E0..&440F: 48 B blank padding before missiles
    # Five missile sprites at &4410, &4438, &4460, &4488, &44B0 (5×8 each = 40 B)
    (0x4410, "missile_0",             5, 8),
    (0x4438, "missile_1",             5, 8),
    (0x4460, "missile_2",             5, 8),
    (0x4488, "missile_3",             5, 8),
    (0x44B0, "missile_4",             5, 8),
    # &44D8..&44FF: 40 B padding
    # &4500..&474F: unknown_table, 592 B — needs disasm investigation
    (0x4500, "unknown_table",         1, 592),  # rendered as a strip; really a data table
    # &4750..&476F: 2×16 graphic — purpose TBD
    (0x4750, "graphic_4750",          2, 16),
    # &4770..&477F: 16 B padding
    # &4780..&47EF: text glyphs, 8 cols × 14 lines = 112 B
    # &47F0..&47FF: 16 B padding
    (0x4780, "text_4780",             8, 14),
    # &4800..&483F: 8 small icons (1×8 each = 8 B), generic naming
    (0x4800, "icon_seq", 1, 8, [
        "icon_10", "icon_11", "icon_12", "icon_13",
        "icon_14", "icon_15", "icon_16", "icon_17",
    ]),
    # &4840..&4847: 8 B pad
    # &4848..&484F: bomb/ball (1×8)
    (0x4848, "bomb",                  1, 8),
    # &4850..&48FF: gap (176 B) — render at 24 lines tall to spot patterns
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
    render_gap(data, 0x4850, 0x4900, "trailing_after_bomb", h=24)
    print(f"  &4850..&48FF ({0x4900-0x4850} B, 24 lines high)")
    print()
    print(f"Total sprites rendered: {count}")


if __name__ == "__main__":
    main()
