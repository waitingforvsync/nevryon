#!/usr/bin/env python3
"""Render 3 enemy frames at &3900 with 1-col blank between each."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image, ImageDraw, ImageFont


GRAPHIX_BASE = 0x3680


def try_font(sz=14):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, sz)
    return ImageFont.load_default()


def render(data, addr, w_cols, h_lines, scale=8):
    off = addr - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, w_cols, h_lines, NEVRYON_GAME_PALETTE)
    return Image.frombytes("RGB", (w, hh), rgb).resize((w * scale, hh * scale), Image.NEAREST)


def main():
    data = open("extracted/$.GRAPHIX", "rb").read()
    font = try_font()
    font_sm = try_font(11)
    SCALE = 8
    pad = 12

    # Layout: F B F B F B, each F=3×24=72 B, each B=1×24=24 B, total 288 B = 3900..3A1F
    items = [
        (0x3900, "F0",  3, 24),
        (0x3948, "B0",  1, 24),
        (0x3960, "F1",  3, 24),
        (0x39A8, "B1",  1, 24),
        (0x39C0, "F2",  3, 24),
        (0x3A08, "B2",  1, 24),
    ]
    rendered = [(addr, name, render(data, addr, w, h, SCALE)) for addr, name, w, h in items]

    total_w = pad + sum(im.width + pad for _, _, im in rendered)
    h0 = rendered[0][2].height
    total_h = 24 + h0 + 32
    canvas = Image.new("RGB", (total_w + 20, total_h + 20), (28, 28, 44))
    draw = ImageDraw.Draw(canvas)

    draw.text((pad, 4),
              "3 enemy frames at &3900, 3×24 each with 1×24 blank between (F B F B F B = 288 B)",
              fill=(220, 220, 220), font=font)

    x = pad
    y = 24
    for addr, name, im in rendered:
        canvas.paste(im, (x, y))
        col = (220, 180, 180) if name.startswith("B") else (180, 220, 180)
        draw.text((x, y - 16), f"&{addr:04X}", fill=col, font=font_sm)
        draw.text((x, y + im.height + 2), name, fill=col, font=font_sm)
        x += im.width + pad

    out = "work/probe_3900_with_blanks.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.width}x{canvas.height})")


if __name__ == "__main__":
    main()
