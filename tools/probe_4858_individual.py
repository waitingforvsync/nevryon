#!/usr/bin/env python3
"""Render each candidate sprite at &4858 / &48A0 individually, zoomed."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import NEVRYON_GAME_PALETTE
from render_sprite import render_column_major
from PIL import Image, ImageDraw, ImageFont


GRAPHIX_BASE = 0x3680


def try_font():
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, 14)
    return ImageFont.load_default()


def render(data, addr, w_cols, h_lines, scale=8):
    off = addr - GRAPHIX_BASE
    rgb, w, hh = render_column_major(data, off, w_cols, h_lines, NEVRYON_GAME_PALETTE)
    base = Image.frombytes("RGB", (w, hh), rgb).resize((w * scale, hh * scale), Image.NEAREST)
    return base


def main():
    data = open("extracted/$.GRAPHIX", "rb").read()
    font = try_font()

    # Try sprites at 4858 / 48A0 as 3×24
    s1_3 = render(data, 0x4858, 3, 24)
    s2_3 = render(data, 0x48A0, 3, 24)
    # And as 4×24 (overshoots if two of them)
    s1_4 = render(data, 0x4858, 4, 24)
    s2_4 = render(data, 0x48A0, 4, 24)

    SCALE = 8
    pad = 24
    total_w = pad + max(s1_3.width, s1_4.width) + pad + max(s2_3.width, s2_4.width) + pad + 100
    total_h = pad + s1_3.height + pad + s1_4.height + pad * 2
    canvas = Image.new("RGB", (total_w, total_h), (30, 30, 50))
    canvas.paste(s1_3, (pad, pad))
    canvas.paste(s2_3, (pad + s1_3.width + pad, pad))
    canvas.paste(s1_4, (pad, pad * 2 + s1_3.height))
    canvas.paste(s2_4, (pad + s1_4.width + pad, pad * 2 + s1_3.height))

    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 4), "&4858  3×24 (=72 B)", fill=(220, 220, 220), font=font)
    draw.text((pad + s1_3.width + pad, 4), "&48A0  3×24 (=72 B)", fill=(220, 220, 220), font=font)
    draw.text((pad, pad + s1_3.height + 4), "&4858  4×24 (=96 B)", fill=(220, 220, 220), font=font)
    draw.text((pad + s1_4.width + pad, pad + s1_3.height + 4), "&48A0  4×24 (=96 B)", fill=(220, 220, 220), font=font)

    out = "work/probe_4858_individual.png"
    canvas.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
