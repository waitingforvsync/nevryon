#!/usr/bin/env python3
"""Probe: render &4858..&48FF as H=24 column-major with annotations."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image, ImageDraw, ImageFont


GRAPHIX_BASE = 0x3680
START = 0x4858
END = 0x4900  # exclusive
H = 24


def try_font():
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, 14)
    return ImageFont.load_default()


def main():
    data = open("extracted/$.GRAPHIX", "rb").read()
    n_bytes = END - START
    n_cols = n_bytes // H
    rest = n_bytes - n_cols * H
    off = START - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, n_cols, H, NEVRYON_GAME_PALETTE)
    base = Image.frombytes("RGB", (w, hh), rgb)

    SCALE = 6
    scaled = base.resize((w * SCALE, hh * SCALE), Image.NEAREST)

    label_top = 24
    label_bot = 24
    margin = 80
    canvas_w = margin + scaled.width + 80
    canvas_h = label_top + scaled.height + label_bot
    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 50))
    canvas.paste(scaled, (margin, label_top))

    draw = ImageDraw.Draw(canvas)
    font = try_font()

    # Yellow tick lines every column (4 px = 4 * SCALE wide each)
    for c in range(n_cols + 1):
        x = margin + c * 4 * SCALE
        draw.line([(x, label_top), (x, label_top + scaled.height)],
                  fill=(200, 200, 80), width=1)
        addr = START + c * H
        if c % 1 == 0:
            draw.text((x - 18, label_top + scaled.height + 4),
                      f"{addr:04X}", fill=(220, 220, 220), font=font)
            # Column index above
            draw.text((x - 4, 2), f"{c}", fill=(180, 180, 180), font=font)

    # Side label
    draw.text((4, label_top + 4),
              f"H={H}\n{n_cols} cols\n+{rest} B",
              fill=(220, 220, 220), font=font)

    # Row tick lines every 4 scanlines on the right
    for r in range(0, H + 1, 4):
        y = label_top + r * SCALE
        draw.line([(margin + scaled.width, y),
                   (margin + scaled.width + 8, y)],
                  fill=(180, 180, 80), width=1)
        draw.text((margin + scaled.width + 10, y - 8),
                  f"{r}", fill=(200, 200, 200), font=font)

    out = "work/probe_4858_24.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.width}x{canvas.height})  "
          f"{n_cols} cols × {H} lines = {n_cols*H} B, {rest} B remainder")


if __name__ == "__main__":
    main()
