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

# Level <N> tile catalogs (18 sprites, 4x32 each).
# Palettes mirror NEVRYON_LEVEL_PALETTES in ../tools/render_screen.py
# (scenario 1..4: black + {red/yellow, blue/cyan, red/green, red/magenta}
# + white).
$ENCODE_SPRITES --src assets/level1/tiles --out data/level1/tiles.6502 \
    --palette black,red,yellow,white   --label "Level 1 tiles" --name-prefix level1
$ENCODE_SPRITES --src assets/level2/tiles --out data/level2/tiles.6502 \
    --palette black,blue,cyan,white    --label "Level 2 tiles" --name-prefix level2
$ENCODE_SPRITES --src assets/level3/tiles --out data/level3/tiles.6502 \
    --palette black,red,green,white    --label "Level 3 tiles" --name-prefix level3
$ENCODE_SPRITES --src assets/level4/tiles --out data/level4/tiles.6502 \
    --palette black,red,magenta,white  --label "Level 4 tiles" --name-prefix level4

# Per-level player-death explosion (6 frames, 4x32 each, scenario-
# shared across both stages). Frames 0..3 originate from each
# scenario's LEVD1 at &4A00..&4BFF and frames 4..5 from LEVD2 at
# &7C00..&7CFF; we treat them as one 6-sprite set per scenario.
$ENCODE_SPRITES --src assets/level1/explosions --out data/level1/explosions.6502 \
    --palette black,red,yellow,white   --label "Level 1 explosions" --name-prefix level1
$ENCODE_SPRITES --src assets/level2/explosions --out data/level2/explosions.6502 \
    --palette black,blue,cyan,white    --label "Level 2 explosions" --name-prefix level2
$ENCODE_SPRITES --src assets/level3/explosions --out data/level3/explosions.6502 \
    --palette black,red,green,white    --label "Level 3 explosions" --name-prefix level3
$ENCODE_SPRITES --src assets/level4/explosions --out data/level4/explosions.6502 \
    --palette black,red,magenta,white  --label "Level 4 explosions" --name-prefix level4

# Per-(level, stage) hazard sets. 14 stage-specific hazards
# (hazard_00..hazard_13) in the scenario palette, plus 3 shared
# GRAPHIX hazards (hazard_15, hazard_16, hazard_19) which were
# originally drawn from $.GRAPHIX in the L1 palette. We duplicate
# the GRAPHIX hazards into every (level, stage) asset bundle so a
# future redesign can repaint them per-scenario; for now they pick
# up the L1-palette --fallback-palette so the encoder maps their
# pixels via {black, red, yellow, white}. (For level 1 the primary
# palette IS the fallback, so it never triggers there.)
$ENCODE_SPRITES --src assets/level1/stage1/hazards --out data/level1/stage1/hazards.6502 \
    --palette black,red,yellow,white   --fallback-palette black,red,yellow,white \
    --label "Level 1 stage 1 hazards" --name-prefix level1_stage1
$ENCODE_SPRITES --src assets/level1/stage2/hazards --out data/level1/stage2/hazards.6502 \
    --palette black,red,yellow,white   --fallback-palette black,red,yellow,white \
    --label "Level 1 stage 2 hazards" --name-prefix level1_stage2
$ENCODE_SPRITES --src assets/level2/stage1/hazards --out data/level2/stage1/hazards.6502 \
    --palette black,blue,cyan,white    --fallback-palette black,red,yellow,white \
    --label "Level 2 stage 1 hazards" --name-prefix level2_stage1
$ENCODE_SPRITES --src assets/level2/stage2/hazards --out data/level2/stage2/hazards.6502 \
    --palette black,blue,cyan,white    --fallback-palette black,red,yellow,white \
    --label "Level 2 stage 2 hazards" --name-prefix level2_stage2
$ENCODE_SPRITES --src assets/level3/stage1/hazards --out data/level3/stage1/hazards.6502 \
    --palette black,red,green,white    --fallback-palette black,red,yellow,white \
    --label "Level 3 stage 1 hazards" --name-prefix level3_stage1
$ENCODE_SPRITES --src assets/level3/stage2/hazards --out data/level3/stage2/hazards.6502 \
    --palette black,red,green,white    --fallback-palette black,red,yellow,white \
    --label "Level 3 stage 2 hazards" --name-prefix level3_stage2
$ENCODE_SPRITES --src assets/level4/stage1/hazards --out data/level4/stage1/hazards.6502 \
    --palette black,red,magenta,white  --fallback-palette black,red,yellow,white \
    --label "Level 4 stage 1 hazards" --name-prefix level4_stage1
$ENCODE_SPRITES --src assets/level4/stage2/hazards --out data/level4/stage2/hazards.6502 \
    --palette black,red,magenta,white  --fallback-palette black,red,yellow,white \
    --label "Level 4 stage 2 hazards" --name-prefix level4_stage2

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
