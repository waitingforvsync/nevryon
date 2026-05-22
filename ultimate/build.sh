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
# + white). --expected-bytes locks in the size from the prior commit;
# bump it deliberately if you repaint artwork.
$ENCODE_SPRITES --src assets/level1/tiles --out data/level1/tiles.6502 \
    --palette black,red,yellow,white   --label "Level 1 tiles" --expected-bytes 1547
$ENCODE_SPRITES --src assets/level2/tiles --out data/level2/tiles.6502 \
    --palette black,blue,cyan,white    --label "Level 2 tiles" --expected-bytes 1231
$ENCODE_SPRITES --src assets/level3/tiles --out data/level3/tiles.6502 \
    --palette black,red,green,white    --label "Level 3 tiles" --expected-bytes 1267
$ENCODE_SPRITES --src assets/level4/tiles --out data/level4/tiles.6502 \
    --palette black,red,magenta,white  --label "Level 4 tiles" --expected-bytes 1835

# Future encode invocations land here as the asset categories arrive:
#   * assets/level<N>/hazards_stage<S>/  -> data/level<N>/hazards_stage<S>.6502
#   * assets/level<N>/explosions/        -> data/level<N>/explosions.6502
#   * assets/level<N>/enemies/           -> data/level<N>/enemies.6502
#   * assets/shared/{player,flames,pickups,graphix_hazards}/ -> data/shared/*.6502
# The animating-sprite categories (player, enemies, flames, pickups)
# will use a different encoder mode (trim + raw blit, not RLE -- see
# ../docs/sprite_rle_notes.md "When to skip the RLE step").

echo
echo "==[ Phase 2 ]== assemble BeebAsm  (TODO)"
# beebasm -i nevryon.6502 -do nevryon.ssd -boot !BOOT -v

echo "==[ Phase 3 ]== build SSD disk image  (TODO)"

echo
echo "build complete."
