#!/usr/bin/env python3
"""Confirm: 6 ball frames at &3860 (2×12) and 3 enemy frames at &3900 (3×24)."""

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

    # Six ball frames: 2x12 each, 24 B per frame, 6 frames = 144 B (3860..38EF)
    ball_addrs = [0x3860 + i * 24 for i in range(6)]
    balls = [render(data, a, 2, 12, SCALE) for a in ball_addrs]

    # Pad between 38F0..38FF (16 B). Render that area too, in two reasonable ways
    # as a strip 1x16 (one col) — to see what's there
    gap_render = render(data, 0x38F0, 1, 16, SCALE)

    # Three enemy ship frames: 3x24 each, 72 B per frame, 3 frames = 216 B (3900..39D7)
    enemy_addrs = [0x3900 + i * 72 for i in range(3)]
    enemies = [render(data, a, 3, 24, SCALE) for a in enemy_addrs]

    # Trailing (39D8..3A1F = 72 B). Render as 3x24 (in case it's a 4th frame)
    tail = render(data, 0x39D8, 3, 24, SCALE)

    cell_w = balls[0].width
    cell_h = balls[0].height
    enemy_w = enemies[0].width
    enemy_h = enemies[0].height

    row1_w = pad + 6 * (cell_w + pad) + pad + gap_render.width + pad
    row1_h = 24 + cell_h + 24
    row2_w = pad + 4 * (enemy_w + pad)  # 3 enemies + trailing
    row2_h = 24 + enemy_h + 24

    canvas_w = max(row1_w, row2_w) + 20
    canvas_h = row1_h + row2_h + 24
    canvas = Image.new("RGB", (canvas_w, canvas_h), (28, 28, 44))
    draw = ImageDraw.Draw(canvas)

    # Row 1: balls + gap
    draw.text((pad, 4), "6 ball frames at &3860, 2×12 each (24 B/frame, 144 B total)",
              fill=(220, 220, 220), font=font)
    x = pad
    y = 24
    for i, (im, addr) in enumerate(zip(balls, ball_addrs)):
        canvas.paste(im, (x, y))
        draw.text((x, y - 16), f"&{addr:04X}", fill=(180, 220, 180), font=font_sm)
        draw.text((x, y + im.height + 2), f"#{i}", fill=(200, 200, 200), font=font_sm)
        x += im.width + pad
    # Gap render
    canvas.paste(gap_render, (x, y))
    draw.text((x, y - 16), "&38F0", fill=(220, 180, 180), font=font_sm)
    draw.text((x, y + gap_render.height + 2), "16B pad?",
              fill=(220, 180, 180), font=font_sm)

    # Row 2: enemies + trailing
    yy = row1_h + 8
    draw.text((pad, yy), "3 enemy frames at &3900, 3×24 each (72 B/frame, 216 B total) + 72 B trailing",
              fill=(220, 220, 220), font=font)
    x = pad
    y2 = yy + 24
    for i, (im, addr) in enumerate(zip(enemies, enemy_addrs)):
        canvas.paste(im, (x, y2))
        draw.text((x, y2 - 16), f"&{addr:04X}", fill=(180, 220, 180), font=font_sm)
        draw.text((x, y2 + im.height + 2), f"#{i}", fill=(200, 200, 200), font=font_sm)
        x += im.width + pad
    canvas.paste(tail, (x, y2))
    draw.text((x, y2 - 16), "&39D8", fill=(220, 180, 180), font=font_sm)
    draw.text((x, y2 + tail.height + 2), "tail 3×24?",
              fill=(220, 180, 180), font=font_sm)

    out = "work/probe_3860_confirm.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.width}x{canvas.height})")


if __name__ == "__main__":
    main()
