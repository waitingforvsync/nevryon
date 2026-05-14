#!/usr/bin/env python3
"""Extract and render Nevryon enemy sprites using the in-LEVD2 sprite
pointer tables.

LEVD2 layout (in memory once loaded at &7380):
  &7A80 + i : enemy sprite source LOW byte (table_lo, 64 entries)
  &7AC0 + i : enemy sprite source HIGH byte (table_hi, 64 entries)
  &7B00 + i : enemy spawn-column schedule (sorted, terminator = &FF)
  &7B80 + i : enemy attribute byte (low 5 bits = sprite index into ptr
              table; bit 7 = direction/mirror; bits 5-6 = pattern flags)

Enemy sprite sizes: most are 4 byte-cols × 32 lines = 128 bytes,
matching the L21BC / L21F1 paths in the disassembly (LDY #&20 = 32
height for the standard sprite_plot_xy call).

This tool reconstructs each enemy sprite by following the pointer
table back to where the data actually lives — be it in LEVD1, LEVD2
itself, or shared in GRAPHIX/CODE memory image.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE, write_png
from render_sprite import render_column_major


# Address ranges and the corresponding files-loaded-into-memory snapshot.
# When a sprite address points into one of these ranges, we read from the
# right file at the right offset.
ADDRESS_REGIONS = {
    # (start, end, file_kind, file_load_base)
    # CODE/CODE2/CODE3 are in the &1100-&3690 region. Most "shared" sprites
    # live in GRAPHIX at &3680-&49FF.
    "GRAPHIX": (0x3680, 0x4A00, "GRAPHIX", 0x3680),
    "LEVD1":   (0x4A00, 0x5800, "LEVD1",   0x4A00),
    "LEVD2/3": (0x7380, 0x8000, "LEVD2",   0x7380),
}


def resolve_addr(addr: int, files: dict[str, bytes]) -> tuple[bytes, int] | None:
    """Return (file_bytes, offset_in_file) for the given CPU address,
    or None if no file is mapped."""
    for name, (lo, hi, kind, base) in ADDRESS_REGIONS.items():
        if lo <= addr < hi:
            return files[kind], addr - base
    return None


def load_files(level: int) -> dict[str, bytes]:
    out = {}
    out["GRAPHIX"] = open("extracted/$.GRAPHIX", "rb").read()
    out["LEVD1"] = open(f"extracted/{level}.LEVD1", "rb").read()
    out["LEVD2"] = open(f"extracted/{level}.LEVD2", "rb").read()
    return out


def extract_enemies(level: int, height: int = 32, width_cols: int = 4):
    files = load_files(level)
    # Tables in LEVD2 at offsets 0x700 (lo) and 0x740 (hi); 64 entries each
    levd2 = files["LEVD2"]
    table_lo = levd2[0x700:0x740]
    table_hi = levd2[0x740:0x780]

    enemies: list[tuple[int, int, bytes | None, int, str]] = []
    for i in range(64):
        lo = table_lo[i]
        hi = table_hi[i]
        addr = (hi << 8) | lo
        if addr == 0:
            continue
        resolved = resolve_addr(addr, files)
        if resolved is None:
            enemies.append((i, addr, None, 0, "??"))
            continue
        data, off = resolved
        # find region name
        region = "??"
        for n, (a, b, _, _) in ADDRESS_REGIONS.items():
            if a <= addr < b:
                region = n
        enemies.append((i, addr, data, off, region))
    return enemies, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--output", "-o", required=True, help="output PNG")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--width", type=int, default=4)
    ap.add_argument("--height", type=int, default=32)
    args = ap.parse_args()

    enemies, files = extract_enemies(args.level, args.height, args.width)

    # Print report
    print(f"Level {args.level} enemy pointer table:")
    for i, addr, data, off, region in enemies:
        n_bytes = args.width * args.height
        addr_str = f"&{addr:04X}"
        avail = (len(data) - off) if data else 0
        print(f"  slot {i:2d}: {addr_str} ({region:8} +0x{off:04X}); "
              f"{avail} bytes available, need {n_bytes}")

    # Render grid
    sprite_w_px = args.width * 4
    sprite_h_px = args.height
    cell_w = sprite_w_px + 2
    cell_h = sprite_h_px + 2
    rows = (len(enemies) + args.cols - 1) // args.cols
    img_w = args.cols * cell_w + 2
    img_h = rows * cell_h + 2

    img = bytearray(img_w * img_h * 3)
    for i in range(img_w * img_h):
        img[i * 3 + 0] = 30
        img[i * 3 + 1] = 30
        img[i * 3 + 2] = 60

    for idx, (i, addr, data, off, region) in enumerate(enemies):
        if data is None:
            continue
        rgb, _, _ = render_column_major(data, off, args.width, args.height,
                                        NEVRYON_GAME_PALETTE)
        sx = idx % args.cols
        sy = idx // args.cols
        x0 = 2 + sx * cell_w
        y0 = 2 + sy * cell_h
        for yy in range(sprite_h_px):
            for xx in range(sprite_w_px):
                si = (yy * sprite_w_px + xx) * 3
                di = ((y0 + yy) * img_w + (x0 + xx)) * 3
                img[di] = rgb[si]
                img[di + 1] = rgb[si + 1]
                img[di + 2] = rgb[si + 2]

    if args.scale > 1:
        from PIL import Image
        im = Image.frombytes("RGB", (img_w, img_h), bytes(img)).resize(
            (img_w * args.scale, img_h * args.scale), Image.NEAREST)
        im.save(args.output)
        print(f"\nwrote {args.output} ({img_w*args.scale}x{img_h*args.scale})")
    else:
        write_png(args.output, bytes(img), img_w, img_h)
        print(f"\nwrote {args.output} ({img_w}x{img_h})")


if __name__ == "__main__":
    main()
