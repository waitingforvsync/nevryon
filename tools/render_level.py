#!/usr/bin/env python3
"""Generate per-level visualisations into levels/<n>/.

DESIGN: one PNG per UNIQUE block of sprite bytes in the LEVD files.
No aliasing — if two table indices point at the same memory, only
the underlying memory range gets a PNG. The README maps all of the
indices back to the filename so the relationships are explicit.

Naming: `sprite_NN.png` numbered sequentially by file then address,
starting at 00 within each per-level directory. Per-sprite dimensions
are native (no upscale).

Other outputs per level:
  map_strip_stage{1,2}.png   — full 240-col playfield strip
  map_with_spawns_{1,2}.png  — same + spawn-pin overlay
  spawn_table_stage{1,2}.md  — decoded spawn schedule
  data/*.bin                 — raw 128/240-byte tables per stage
  README.md                  — byte-by-byte memory map + index-to-sprite
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(__file__))
from render_screen import palette_for_level, write_png
from render_sprite import render_column_major


# ---- LEVD layout (mirrors disasm/Nevryon.6502 lev_*) ----
LEVD1_LOAD = 0x4A00
LEVD2_LOAD = 0x7380
GRAPHIX_LOAD = 0x3680

LEVD1_EXPLOSION_OFF   = 0x000   # &4A00..&4BFF — frames 0..3 of the 6-frame player explosion (= lev_enemy_ptr_*[21..24])
LEVD1_EXPLOSION_COUNT = 4
# &4C00..&4E7F contains the per-scenario small-enemy animation strip
# read by the L1BE3 state machine in CODE. Each frame is 4 byte-cols
# × 24 lines = 96 bytes. Adjacent frames overlap by ONE COLUMN
# (24 bytes) — the stride between most starts is 72 B. Three damage
# frames first (enemy_hit_1..3), then four normal frames
# (enemy_0..3). Zero-pad gaps at &4C00..&4C1F, &4DA8..&4DAF,
# &4E70..&4E7F.
ENEMY_ANIM_OFFS   = [(0x220, 'enemy_hit_01'),
                     (0x268, 'enemy_hit_02'),
                     (0x2B0, 'enemy_hit_03'),
                     (0x300, 'enemy_00'),
                     (0x348, 'enemy_01'),
                     (0x3B0, 'enemy_02'),
                     (0x410, 'enemy_03')]
ENEMY_W_COLS      = 4
ENEMY_H_LINES     = 24
ENEMY_SIZE        = ENEMY_W_COLS * ENEMY_H_LINES   # 96 bytes
PLAYER_OFF        = 0x480   # &4E80 — 6×22 player ship (132 bytes; overlaps tile 0 first 4 bytes)
PLAYER_W_COLS     = 6
PLAYER_H_LINES    = 22
TILE_CATALOG_OFF  = 0x500   # &4F00 — 18 tile slots
TILE_COUNT        = 18

LEVD2_ENEMY_OFF   = 0x000   # &7380..&7A7F — 14 × 128-byte primary enemy sprites
LEVD2_ENEMY_COUNT = 14
ENEMY_PTR_LO_OFF  = 0x700   # &7A80
ENEMY_PTR_HI_OFF  = 0x740   # &7AC0
N_ENEMY_SLOTS     = 32
SPAWN_COL_OFF     = 0x780   # &7B00
SPAWN_ATTR_OFF    = 0x800   # &7B80
SPAWN_TABLE_LEN   = 128
HAZARD_A_OFF      = 0x880   # &7C00
HAZARD_B_OFF      = 0x900   # &7C80
ERASE_BRUSH_OFF   = 0x980   # &7D00..&7E0F (272 B of zeros)
ERASE_BRUSH_LEN   = 272
MAP_UPPER_OFF     = 0xA90   # &7E10
MAP_PAD_OFF       = 0xB80   # &7F00..&7F0F
MAP_PAD_LEN       = 16
MAP_LOWER_OFF     = 0xB90   # &7F10
MAP_TABLE_LEN     = 240

SPRITE_SIZE       = 128     # default sprite block (4 cols × 32 lines)
SPRITE_W_COLS     = 4
SPRITE_H_LINES    = 32


# Death-anim source pointers are the alias of enemy_ptr_*[21..26]
DEATH_ANIM_SLOTS = list(range(21, 27))


# ---- per-LEVD inventory builder ---------------------------------------

@dataclass
class SpriteBlock:
    file: str                   # 'LEVD1' or 'LEVD2'
    file_off: int               # offset within the LEVD file
    cpu_addr: int               # CPU load address
    size: int                   # bytes
    w_cols: int                 # render width in byte-cols
    h_lines: int                # render height in scanlines
    label: str                  # short name — also the PNG basename, e.g. 'explosion_00', 'tile_05', 'player_sprite', 'hazard_07'

    @property
    def filename(self) -> str:
        return f'{self.label}.png'


def build_sprite_inventory() -> list[SpriteBlock]:
    """Per-level sprite-block inventory in address order (LEVD1 first,
    then LEVD2). One block per *sprite the engine reads from*. The
    enemy-animation frames at &4C20..&4E70 overlap each other by one
    column (24 B) — adjacent PNGs in that range share a column of
    source bytes. The byte-map in the README accounts for the overlap
    and the inter-sprite zero padding."""
    blocks: list[SpriteBlock] = []

    # --- LEVD1 ---
    # explosion frames 0..3 — 4×32 = 128 B each
    for i in range(LEVD1_EXPLOSION_COUNT):
        off = LEVD1_EXPLOSION_OFF + i * SPRITE_SIZE
        blocks.append(SpriteBlock('LEVD1', off, LEVD1_LOAD + off,
                                  SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
                                  f'explosion_{i:02d}'))

    # per-scenario enemy animation strip — 4×24 = 96 B each,
    # overlapping columns
    for off, label in ENEMY_ANIM_OFFS:
        blocks.append(SpriteBlock('LEVD1', off, LEVD1_LOAD + off,
                                  ENEMY_SIZE, ENEMY_W_COLS, ENEMY_H_LINES,
                                  label))

    # player ship — 6×22 = 132 B
    blocks.append(SpriteBlock('LEVD1', PLAYER_OFF, LEVD1_LOAD + PLAYER_OFF,
                              PLAYER_W_COLS * PLAYER_H_LINES,
                              PLAYER_W_COLS, PLAYER_H_LINES, 'player_sprite'))

    # tile catalog — 4×32 = 128 B each
    for tid in range(TILE_COUNT):
        off = TILE_CATALOG_OFF + tid * SPRITE_SIZE
        blocks.append(SpriteBlock('LEVD1', off, LEVD1_LOAD + off,
                                  SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
                                  f'tile_{tid:02d}'))

    # --- LEVD2: explosion frames 4-5 (shared between stages — bytes are
    # identical in scenarios 1-3 because LEVD3 is too short to overlay
    # this region, and identical in scenario 4 by coincidence) ---
    blocks.append(SpriteBlock('LEVD2', HAZARD_A_OFF, LEVD2_LOAD + HAZARD_A_OFF,
                              SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
                              'explosion_04'))
    blocks.append(SpriteBlock('LEVD2', HAZARD_B_OFF, LEVD2_LOAD + HAZARD_B_OFF,
                              SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
                              'explosion_05'))

    # NOTE: the 14 hazard sprites at &7380..&7A7F are per-stage
    # (LEVD2 = stage 1, LEVD3 = stage 2 — the ptr LUT offsets are
    # identical between the two files, only the sprite bytes differ).
    # They're rendered separately by build_level() so each stage gets
    # its own `hazard_stage{1,2}_NN.png`.

    return blocks


def build_hazard_blocks(stage: int) -> list[SpriteBlock]:
    """The 14 hazard sprites of one stage. Source file is LEVD2 for
    stage 1, LEVD3 for stage 2 — same offsets within the file."""
    src_file = 'LEVD2' if stage == 1 else 'LEVD3'
    blocks: list[SpriteBlock] = []
    for i in range(LEVD2_ENEMY_COUNT):
        off = LEVD2_ENEMY_OFF + i * SPRITE_SIZE
        blocks.append(SpriteBlock(src_file, off, LEVD2_LOAD + off,
                                  SPRITE_SIZE, SPRITE_W_COLS, SPRITE_H_LINES,
                                  f'hazard_stage{stage}_{i:02d}'))
    return blocks


def resolve_sprite(addr: int, levd1: bytes, levd2: bytes, graphix: bytes):
    """Return (data, offset, region_name) for `addr` if it lives in
    LEVD1, LEVD2, or GRAPHIX. Returns None for the all-zero erase
    brush (anywhere in `&7D00..&7E0F`) or for &0000."""
    if addr == 0:
        return None
    if 0x7D00 <= addr < 0x7E10:
        return None
    if GRAPHIX_LOAD <= addr < GRAPHIX_LOAD + len(graphix):
        return graphix, addr - GRAPHIX_LOAD, 'GRAPHIX'
    if LEVD1_LOAD <= addr < LEVD1_LOAD + len(levd1):
        return levd1, addr - LEVD1_LOAD, 'LEVD1'
    if LEVD2_LOAD <= addr < LEVD2_LOAD + len(levd2):
        return levd2, addr - LEVD2_LOAD, 'LEVD2'
    return None


def find_sprite_for_addr(blocks: list[SpriteBlock], addr: int) -> SpriteBlock | None:
    """Return the SpriteBlock whose CPU range covers `addr`, or None
    if no LEVD-resident sprite matches (e.g. a GRAPHIX-resident
    pointer, or the all-zero erase brush)."""
    for b in blocks:
        if b.cpu_addr <= addr < b.cpu_addr + b.size:
            return b
    return None


# ---- shared image helpers ---------------------------------------------

def blank(w: int, h: int, bg=(0, 0, 0)) -> bytearray:
    buf = bytearray(w * h * 3)
    for i in range(w * h):
        buf[i * 3] = bg[0]
        buf[i * 3 + 1] = bg[1]
        buf[i * 3 + 2] = bg[2]
    return buf


def blit(dst: bytearray, dst_w: int, src: bytes, src_w: int, src_h: int,
         dx: int, dy: int, mirror_v: bool = False,
         transparent_black: bool = False):
    """Blit `src` into `dst`. If `transparent_black`, pure-black pixels
    in the source are skipped — for sprites the engine plots with the
    standard palette where pixel 0 (black) acts as transparent."""
    for y in range(src_h):
        sy = (src_h - 1 - y) if mirror_v else y
        for x in range(src_w):
            si = (sy * src_w + x) * 3
            r, g, b = src[si], src[si + 1], src[si + 2]
            if transparent_black and r == 0 and g == 0 and b == 0:
                continue
            di = ((dy + y) * dst_w + (dx + x)) * 3
            if 0 <= di < len(dst) - 2:
                dst[di] = r
                dst[di + 1] = g
                dst[di + 2] = b


# ---- sprite + map renderers -------------------------------------------

def write_sprites(out_dir: str, blocks: list[SpriteBlock],
                  levd1: bytes, levd2: bytes, palette,
                  levd3: bytes | None = None):
    file_data = {'LEVD1': levd1, 'LEVD2': levd2}
    if levd3 is not None:
        file_data['LEVD3'] = levd3
    for b in blocks:
        data = file_data[b.file]
        rgb, w, h = render_column_major(data, b.file_off, b.w_cols, b.h_lines,
                                        palette, bg=(0, 0, 0))
        write_png(f'{out_dir}/{b.filename}', rgb, w, h)


def render_map_strip(levd1: bytes, stage_levd: bytes, palette):
    upper_ids = stage_levd[MAP_UPPER_OFF:MAP_UPPER_OFF + MAP_TABLE_LEN]
    lower_ids = stage_levd[MAP_LOWER_OFF:MAP_LOWER_OFF + MAP_TABLE_LEN]
    tile_px_w = SPRITE_W_COLS * 4
    tile_px_h = SPRITE_H_LINES
    gap_h = 96
    n = MAP_TABLE_LEN
    w = n * tile_px_w
    h = tile_px_h * 2 + gap_h
    img = blank(w, h)
    for col in range(n):
        utid = upper_ids[col]
        uoff = TILE_CATALOG_OFF + utid * SPRITE_SIZE
        if uoff + SPRITE_SIZE <= len(levd1):
            rgb, sw, sh = render_column_major(levd1, uoff, SPRITE_W_COLS,
                                              SPRITE_H_LINES, palette,
                                              bg=(0, 0, 0))
            blit(img, w, rgb, sw, sh, col * tile_px_w, 0, mirror_v=True)
        ltid = lower_ids[col]
        loff = TILE_CATALOG_OFF + ltid * SPRITE_SIZE
        if loff + SPRITE_SIZE <= len(levd1):
            rgb, sw, sh = render_column_major(levd1, loff, SPRITE_W_COLS,
                                              SPRITE_H_LINES, palette,
                                              bg=(0, 0, 0))
            blit(img, w, rgb, sw, sh, col * tile_px_w, tile_px_h + gap_h)
    return bytes(img), w, h


# spawn y_row maps to char rows 4 / 8 / 12 / 16 (the play-area gap is
# 12 char rows tall, sitting between the upper tile (rows 0..3) and
# the lower tile (rows 16..19)). Each char row is 8 px tall, so y_rows
# are 32 px apart, and the first spawn y_row sits at pixel 32 (i.e.
# straight after the 32-px upper tile band).
SPAWN_Y_PIXEL = lambda y_row: SPRITE_H_LINES + y_row * 32


def render_map_with_spawns(levd1: bytes, stage_levd: bytes, palette):
    """Overlay coloured pins at every spawn (column, y_row) — useful
    for at-a-glance schedule density. See render_map_with_hazards for
    the actual-sprite version."""
    rgb_bytes, w, h = render_map_strip(levd1, stage_levd, palette)
    img = bytearray(rgb_bytes)
    tile_px_w = SPRITE_W_COLS * 4
    spawn_cols = stage_levd[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN]
    spawn_attrs = stage_levd[SPAWN_ATTR_OFF:SPAWN_ATTR_OFF + SPAWN_TABLE_LEN]
    for col, attr in zip(spawn_cols, spawn_attrs):
        if col == 0xFF:
            break
        slot_type = attr & 0x1F
        y_row = (attr >> 5) & 3
        py = SPAWN_Y_PIXEL(y_row)
        px_centre = col * tile_px_w + tile_px_w // 2
        if slot_type == 7:
            colour = (255, 220, 0)
        elif attr & 0x80:
            colour = (255, 60, 60)
        else:
            colour = (90, 240, 90)
        for d in range(-3, 4):
            for ox, oy in ((d, 0), (0, d)):
                x = px_centre + ox
                y = py + oy
                if 0 <= x < w and 0 <= y < h:
                    di = (y * w + x) * 3
                    img[di] = colour[0]
                    img[di + 1] = colour[1]
                    img[di + 2] = colour[2]
    return bytes(img), w, h


def render_map_with_hazards(levd1: bytes, levd2: bytes, graphix: bytes,
                            stage_levd: bytes, palette):
    """Like render_map_with_spawns, but plot the ACTUAL enemy / hazard
    sprite at each spawn position, mirrored when attr bit 7 is set —
    so it reads like a level-design schematic. Force-field spawns
    (type 7) draw a yellow vertical strip (no fixed sprite); spawns
    pointing at the erase brush or unused slots are skipped.

    The map strip itself is per-LEVEL (stage 1 and 2 share the same
    map tiles); only the spawn overlay changes per stage."""
    rgb_bytes, w, h = render_map_strip(levd1, stage_levd, palette)
    img = bytearray(rgb_bytes)
    tile_px_w = SPRITE_W_COLS * 4    # 16
    enemy_ptr_lo = stage_levd[ENEMY_PTR_LO_OFF:ENEMY_PTR_LO_OFF + N_ENEMY_SLOTS]
    enemy_ptr_hi = stage_levd[ENEMY_PTR_HI_OFF:ENEMY_PTR_HI_OFF + N_ENEMY_SLOTS]
    spawn_cols = stage_levd[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN]
    spawn_attrs = stage_levd[SPAWN_ATTR_OFF:SPAWN_ATTR_OFF + SPAWN_TABLE_LEN]
    for col, attr in zip(spawn_cols, spawn_attrs):
        if col == 0xFF:
            break
        slot_type = attr & 0x1F
        y_row = (attr >> 5) & 3
        v_flip = bool(attr & 0x80)
        py = SPAWN_Y_PIXEL(y_row)
        px = col * tile_px_w

        if slot_type == 7:
            # Force-field — procedural strip. Draw a 16×32 yellow
            # rectangle as a placeholder; the real one is pixel noise
            # from a sideways ROM via lfsr_random.
            for yy in range(32):
                for xx in range(tile_px_w):
                    x = px + xx
                    y = py + yy
                    if 0 <= x < w and 0 <= y < h:
                        di = (y * w + x) * 3
                        img[di] = 200
                        img[di + 1] = 180
                        img[di + 2] = 0
            continue

        addr = (enemy_ptr_hi[slot_type] << 8) | enemy_ptr_lo[slot_type]
        resolved = resolve_sprite(addr, levd1, levd2, graphix)
        if resolved is None:
            continue   # erase brush or unused slot
        data, off, _ = resolved
        if off + SPRITE_W_COLS * SPRITE_H_LINES > len(data):
            continue
        rgb_sp, sw, sh = render_column_major(data, off, SPRITE_W_COLS,
                                             SPRITE_H_LINES, palette,
                                             bg=(0, 0, 0))
        blit(img, w, rgb_sp, sw, sh, px, py,
             mirror_v=v_flip, transparent_black=True)
    return bytes(img), w, h


# ---- stage data helpers ----------------------------------------------

def load_levd(level: int):
    return (
        open(f'extracted/{level}.LEVD1', 'rb').read(),
        open(f'extracted/{level}.LEVD2', 'rb').read(),
        open(f'extracted/{level}.LEVD3', 'rb').read(),
    )


def stage_data(level: int, stage: int, levd2: bytes, levd3: bytes) -> bytes:
    if stage == 1:
        return levd2
    if len(levd3) >= len(levd2):
        return levd3
    return levd3 + levd2[len(levd3):]


# ---- spawn-table markdown ---------------------------------------------

def write_spawn_table(path: str, stage_levd: bytes, stage: int):
    spawn_cols = stage_levd[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN]
    spawn_attrs = stage_levd[SPAWN_ATTR_OFF:SPAWN_ATTR_OFF + SPAWN_TABLE_LEN]
    with open(path, 'w') as f:
        f.write(f"# Stage {stage} spawn schedule\n\n")
        f.write("Walked by `spawn_check_step` (CODE `&208A`) each time the\n")
        f.write("scroll counter advances. Both `lev_spawn_col` and\n")
        f.write("`lev_spawn_attr` are walked together until `&FF`.\n\n")
        f.write("| Idx | Col | Attr | Type | Y-row | V-flip | Notes |\n")
        f.write("|----:|----:|-----:|-----:|------:|:------:|-------|\n")
        n = 0
        for i, (col, attr) in enumerate(zip(spawn_cols, spawn_attrs)):
            if col == 0xFF:
                f.write(f"| ... | `&FF` | — | — | — | — | terminator at slot {i} ({n} active) |\n")
                break
            t = attr & 0x1F
            y = (attr >> 5) & 3
            vf = (attr >> 7) & 1
            note = ""
            if t == 7:
                note = "force-field (procedural, no sprite)"
            elif t in (4, 0x13):
                note = "multi-shot"
            elif t == 6:
                note = "CODE2 spawn_enemy_missile"
            elif t == 8:
                note = "high-HP variant"
            elif t == 0x10:
                note = "boss / heavy"
            f.write(f"| {i:3d} | `&{col:02X}` | `&{attr:02X}` | {t:2d} | {y} | "
                    f"{'Y' if vf else 'n'}     | {note} |\n")
            n += 1


# ---- README writer ---------------------------------------------------

PALETTE_NAMES = {
    1: "black / red / yellow / white  (Battle Cruiser)",
    2: "black / blue / cyan / white   (Asteroid Base)",
    3: "black / red / green / white   (Planet / Caves)",
    4: "black / red / magenta / white (Alien Beast)",
}

# These cross-binary slot pointers are identical across every level —
# referenced here so the slot map can show the GRAPHIX label for the
# slots that don't get a per-level PNG.
GRAPHIX_SLOT_LABELS = {
    0x3700: 'gfx_enemy_slot15',
    0x3780: 'gfx_enemy_slot16',
    0x4360: 'gfx_enemy_slot19',
}


def write_readme(path: str, level: int, levd1: bytes, levd2: bytes,
                 levd3: bytes, blocks: list[SpriteBlock]):
    spawns_s1 = sum(1 for c in levd2[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN] if c != 0xFF)
    s2 = stage_data(level, 2, levd2, levd3)
    spawns_s2 = sum(1 for c in s2[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN] if c != 0xFF)

    # Index for "given an address, which named sprite does it sit in?"
    by_label = {b.label: b for b in blocks}
    explosion_lo = [by_label[f'explosion_{i:02d}'] for i in range(LEVD1_EXPLOSION_COUNT)]
    enemy_anim_sp = [by_label[lab] for _, lab in ENEMY_ANIM_OFFS]
    tile_sprite = [by_label[f'tile_{i:02d}'] for i in range(TILE_COUNT)]
    # Hazard sprites are per-stage (LEVD2 vs LEVD3); rendered separately.
    # The README references them as a count rather than by-label lookup
    # since the SpriteBlock list passed in only contains the shared
    # LEVD1/LEVD2 inventory.
    hazard_count = LEVD2_ENEMY_COUNT
    explosion_04 = by_label['explosion_04']
    explosion_05 = by_label['explosion_05']
    player_sprite = by_label['player_sprite']
    explosion_all = explosion_lo + [explosion_04, explosion_05]

    # The 32 enemy-pointer slots, expressed as where each address resolves.
    enemy_slot_rows = []
    for slot in range(N_ENEMY_SLOTS):
        lo = levd2[ENEMY_PTR_LO_OFF + slot]
        hi = levd2[ENEMY_PTR_HI_OFF + slot]
        addr = (hi << 8) | lo
        sp = find_sprite_for_addr(blocks, addr)
        if addr == 0:
            target = '*(unused — pointer pair is &0000)*'
        elif sp is None and GRAPHIX_LOAD <= addr < GRAPHIX_LOAD + 0x1380:
            target = f'GRAPHIX `{GRAPHIX_SLOT_LABELS.get(addr, f"&{addr:04X}")}` *(not exported here)*'
        elif sp is None:
            # Could be erase brush (&7D80) or some other reference
            target = f'*(no sprite — points at &{addr:04X})*'
        else:
            off_in_sprite = addr - sp.cpu_addr
            if off_in_sprite == 0:
                target = f'`{sp.filename}` ({sp.label})'
            else:
                target = f'`{sp.filename}` ({sp.label}) at +{off_in_sprite:#x}'
        enemy_slot_rows.append((slot, addr, target))

    with open(path, 'w') as f:
        f.write(f"# Level {level}\n\n")
        f.write(f"Palette: {PALETTE_NAMES[level]}\n\n")
        f.write(f"LEVD1: 3584 B (`&E00`)\n")
        f.write(f"LEVD2: {len(levd2)} B (`{len(levd2):#06x}`)\n")
        f.write(f"LEVD3: {len(levd3)} B (`{len(levd3):#06x}`) — "
                f"{'full overlay (tile streams byte-identical to LEVD2)' if len(levd3) >= len(levd2) else 'lower-half overlay (2176 B; tile streams inherit from LEVD2)'}\n\n")

        # ---- The sprite inventory: one row per unique memory range
        f.write("## Sprite inventory\n\n")
        f.write("Every unique block of bytes in the LEVD files that the\n")
        f.write("engine reads as sprite data is exported as a PNG. Names\n")
        f.write("are semantic rather than sequential — six categories cover\n")
        f.write("all of the per-level sprite data:\n\n")
        f.write("| Category | Files | What it is |\n")
        f.write("|----------|-------|------------|\n")
        f.write("| `explosion_NN` | `explosion_00..05` | The 6 frames of the player death-explosion animation. Frames 00..03 live in LEVD1 (`&4A00..&4BFF`); frames 04..05 live in LEVD2 (`&7C00..&7CFF`). The same 6 byte-pairs also appear in `lev_enemy_ptr_*` slots 21..26 — that's how `death_anim` (CODE `&1E47`) reaches them. |\n")
        f.write("| `enemy_NN` | `enemy_00..03` | 4 frames of the per-scenario small flying enemy. 4×24 (96 B) each; the state machine in CODE `L1BE3` cycles through these as states 1..4. |\n")
        f.write("| `enemy_hit_NN` | `enemy_hit_01..03` | 3 frames of the same enemy's hit / destruction cycle. 4×24 (96 B) each; state machine states `&0A..&0C`. Numbered 01..03 to keep the index in step with the state-machine state values (the LEVD1 designer left `enemy_hit_00` empty / unused). |\n")
        f.write("| `player_sprite` | `player_sprite` | The 6×22 (132 B) player ship at LEVD1 `&4E80`. |\n")
        f.write("| `tile_NN` | `tile_00..17` | The 18-slot per-scenario map tile catalog (LEVD1 `&4F00 + N*&80`, each 4×32 = 128 B). |\n")
        f.write("| `hazard_stageN_NN` | `hazard_stage1_00..13` + `hazard_stage2_00..13` | The 14 hazard sprites for each stage (large stationary threats — gun-towers, tanks, structures). 4×32 (128 B) each. Stage 1 sprites come from LEVD2 `&7380..&7A00`, stage 2 sprites from LEVD3 at the same offsets (LEVD3 overlays the LEVD2 sprite block in RAM when stage 2 loads). The ptr LUT entries at `&7A80..&7AFF` are identical between LEVD2 and LEVD3, so slot N points at the same offset in both; only the sprite bytes differ. |\n")

        f.write("\n### Per-sprite details\n\n")
        f.write("| PNG | File | Bytes (file off) | CPU addr | Shape | Render dims |\n")
        f.write("|-----|------|------------------|----------|-------|-------------|\n")
        for b in blocks:
            f.write(f"| `{b.filename}` | {b.file} | "
                    f"`{b.file_off:#06x}..{b.file_off + b.size - 1:#06x}` ({b.size}) | "
                    f"`&{b.cpu_addr:04X}..&{b.cpu_addr + b.size - 1:04X}` | "
                    f"{b.w_cols}×{b.h_lines} col-major | "
                    f"{b.w_cols * 4}×{b.h_lines} px |\n")

        f.write("\n*Notes on sprite shapes / overlap*:\n\n")
        f.write("- The 6 `explosion_*` sprites are 4×32 (128 B each). Frames\n")
        f.write("  00..03 live consecutively in LEVD1, then there's a 96-byte\n")
        f.write("  zero pad and the per-scenario `enemy_*` strip; frames\n")
        f.write("  04..05 live in LEVD2 at `&7C00`/`&7C80`. The split-across-\n")
        f.write("  files layout is unusual but consistent with the level\n")
        f.write("  designer's memory packing: LEVD1 is per-scenario only\n")
        f.write("  (palette differs), while the explosion's pointer table\n")
        f.write("  lives in LEVD2 (per-stage) and happens to have spare slots\n")
        f.write("  for the last two frames.\n")
        f.write("- The 7 `enemy_*` / `enemy_hit_*` sprites are 4×24 (96 B).\n")
        f.write("  Adjacent frames in the strip *share a column* of 24 bytes —\n")
        f.write("  e.g. the 24 bytes at `&4D00..&4D17` are simultaneously the\n")
        f.write("  last column of `enemy_hit_03` and the first column of\n")
        f.write("  `enemy_00`. The state machine reads each frame as a complete\n")
        f.write("  4×24 block; the sharing is byte-packing.\n")
        f.write("- `player_sprite` is 6×22 (132 B) and overlaps the first 4 bytes\n")
        f.write("  of `tile_00` (both are zero in that region — overlap is benign).\n")
        f.write("- All 18 `tile_*` and all 16 LEVD2 `hazard_*` / `explosion_04/05`\n")
        f.write("  sprites are 4×32 (128 B each).\n\n")

        # ---- Table index → sprite
        f.write("## Table indices → sprite\n\n")

        f.write(f"### `lev_player_sprite` (&4E80)\n\n")
        f.write(f"Always `{player_sprite.filename}` — the only entry in this table.\n\n")

        f.write(f"### `lev_tile_catalog` (&4F00 + N*&80, N = 0..17)\n\n")
        f.write("| Tile id | CPU addr | sprite | Notes |\n")
        f.write("|--------:|----------|--------|-------|\n")
        for tid, sp in enumerate(tile_sprite):
            tile_bytes = levd1[TILE_CATALOG_OFF + tid * SPRITE_SIZE:
                               TILE_CATALOG_OFF + (tid + 1) * SPRITE_SIZE]
            note = '**all-zero (blank tile)**' if not any(tile_bytes) else ''
            f.write(f"| {tid:7d} | `&{sp.cpu_addr:04X}` | `{sp.filename}` | {note} |\n")

        f.write(f"\n### `lev_enemy_ptr_lo` / `lev_enemy_ptr_hi` (&7A80 / &7AC0, 32 slots)\n\n")
        f.write("`lev_enemy_ptr_*[N]` is read whenever an enemy of type N\n")
        f.write("(bits 0..4 of `lev_spawn_attr`) is plotted.\n\n")
        f.write("| Slot | Pointer | Resolves to | Aliases |\n")
        f.write("|-----:|---------|-------------|---------|\n")
        for slot, addr, target in enemy_slot_rows:
            aliases = []
            if slot in DEATH_ANIM_SLOTS:
                aliases.append(f"`lev_explosion_ptr_*[{slot - 21}]` (= explosion frame {slot - 21})")
            alias_str = ', '.join(aliases) if aliases else ''
            f.write(f"| {slot:4d} | `&{addr:04X}` | {target} | {alias_str} |\n")

        f.write(f"\n### `lev_explosion_ptr_lo` / `lev_explosion_ptr_hi` (&7A95 / &7AD5, 6 entries)\n\n")
        f.write("**Same physical bytes** as `lev_enemy_ptr_*[21..26]`. The\n")
        f.write("6-frame player-death explosion (CODE `death_anim` at\n")
        f.write("`&1E47`) reads its source pointers here. Each frame is\n")
        f.write("plotted as 4×32 (so frames 0..3 use the *full* 128-B\n")
        f.write("`explosion_00..03` blocks in LEVD1, while frames 4..5 use\n")
        f.write("the 128-B `explosion_04` / `explosion_05` blocks in LEVD2 —\n")
        f.write("those are 4×32 blocks too, distinct from the 4×24 `enemy_*`\n")
        f.write("/ `enemy_hit_*` sprites in LEVD1 which are a DIFFERENT\n")
        f.write("animation entirely, used by the L1BE3 state machine).\n\n")
        f.write("| Frame | Pointer | Resolves to |\n")
        f.write("|------:|---------|-------------|\n")
        for i in range(6):
            slot = 21 + i
            lo = levd2[ENEMY_PTR_LO_OFF + slot]
            hi = levd2[ENEMY_PTR_HI_OFF + slot]
            addr = (hi << 8) | lo
            sp = find_sprite_for_addr(blocks, addr)
            tgt = f'`{sp.filename}` ({sp.label})' if sp else f'&{addr:04X} (no sprite resolved)'
            f.write(f"| {i:5d} | `&{addr:04X}` | {tgt} |\n")

        # ---- LEVD1 byte map
        f.write("\n## LEVD1 byte map\n\n")
        f.write("Total 3584 B. Every byte accounted for, including the inter-sprite\n")
        f.write("zero-pad regions and the column-sharing between adjacent `enemy_*`\n")
        f.write("frames:\n\n")
        f.write("| File off | CPU addr | Size | Content |\n")
        f.write("|----------|----------|-----:|---------|\n")
        for i, sp in enumerate(explosion_lo):
            f.write(f"| `{sp.file_off:#06x}` | `&{sp.cpu_addr:04X}` | {sp.size:4d} | "
                    f"`{sp.filename}` — explosion frame {i} (also `lev_enemy_ptr_*[{21 + i}]`) |\n")
        # 32 B zero pad before the first enemy frame
        f.write(f"| `0x0200` | `&4C00` |   32 | zero-pad |\n")
        # enemy animation frames — describe overlap with previous where applicable
        prev_end = None
        for i, sp in enumerate(enemy_anim_sp):
            note = f"`{sp.filename}`"
            if prev_end is not None:
                if sp.file_off < prev_end:
                    overlap = prev_end - sp.file_off
                    note += f" — first {overlap} B (col 0) shared with previous frame's last col"
                elif sp.file_off > prev_end:
                    pad = sp.file_off - prev_end
                    f.write(f"| `{prev_end:#06x}` | `&{LEVD1_LOAD + prev_end:04X}` | {pad:4d} | zero-pad |\n")
            f.write(f"| `{sp.file_off:#06x}` | `&{sp.cpu_addr:04X}` | {sp.size:4d} | {note} |\n")
            prev_end = sp.file_off + sp.size
        if prev_end is not None and prev_end < PLAYER_OFF:
            pad = PLAYER_OFF - prev_end
            f.write(f"| `{prev_end:#06x}` | `&{LEVD1_LOAD + prev_end:04X}` | {pad:4d} | zero-pad |\n")
        f.write(f"| `{player_sprite.file_off:#06x}` | `&{player_sprite.cpu_addr:04X}` | {player_sprite.size:4d} | "
                f"`{player_sprite.filename}` — 6×22; last 4 bytes overlap `tile_00` first 4 bytes |\n")
        for tid, sp in enumerate(tile_sprite):
            f.write(f"| `{sp.file_off:#06x}` | `&{sp.cpu_addr:04X}` | {sp.size:4d} | "
                    f"`{sp.filename}` |\n")
        f.write(f"\nCoverage: 4×128 (explosion frames 0..3) + 32 pad + 7×96 enemy / enemy_hit (− shared cols + pads net 640 B) "
                f"+ 132 player + 18×128 tile − 4 overlap = **3584 B** ✓ (every byte of LEVD1 accounted for)\n")

        # ---- LEVD2 byte map
        f.write("\n## LEVD2 byte map\n\n")
        f.write("Total 3200 B. Every byte accounted for:\n\n")
        f.write("| File off | CPU addr | Size | Content |\n")
        f.write("|----------|----------|-----:|---------|\n")
        for i in range(hazard_count):
            off = LEVD2_ENEMY_OFF + i * SPRITE_SIZE
            f.write(f"| `{off:#06x}` | `&{LEVD2_LOAD + off:04X}` | {SPRITE_SIZE:4d} | "
                    f"`hazard_stage1_{i:02d}.png` (= `lev_hazard_ptr_*[{i + 1}]` for stage 1) |\n")
        f.write(f"| `{ENEMY_PTR_LO_OFF:#06x}` | `&{LEVD2_LOAD + ENEMY_PTR_LO_OFF:04X}` |   64 | `lev_enemy_ptr_lo` (32 × 1-byte) |\n")
        f.write(f"| `{ENEMY_PTR_HI_OFF:#06x}` | `&{LEVD2_LOAD + ENEMY_PTR_HI_OFF:04X}` |   64 | `lev_enemy_ptr_hi` (32 × 1-byte) |\n")
        f.write(f"| `{SPAWN_COL_OFF:#06x}` | `&{LEVD2_LOAD + SPAWN_COL_OFF:04X}` |  128 | `lev_spawn_col` (sorted asc, `&FF` end) |\n")
        f.write(f"| `{SPAWN_ATTR_OFF:#06x}` | `&{LEVD2_LOAD + SPAWN_ATTR_OFF:04X}` |  128 | `lev_spawn_attr` |\n")
        f.write(f"| `{explosion_04.file_off:#06x}` | `&{explosion_04.cpu_addr:04X}` | {explosion_04.size:4d} | "
                f"`{explosion_04.filename}` — explosion frame 4 (also `lev_enemy_ptr_*[25]`) |\n")
        f.write(f"| `{explosion_05.file_off:#06x}` | `&{explosion_05.cpu_addr:04X}` | {explosion_05.size:4d} | "
                f"`{explosion_05.filename}` — explosion frame 5 (also `lev_enemy_ptr_*[26]`) |\n")
        f.write(f"| `{ERASE_BRUSH_OFF:#06x}` | `&{LEVD2_LOAD + ERASE_BRUSH_OFF:04X}` |  272 | `lev_erase_brush` — all zeros |\n")
        f.write(f"| `{MAP_UPPER_OFF:#06x}` | `&{LEVD2_LOAD + MAP_UPPER_OFF:04X}` |  240 | `lev_map_upper` (one tile id per scroll col) |\n")
        f.write(f"| `{MAP_PAD_OFF:#06x}` | `&{LEVD2_LOAD + MAP_PAD_OFF:04X}` |   16 | gap / pad between the two map streams |\n")
        f.write(f"| `{MAP_LOWER_OFF:#06x}` | `&{LEVD2_LOAD + MAP_LOWER_OFF:04X}` |  240 | `lev_map_lower` |\n")
        bytes_in_levd2 = (hazard_count * SPRITE_SIZE + 64 + 64 + 128 + 128 +
                          explosion_04.size + explosion_05.size + 272 + 240 + 16 + 240)
        f.write(f"\n(Sum: {bytes_in_levd2} B = 14×128 (hazards) + 64 + 64 + 128 + 128 + 128 + 128 + 272 + 240 + 16 + 240 = 3200 ✓)\n")

        # ---- LEVD3 note + stage 2 hazards
        if len(levd3) >= len(levd2):
            f.write("\n## LEVD3 byte map\n\n")
            f.write("LEVD3 is the same shape as LEVD2 (3200 B, full overlay).\n")
            f.write("See LEVD2 byte map above for the layout; for this scenario\n")
            f.write("the sprite count, table offsets and map-stream positions are\n")
            f.write("identical, but the sprite bytes differ — stage 2 swaps in a\n")
            f.write("new set of 14 hazards (rendered as `hazard_stage2_NN.png`)\n")
            f.write("and a new spawn schedule.\n")
        else:
            f.write("\n## LEVD3 byte map\n\n")
            f.write(f"LEVD3 is 2176 B (`&880`) — only the first 2176 B of the\n")
            f.write("LEVD2 layout is overlaid. The 14 hazard sprites, the ptr LUT\n")
            f.write("and the spawn-column / spawn-attr tables ARE replaced (= the\n")
            f.write("stage-2-specific data); everything from `&0880` onwards —\n")
            f.write("explosion frames 4/5, erase brush, map tile streams — keeps\n")
            f.write("the LEVD2 bytes in RAM unchanged. So stage 2 has its own\n")
            f.write("hazards and spawn schedule but inherits the stage-1 map.\n")
            f.write("Stage-2 hazards are rendered as `hazard_stage2_NN.png`.\n")

        # ---- Map + spawn outputs
        f.write("\n## Map + spawn outputs\n\n")
        f.write("| File | Scope | Source |\n")
        f.write("|------|-------|--------|\n")
        f.write("| `map_strip.png` | level (both stages) | LEVD2 `lev_map_upper` + `lev_map_lower` — native 3840×160. The two stages of every scenario share the same tile streams, so one strip covers both. |\n")
        f.write("| `map_with_spawns_1.png` | stage 1 | map_strip + spawn-pin overlay (small coloured crosses, one per active spawn) |\n")
        f.write("| `map_with_spawns_2.png` | stage 2 | same, with stage-2 spawn schedule |\n")
        f.write("| `map_with_hazards_1.png` | stage 1 | map_strip with the **actual sprites** drawn at every spawn position, vertically mirrored where attr bit 7 is set — reads like a level-design schematic |\n")
        f.write("| `map_with_hazards_2.png` | stage 2 | same, for stage 2 |\n")
        f.write("| `spawn_table_stage1.md` | stage 1 | decoded spawn schedule |\n")
        f.write("| `spawn_table_stage2.md` | stage 2 | decoded spawn schedule |\n")
        f.write(f"\nStage 1: **{spawns_s1} spawn events** | Stage 2: **{spawns_s2} spawn events**\n\n")
        f.write("### Spawn-pin colour key (in `map_with_spawns_*.png`)\n\n")
        f.write("- **Green** — normal spawn.\n")
        f.write("- **Red** — `v-flip = 1`.\n")
        f.write("- **Yellow** — `type = 7` (force-field; renderer generates pixels via `lfsr_random`, no fixed sprite).\n\n")
        f.write("### Hazard-overlay notes (in `map_with_hazards_*.png`)\n\n")
        f.write("- Sprites are plotted at their resolved `lev_enemy_ptr_*` address with the level palette.\n")
        f.write("- Bit-7 v-flip is honoured — paired spawns at the same column produce ceiling-hanging + floor-rising decoration.\n")
        f.write("- `type = 7` (force-field) spawns appear as a 16×32 yellow box — the real one is a procedural noise strip (`forcefield_render`) and has no fixed sprite.\n")
        f.write("- Sprites whose `lev_enemy_ptr_*` slot resolves into GRAPHIX (slots 15 / 16 / 19) are drawn from `$.GRAPHIX` with the level palette so they pick up the per-scenario colours.\n")

        # ---- Raw data dumps
        f.write("\n## Raw data dumps (`data/`)\n\n")
        f.write("| File | Source |\n")
        f.write("|------|--------|\n")
        for stg in (1, 2):
            f.write(f"| `data/stage{stg}_spawn.bin` | 128 B `lev_spawn_col` |\n")
            f.write(f"| `data/stage{stg}_attr.bin` | 128 B `lev_spawn_attr` |\n")
            f.write(f"| `data/stage{stg}_map_upper.bin` | 240 B `lev_map_upper` |\n")
            f.write(f"| `data/stage{stg}_map_lower.bin` | 240 B `lev_map_lower` |\n")


# ---- driver ---------------------------------------------------------

def build_level(level: int):
    out_dir = f'levels/{level}'
    data_dir = f'{out_dir}/data'
    os.makedirs(data_dir, exist_ok=True)

    # Clean any old outputs from previous renderer passes (everything
    # under the level dir gets regenerated; we leave data/ alone — its
    # contents will be overwritten in place).
    for f in os.listdir(out_dir):
        if f.endswith('.png') or f.endswith('.md'):
            os.remove(f'{out_dir}/{f}')

    levd1, levd2, levd3 = load_levd(level)
    graphix = open('extracted/$.GRAPHIX', 'rb').read()
    palette = palette_for_level(level)
    blocks = build_sprite_inventory()
    hazard_blocks_s1 = build_hazard_blocks(1)
    hazard_blocks_s2 = build_hazard_blocks(2)

    write_sprites(out_dir, blocks, levd1, levd2, palette)
    write_sprites(out_dir, hazard_blocks_s1, levd1, levd2, palette)
    write_sprites(out_dir, hazard_blocks_s2, levd1, levd2, palette, levd3=levd3)

    # Map is shared between stages 1 and 2 (LEVD3 for scenarios 1-3
    # overlays only the lower half of LEVD2 — tile-id streams inherit;
    # for scenario 4 the LEVD3 tile streams happen to be byte-identical
    # to LEVD2's). Write one map_strip per level, not two.
    rgb, w, h = render_map_strip(levd1, levd2, palette)
    write_png(f'{out_dir}/map_strip.png', rgb, w, h)

    for stage in (1, 2):
        st = stage_data(level, stage, levd2, levd3)
        rgb, w, h = render_map_with_spawns(levd1, st, palette)
        write_png(f'{out_dir}/map_with_spawns_{stage}.png', rgb, w, h)
        rgb, w, h = render_map_with_hazards(levd1, levd2, graphix, st, palette)
        write_png(f'{out_dir}/map_with_hazards_{stage}.png', rgb, w, h)
        with open(f'{data_dir}/stage{stage}_spawn.bin', 'wb') as f:
            f.write(st[SPAWN_COL_OFF:SPAWN_COL_OFF + SPAWN_TABLE_LEN])
        with open(f'{data_dir}/stage{stage}_attr.bin', 'wb') as f:
            f.write(st[SPAWN_ATTR_OFF:SPAWN_ATTR_OFF + SPAWN_TABLE_LEN])
        with open(f'{data_dir}/stage{stage}_map_upper.bin', 'wb') as f:
            f.write(st[MAP_UPPER_OFF:MAP_UPPER_OFF + MAP_TABLE_LEN])
        with open(f'{data_dir}/stage{stage}_map_lower.bin', 'wb') as f:
            f.write(st[MAP_LOWER_OFF:MAP_LOWER_OFF + MAP_TABLE_LEN])
        write_spawn_table(f'{out_dir}/spawn_table_stage{stage}.md', st, stage)

    write_readme(f'{out_dir}/README.md', level, levd1, levd2, levd3, blocks)
    print(f'  level {level}: wrote {len(blocks)} sprite PNGs to {out_dir}/')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', type=int, choices=(1, 2, 3, 4))
    args = ap.parse_args()
    levels = (args.level,) if args.level else (1, 2, 3, 4)
    for lev in levels:
        build_level(lev)


if __name__ == '__main__':
    main()
