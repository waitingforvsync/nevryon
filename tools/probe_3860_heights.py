#!/usr/bin/env python3
"""Probe: render &3860..&3A1F at multiple H values, annotated."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image, ImageDraw, ImageFont


GRAPHIX_BASE = 0x3680
START = 0x3860
END = 0x3A20  # exclusive
HEIGHTS = [8, 12, 16, 20, 24, 28, 32]
SCALE = 4


def try_font(sz=14):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, sz)
    return ImageFont.load_default()


def render_row(data, h, font):
    n_bytes = END - START
    n_cols = n_bytes // h
    rest = n_bytes - n_cols * h
    off = START - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, n_cols, h, NEVRYON_GAME_PALETTE)
    base = Image.frombytes("RGB", (w, hh), rgb)
    scaled = base.resize((w * SCALE, hh * SCALE), Image.NEAREST)

    side_w = 110
    label_top = 22
    label_bot = 22
    canvas_w = side_w + scaled.width + 30
    canvas_h = label_top + scaled.height + label_bot
    canvas = Image.new("RGB", (canvas_w, canvas_h), (28, 28, 44))
    canvas.paste(scaled, (side_w, label_top))

    draw = ImageDraw.Draw(canvas)
    # side label
    draw.text((6, label_top + 4),
              f"H={h:>2}\n{n_cols} cols\n+{rest} B",
              fill=(220, 220, 220), font=font)
    # column ticks every column, address labels every 2 columns
    tick_every = max(1, min(4, n_cols // 16 or 1))
    for c in range(n_cols + 1):
        x = side_w + c * 4 * SCALE
        draw.line([(x, label_top), (x, label_top + scaled.height)],
                  fill=(200, 200, 80), width=1)
        if c % tick_every == 0 and c < n_cols + 1:
            addr = START + c * h
            draw.text((x - 16, label_top + scaled.height + 3),
                      f"{addr:04X}", fill=(220, 220, 220), font=font)
            draw.text((x - 4, 4), f"{c}", fill=(170, 170, 170), font=font)
    return canvas


def main():
    data = open("extracted/$.GRAPHIX", "rb").read()
    font = try_font()
    rows = [render_row(data, h, font) for h in HEIGHTS]
    max_w = max(r.width for r in rows)
    total_h = sum(r.height for r in rows) + (len(rows) - 1) * 8
    canvas = Image.new("RGB", (max_w, total_h), (12, 12, 24))
    y = 0
    for r in rows:
        canvas.paste(r, (0, y))
        y += r.height + 8
    out = "work/probe_3860_heights.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.width}x{canvas.height})  "
          f"range &{START:04X}..&{END-1:04X} = {END-START} B")


if __name__ == "__main__":
    main()
