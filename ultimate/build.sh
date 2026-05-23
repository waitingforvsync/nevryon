#!/usr/bin/env bash
# Nevryon Ultimate build script.
#
# Phases:
#   1. encode assets/ -> data/   (compressed BeebAsm sources via scheme C RLE)
#   2. assemble BeebAsm           (TODO -- when there's something to assemble)
#   3. build SSD disk image       (TODO)
#
# Re-runnable: regenerates everything from sources. Asserts each
# encoded blob matches its known-good byte count (regression check).

set -euo pipefail
cd "$(dirname "$0")"

ENCODE_SPRITES="python3 tools/encode_sprites.py"

echo "==[ Phase 1 ]== encode assets/ -> data/"

# The encoder auto-detects each sprite's palette from its PNG pixels
# and assigns BBC physical colours to logical 0..3 in brightness order
# (black < blue < red < magenta < green < cyan < yellow < white).
# Each sprite emits its own <name>_colour0..3 metadata symbols (or
# colour_unused for unfilled slots), so editing colours in a pixel
# editor flows through to the runtime palette setup.

# Level <N> tile catalogs (18 sprites, 4x32 each).
$ENCODE_SPRITES --src assets/level1/tiles --out data/level1/tiles.6502 \
    --label "Level 1 tiles" --name-prefix level1
$ENCODE_SPRITES --src assets/level2/tiles --out data/level2/tiles.6502 \
    --label "Level 2 tiles" --name-prefix level2
$ENCODE_SPRITES --src assets/level3/tiles --out data/level3/tiles.6502 \
    --label "Level 3 tiles" --name-prefix level3
$ENCODE_SPRITES --src assets/level4/tiles --out data/level4/tiles.6502 \
    --label "Level 4 tiles" --name-prefix level4

# Per-level player-death explosion (6 frames, 4x32 each, scenario-
# shared across both stages). Frames 0..3 originate from each
# scenario's LEVD1 at &4A00..&4BFF and frames 4..5 from LEVD2 at
# &7C00..&7CFF; we treat them as one 6-sprite set per scenario.
$ENCODE_SPRITES --src assets/level1/explosions --out data/level1/explosions.6502 \
    --label "Level 1 explosions" --name-prefix level1
$ENCODE_SPRITES --src assets/level2/explosions --out data/level2/explosions.6502 \
    --label "Level 2 explosions" --name-prefix level2
$ENCODE_SPRITES --src assets/level3/explosions --out data/level3/explosions.6502 \
    --label "Level 3 explosions" --name-prefix level3
$ENCODE_SPRITES --src assets/level4/explosions --out data/level4/explosions.6502 \
    --label "Level 4 explosions" --name-prefix level4

# Per-(level, stage) hazard sets. 14 stage-specific hazards
# (hazard_00..hazard_13) plus 3 game-shared GRAPHIX hazards
# (hazard_15, hazard_16, hazard_19) duplicated per (level, stage)
# so future redesigns can repaint them per scenario. The shared
# ones are currently painted in L1 colours so the encoder lays
# them out as black/red/yellow/white -> logical 0/1/2/3; the
# runtime metadata is per-sprite, so the colours travel with the
# sprite.
$ENCODE_SPRITES --src assets/level1/stage1/hazards --out data/level1/stage1/hazards.6502 \
    --label "Level 1 stage 1 hazards" --name-prefix level1_stage1
$ENCODE_SPRITES --src assets/level1/stage2/hazards --out data/level1/stage2/hazards.6502 \
    --label "Level 1 stage 2 hazards" --name-prefix level1_stage2
$ENCODE_SPRITES --src assets/level2/stage1/hazards --out data/level2/stage1/hazards.6502 \
    --label "Level 2 stage 1 hazards" --name-prefix level2_stage1
$ENCODE_SPRITES --src assets/level2/stage2/hazards --out data/level2/stage2/hazards.6502 \
    --label "Level 2 stage 2 hazards" --name-prefix level2_stage2
$ENCODE_SPRITES --src assets/level3/stage1/hazards --out data/level3/stage1/hazards.6502 \
    --label "Level 3 stage 1 hazards" --name-prefix level3_stage1
$ENCODE_SPRITES --src assets/level3/stage2/hazards --out data/level3/stage2/hazards.6502 \
    --label "Level 3 stage 2 hazards" --name-prefix level3_stage2
$ENCODE_SPRITES --src assets/level4/stage1/hazards --out data/level4/stage1/hazards.6502 \
    --label "Level 4 stage 1 hazards" --name-prefix level4_stage1
$ENCODE_SPRITES --src assets/level4/stage2/hazards --out data/level4/stage2/hazards.6502 \
    --label "Level 4 stage 2 hazards" --name-prefix level4_stage2

# Game-shared HUD bitmap (160x16 px = 40x16 byte-columns). Lives in
# the static 2-line strip below the playfield (CRTC vertical-rupture
# split). No --name-prefix: there's exactly one HUD for the whole
# game, so the bare "hud_" symbols don't collide with anything.
$ENCODE_SPRITES --src assets/hud --out data/hud.6502 \
    --label "HUD"

# Future encode invocations land here as the asset categories arrive:
#   * assets/level<N>/enemies/           -> data/level<N>/enemies.6502
#   * assets/shared/{player,flames,pickups}/ -> data/shared/*.6502
# The animating-sprite categories (player, enemies, flames, pickups)
# will use a different encoder mode (trim + raw blit, not RLE -- see
# ../docs/sprite_rle_notes.md "When to skip the RLE step").

echo
echo "==[ Phase 2 ]== assemble BeebAsm  (TODO)"
# beebasm -i nevryon.6502 -do nevryon.ssd -boot !BOOT -v

echo "==[ Phase 3 ]== build SSD disk image  (TODO)"

echo
echo "build complete."
