# Level 1

Palette: black / red / yellow / white  (Battle Cruiser)

LEVD1: 3584 B (`&E00`)
LEVD2: 3200 B (`0x0c80`)
LEVD3: 2176 B (`0x0880`) — lower-half overlay (2176 B; tile streams inherit from LEVD2)

## Sprite inventory

Every unique block of bytes in the LEVD files that the
engine reads as sprite data is exported as a PNG. Names
are semantic rather than sequential — six categories cover
all of the per-level sprite data:

| Category | Files | What it is |
|----------|-------|------------|
| `explosion_NN` | `explosion_00..05` | The 6 frames of the player death-explosion animation. Frames 00..03 live in LEVD1 (`&4A00..&4BFF`); frames 04..05 live in LEVD2 (`&7C00..&7CFF`). The same 6 byte-pairs also appear in `lev_hazard_ptr_*` slots 21..26 — that's how `death_anim` (CODE `&1E47`) reaches them. |
| `enemy_NN` | `enemy_00..03` | 4 frames of the per-scenario small flying enemy. 4×24 (96 B) each; the state machine in CODE `L1BE3` cycles through these as states 1..4. |
| `enemy_hit_NN` | `enemy_hit_01..03` | 3 frames of the same enemy's hit / destruction cycle. 4×24 (96 B) each; state machine states `&0A..&0C`. Numbered 01..03 to keep the index in step with the state-machine state values (the LEVD1 designer left `enemy_hit_00` empty / unused). |
| `player_sprite` | `player_sprite` | The 6×22 (132 B) player ship at LEVD1 `&4E80`. |
| `tile_NN` | `tile_00..17` | The 18-slot per-scenario map tile catalog (LEVD1 `&4F00 + N*&80`, each 4×32 = 128 B). |
| `hazard_stageN_NN` | `hazard_stage1_00..13` + `hazard_stage2_00..13` | The 14 hazard sprites for each stage (large stationary threats — gun-towers, tanks, structures). 4×32 (128 B) each. Stage 1 sprites come from LEVD2 `&7380..&7A00`, stage 2 sprites from LEVD3 at the same offsets (LEVD3 overlays the LEVD2 sprite block in RAM when stage 2 loads). The ptr LUT entries at `&7A80..&7AFF` are identical between LEVD2 and LEVD3, so slot N points at the same offset in both; only the sprite bytes differ. |

### Per-sprite details

| PNG | File | Bytes (file off) | CPU addr | Shape | Render dims |
|-----|------|------------------|----------|-------|-------------|
| `explosion_00.png` | LEVD1 | `0x0000..0x007f` (128) | `&4A00..&4A7F` | 4×32 col-major | 16×32 px |
| `explosion_01.png` | LEVD1 | `0x0080..0x00ff` (128) | `&4A80..&4AFF` | 4×32 col-major | 16×32 px |
| `explosion_02.png` | LEVD1 | `0x0100..0x017f` (128) | `&4B00..&4B7F` | 4×32 col-major | 16×32 px |
| `explosion_03.png` | LEVD1 | `0x0180..0x01ff` (128) | `&4B80..&4BFF` | 4×32 col-major | 16×32 px |
| `enemy_hit_01.png` | LEVD1 | `0x0220..0x027f` (96) | `&4C20..&4C7F` | 4×24 col-major | 16×24 px |
| `enemy_hit_02.png` | LEVD1 | `0x0268..0x02c7` (96) | `&4C68..&4CC7` | 4×24 col-major | 16×24 px |
| `enemy_hit_03.png` | LEVD1 | `0x02b0..0x030f` (96) | `&4CB0..&4D0F` | 4×24 col-major | 16×24 px |
| `enemy_00.png` | LEVD1 | `0x0300..0x035f` (96) | `&4D00..&4D5F` | 4×24 col-major | 16×24 px |
| `enemy_01.png` | LEVD1 | `0x0348..0x03a7` (96) | `&4D48..&4DA7` | 4×24 col-major | 16×24 px |
| `enemy_02.png` | LEVD1 | `0x03b0..0x040f` (96) | `&4DB0..&4E0F` | 4×24 col-major | 16×24 px |
| `enemy_03.png` | LEVD1 | `0x0410..0x046f` (96) | `&4E10..&4E6F` | 4×24 col-major | 16×24 px |
| `player_sprite.png` | LEVD1 | `0x0480..0x0503` (132) | `&4E80..&4F03` | 6×22 col-major | 24×22 px |
| `tile_00.png` | LEVD1 | `0x0500..0x057f` (128) | `&4F00..&4F7F` | 4×32 col-major | 16×32 px |
| `tile_01.png` | LEVD1 | `0x0580..0x05ff` (128) | `&4F80..&4FFF` | 4×32 col-major | 16×32 px |
| `tile_02.png` | LEVD1 | `0x0600..0x067f` (128) | `&5000..&507F` | 4×32 col-major | 16×32 px |
| `tile_03.png` | LEVD1 | `0x0680..0x06ff` (128) | `&5080..&50FF` | 4×32 col-major | 16×32 px |
| `tile_04.png` | LEVD1 | `0x0700..0x077f` (128) | `&5100..&517F` | 4×32 col-major | 16×32 px |
| `tile_05.png` | LEVD1 | `0x0780..0x07ff` (128) | `&5180..&51FF` | 4×32 col-major | 16×32 px |
| `tile_06.png` | LEVD1 | `0x0800..0x087f` (128) | `&5200..&527F` | 4×32 col-major | 16×32 px |
| `tile_07.png` | LEVD1 | `0x0880..0x08ff` (128) | `&5280..&52FF` | 4×32 col-major | 16×32 px |
| `tile_08.png` | LEVD1 | `0x0900..0x097f` (128) | `&5300..&537F` | 4×32 col-major | 16×32 px |
| `tile_09.png` | LEVD1 | `0x0980..0x09ff` (128) | `&5380..&53FF` | 4×32 col-major | 16×32 px |
| `tile_10.png` | LEVD1 | `0x0a00..0x0a7f` (128) | `&5400..&547F` | 4×32 col-major | 16×32 px |
| `tile_11.png` | LEVD1 | `0x0a80..0x0aff` (128) | `&5480..&54FF` | 4×32 col-major | 16×32 px |
| `tile_12.png` | LEVD1 | `0x0b00..0x0b7f` (128) | `&5500..&557F` | 4×32 col-major | 16×32 px |
| `tile_13.png` | LEVD1 | `0x0b80..0x0bff` (128) | `&5580..&55FF` | 4×32 col-major | 16×32 px |
| `tile_14.png` | LEVD1 | `0x0c00..0x0c7f` (128) | `&5600..&567F` | 4×32 col-major | 16×32 px |
| `tile_15.png` | LEVD1 | `0x0c80..0x0cff` (128) | `&5680..&56FF` | 4×32 col-major | 16×32 px |
| `tile_16.png` | LEVD1 | `0x0d00..0x0d7f` (128) | `&5700..&577F` | 4×32 col-major | 16×32 px |
| `tile_17.png` | LEVD1 | `0x0d80..0x0dff` (128) | `&5780..&57FF` | 4×32 col-major | 16×32 px |
| `explosion_04.png` | LEVD2 | `0x0880..0x08ff` (128) | `&7C00..&7C7F` | 4×32 col-major | 16×32 px |
| `explosion_05.png` | LEVD2 | `0x0900..0x097f` (128) | `&7C80..&7CFF` | 4×32 col-major | 16×32 px |

*Notes on sprite shapes / overlap*:

- The 6 `explosion_*` sprites are 4×32 (128 B each). Frames
  00..03 live consecutively in LEVD1, then there's a 96-byte
  zero pad and the per-scenario `enemy_*` strip; frames
  04..05 live in LEVD2 at `&7C00`/`&7C80`. The split-across-
  files layout is unusual but consistent with the level
  designer's memory packing: LEVD1 is per-scenario only
  (palette differs), while the explosion's pointer table
  lives in LEVD2 (per-stage) and happens to have spare slots
  for the last two frames.
- The 7 `enemy_*` / `enemy_hit_*` sprites are 4×24 (96 B).
  Adjacent frames in the strip *share a column* of 24 bytes —
  e.g. the 24 bytes at `&4D00..&4D17` are simultaneously the
  last column of `enemy_hit_03` and the first column of
  `enemy_00`. The state machine reads each frame as a complete
  4×24 block; the sharing is byte-packing.
- `player_sprite` is 6×22 (132 B) and overlaps the first 4 bytes
  of `tile_00` (both are zero in that region — overlap is benign).
- All 18 `tile_*` and all 16 LEVD2 `hazard_*` / `explosion_04/05`
  sprites are 4×32 (128 B each).

## Table indices → sprite

### `lev_player_sprite` (&4E80)

Always `player_sprite.png` — the only entry in this table.

### `lev_tile_catalog` (&4F00 + N*&80, N = 0..17)

| Tile id | CPU addr | sprite | Notes |
|--------:|----------|--------|-------|
|       0 | `&4F00` | `tile_00.png` |  |
|       1 | `&4F80` | `tile_01.png` |  |
|       2 | `&5000` | `tile_02.png` |  |
|       3 | `&5080` | `tile_03.png` |  |
|       4 | `&5100` | `tile_04.png` |  |
|       5 | `&5180` | `tile_05.png` |  |
|       6 | `&5200` | `tile_06.png` | **all-zero (blank tile)** |
|       7 | `&5280` | `tile_07.png` |  |
|       8 | `&5300` | `tile_08.png` |  |
|       9 | `&5380` | `tile_09.png` |  |
|      10 | `&5400` | `tile_10.png` |  |
|      11 | `&5480` | `tile_11.png` |  |
|      12 | `&5500` | `tile_12.png` |  |
|      13 | `&5580` | `tile_13.png` |  |
|      14 | `&5600` | `tile_14.png` |  |
|      15 | `&5680` | `tile_15.png` |  |
|      16 | `&5700` | `tile_16.png` |  |
|      17 | `&5780` | `tile_17.png` |  |

### `lev_hazard_ptr_lo` / `lev_hazard_ptr_hi` (&7A80 / &7AC0, 32 slots)

`lev_hazard_ptr_*[N]` is read whenever a hazard of type N
(bits 0..4 of `lev_spawn_attr`) is plotted. Slots 1..14 are
per-stage — same pointer in LEVD2 and LEVD3, but the bytes
they point at differ, so each slot resolves to a different
PNG per stage (shown as `stage1 / stage2`).

| Slot | Pointer | Resolves to | Aliases |
|-----:|---------|-------------|---------|
|    0 | `&7D80` | `lev_erase_brush + &80` *(all-zero erase rectangle)* |  |
|    1 | `&7380` | `hazard_stage1_00.png` / `hazard_stage2_00.png` (S1 / S2) |  |
|    2 | `&7400` | `hazard_stage1_01.png` / `hazard_stage2_01.png` (S1 / S2) |  |
|    3 | `&7480` | `hazard_stage1_02.png` / `hazard_stage2_02.png` (S1 / S2) |  |
|    4 | `&7500` | `hazard_stage1_03.png` / `hazard_stage2_03.png` (S1 / S2) |  |
|    5 | `&7580` | `hazard_stage1_04.png` / `hazard_stage2_04.png` (S1 / S2) |  |
|    6 | `&7600` | `hazard_stage1_05.png` / `hazard_stage2_05.png` (S1 / S2) |  |
|    7 | `&7680` | `hazard_stage1_06.png` / `hazard_stage2_06.png` (S1 / S2) |  |
|    8 | `&7700` | `hazard_stage1_07.png` / `hazard_stage2_07.png` (S1 / S2) |  |
|    9 | `&7780` | `hazard_stage1_08.png` / `hazard_stage2_08.png` (S1 / S2) |  |
|   10 | `&7800` | `hazard_stage1_09.png` / `hazard_stage2_09.png` (S1 / S2) |  |
|   11 | `&7880` | `hazard_stage1_10.png` / `hazard_stage2_10.png` (S1 / S2) |  |
|   12 | `&7900` | `hazard_stage1_11.png` / `hazard_stage2_11.png` (S1 / S2) |  |
|   13 | `&7980` | `hazard_stage1_12.png` / `hazard_stage2_12.png` (S1 / S2) |  |
|   14 | `&7A00` | `hazard_stage1_13.png` / `hazard_stage2_13.png` (S1 / S2) |  |
|   15 | `&3700` | GRAPHIX `gfx_hazard_slot15` *(not exported here)* |  |
|   16 | `&3780` | GRAPHIX `gfx_hazard_slot16` *(not exported here)* |  |
|   17 | `&5180` | `tile_05.png` (tile_05) |  |
|   18 | `&5100` | `tile_04.png` (tile_04) |  |
|   19 | `&4360` | GRAPHIX `gfx_hazard_slot19` *(not exported here)* |  |
|   20 | `&0000` | *(unused — pointer pair is &0000)* |  |
|   21 | `&4A00` | `explosion_00.png` (explosion_00) | `lev_explosion_ptr_*[0]` (= explosion frame 0) |
|   22 | `&4A80` | `explosion_01.png` (explosion_01) | `lev_explosion_ptr_*[1]` (= explosion frame 1) |
|   23 | `&4B00` | `explosion_02.png` (explosion_02) | `lev_explosion_ptr_*[2]` (= explosion frame 2) |
|   24 | `&4B80` | `explosion_03.png` (explosion_03) | `lev_explosion_ptr_*[3]` (= explosion frame 3) |
|   25 | `&7C00` | `explosion_04.png` (explosion_04) | `lev_explosion_ptr_*[4]` (= explosion frame 4) |
|   26 | `&7C80` | `explosion_05.png` (explosion_05) | `lev_explosion_ptr_*[5]` (= explosion frame 5) |
|   27 | `&7D80` | `lev_erase_brush + &80` *(all-zero erase rectangle)* |  |
|   28 | `&0000` | *(unused — pointer pair is &0000)* |  |
|   29 | `&0000` | *(unused — pointer pair is &0000)* |  |
|   30 | `&0000` | *(unused — pointer pair is &0000)* |  |
|   31 | `&0000` | *(unused — pointer pair is &0000)* |  |

### `lev_explosion_ptr_lo` / `lev_explosion_ptr_hi` (&7A95 / &7AD5, 6 entries)

**Same physical bytes** as `lev_hazard_ptr_*[21..26]`. The
6-frame player-death explosion (CODE `death_anim` at
`&1E47`) reads its source pointers here. Each frame is
plotted as 4×32 (so frames 0..3 use the *full* 128-B
`explosion_00..03` blocks in LEVD1, while frames 4..5 use
the 128-B `explosion_04` / `explosion_05` blocks in LEVD2 —
those are 4×32 blocks too, distinct from the 4×24 `enemy_*`
/ `enemy_hit_*` sprites in LEVD1 which are a DIFFERENT
animation entirely, used by the L1BE3 state machine).

| Frame | Pointer | Resolves to |
|------:|---------|-------------|
|     0 | `&4A00` | `explosion_00.png` (explosion_00) |
|     1 | `&4A80` | `explosion_01.png` (explosion_01) |
|     2 | `&4B00` | `explosion_02.png` (explosion_02) |
|     3 | `&4B80` | `explosion_03.png` (explosion_03) |
|     4 | `&7C00` | `explosion_04.png` (explosion_04) |
|     5 | `&7C80` | `explosion_05.png` (explosion_05) |

## LEVD1 byte map

Total 3584 B. Every byte accounted for, including the inter-sprite
zero-pad regions and the column-sharing between adjacent `enemy_*`
frames:

| File off | CPU addr | Size | Content |
|----------|----------|-----:|---------|
| `0x0000` | `&4A00` |  128 | `explosion_00.png` — explosion frame 0 (also `lev_hazard_ptr_*[21]`) |
| `0x0080` | `&4A80` |  128 | `explosion_01.png` — explosion frame 1 (also `lev_hazard_ptr_*[22]`) |
| `0x0100` | `&4B00` |  128 | `explosion_02.png` — explosion frame 2 (also `lev_hazard_ptr_*[23]`) |
| `0x0180` | `&4B80` |  128 | `explosion_03.png` — explosion frame 3 (also `lev_hazard_ptr_*[24]`) |
| `0x0200` | `&4C00` |   32 | zero-pad |
| `0x0220` | `&4C20` |   96 | `enemy_hit_01.png` |
| `0x0268` | `&4C68` |   96 | `enemy_hit_02.png` — first 24 B (col 0) shared with previous frame's last col |
| `0x02b0` | `&4CB0` |   96 | `enemy_hit_03.png` — first 24 B (col 0) shared with previous frame's last col |
| `0x0300` | `&4D00` |   96 | `enemy_00.png` — first 16 B (col 0) shared with previous frame's last col |
| `0x0348` | `&4D48` |   96 | `enemy_01.png` — first 24 B (col 0) shared with previous frame's last col |
| `0x03a8` | `&4DA8` |    8 | zero-pad |
| `0x03b0` | `&4DB0` |   96 | `enemy_02.png` |
| `0x0410` | `&4E10` |   96 | `enemy_03.png` |
| `0x0470` | `&4E70` |   16 | zero-pad |
| `0x0480` | `&4E80` |  132 | `player_sprite.png` — 6×22; last 4 bytes overlap `tile_00` first 4 bytes |
| `0x0500` | `&4F00` |  128 | `tile_00.png` |
| `0x0580` | `&4F80` |  128 | `tile_01.png` |
| `0x0600` | `&5000` |  128 | `tile_02.png` |
| `0x0680` | `&5080` |  128 | `tile_03.png` |
| `0x0700` | `&5100` |  128 | `tile_04.png` |
| `0x0780` | `&5180` |  128 | `tile_05.png` |
| `0x0800` | `&5200` |  128 | `tile_06.png` |
| `0x0880` | `&5280` |  128 | `tile_07.png` |
| `0x0900` | `&5300` |  128 | `tile_08.png` |
| `0x0980` | `&5380` |  128 | `tile_09.png` |
| `0x0a00` | `&5400` |  128 | `tile_10.png` |
| `0x0a80` | `&5480` |  128 | `tile_11.png` |
| `0x0b00` | `&5500` |  128 | `tile_12.png` |
| `0x0b80` | `&5580` |  128 | `tile_13.png` |
| `0x0c00` | `&5600` |  128 | `tile_14.png` |
| `0x0c80` | `&5680` |  128 | `tile_15.png` |
| `0x0d00` | `&5700` |  128 | `tile_16.png` |
| `0x0d80` | `&5780` |  128 | `tile_17.png` |

Coverage: 4×128 (explosion frames 0..3) + 32 pad + 7×96 enemy / enemy_hit (− shared cols + pads net 640 B) + 132 player + 18×128 tile − 4 overlap = **3584 B** ✓ (every byte of LEVD1 accounted for)

## LEVD2 byte map

Total 3200 B. Every byte accounted for:

| File off | CPU addr | Size | Content |
|----------|----------|-----:|---------|
| `0x0000` | `&7380` |  128 | `hazard_stage1_00.png` (= `lev_hazard_ptr_*[1]` for stage 1) |
| `0x0080` | `&7400` |  128 | `hazard_stage1_01.png` (= `lev_hazard_ptr_*[2]` for stage 1) |
| `0x0100` | `&7480` |  128 | `hazard_stage1_02.png` (= `lev_hazard_ptr_*[3]` for stage 1) |
| `0x0180` | `&7500` |  128 | `hazard_stage1_03.png` (= `lev_hazard_ptr_*[4]` for stage 1) |
| `0x0200` | `&7580` |  128 | `hazard_stage1_04.png` (= `lev_hazard_ptr_*[5]` for stage 1) |
| `0x0280` | `&7600` |  128 | `hazard_stage1_05.png` (= `lev_hazard_ptr_*[6]` for stage 1) |
| `0x0300` | `&7680` |  128 | `hazard_stage1_06.png` (= `lev_hazard_ptr_*[7]` for stage 1) |
| `0x0380` | `&7700` |  128 | `hazard_stage1_07.png` (= `lev_hazard_ptr_*[8]` for stage 1) |
| `0x0400` | `&7780` |  128 | `hazard_stage1_08.png` (= `lev_hazard_ptr_*[9]` for stage 1) |
| `0x0480` | `&7800` |  128 | `hazard_stage1_09.png` (= `lev_hazard_ptr_*[10]` for stage 1) |
| `0x0500` | `&7880` |  128 | `hazard_stage1_10.png` (= `lev_hazard_ptr_*[11]` for stage 1) |
| `0x0580` | `&7900` |  128 | `hazard_stage1_11.png` (= `lev_hazard_ptr_*[12]` for stage 1) |
| `0x0600` | `&7980` |  128 | `hazard_stage1_12.png` (= `lev_hazard_ptr_*[13]` for stage 1) |
| `0x0680` | `&7A00` |  128 | `hazard_stage1_13.png` (= `lev_hazard_ptr_*[14]` for stage 1) |
| `0x0700` | `&7A80` |   64 | `lev_hazard_ptr_lo` (32 × 1-byte) |
| `0x0740` | `&7AC0` |   64 | `lev_hazard_ptr_hi` (32 × 1-byte) |
| `0x0780` | `&7B00` |  128 | `lev_spawn_col` (sorted asc, `&FF` end) |
| `0x0800` | `&7B80` |  128 | `lev_spawn_attr` |
| `0x0880` | `&7C00` |  128 | `explosion_04.png` — explosion frame 4 (also `lev_hazard_ptr_*[25]`) |
| `0x0900` | `&7C80` |  128 | `explosion_05.png` — explosion frame 5 (also `lev_hazard_ptr_*[26]`) |
| `0x0980` | `&7D00` |  272 | `lev_erase_brush` — all zeros |
| `0x0a90` | `&7E10` |  240 | `lev_map_upper` (one tile id per scroll col) |
| `0x0b80` | `&7F00` |   16 | gap / pad between the two map streams |
| `0x0b90` | `&7F10` |  240 | `lev_map_lower` |

(Sum: 3200 B = 14×128 (hazards) + 64 + 64 + 128 + 128 + 128 + 128 + 272 + 240 + 16 + 240 = 3200 ✓)

## LEVD3 byte map

LEVD3 is 2176 B (`&880`) — only the first 2176 B of the
LEVD2 layout is overlaid. The 14 hazard sprites, the ptr LUT
and the spawn-column / spawn-attr tables ARE replaced (= the
stage-2-specific data); everything from `&0880` onwards —
explosion frames 4/5, erase brush, map tile streams — keeps
the LEVD2 bytes in RAM unchanged. So stage 2 has its own
hazards and spawn schedule but inherits the stage-1 map.
Stage-2 hazards are rendered as `hazard_stage2_NN.png`.

## Map + spawn outputs

| File | Scope | Source |
|------|-------|--------|
| `map_strip.png` | level (both stages) | LEVD2 `lev_map_upper` + `lev_map_lower` — native 3840×160. The two stages of every scenario share the same tile streams, so one strip covers both. |
| `map_with_spawns_1.png` | stage 1 | map_strip + spawn-pin overlay (small coloured crosses, one per active spawn) |
| `map_with_spawns_2.png` | stage 2 | same, with stage-2 spawn schedule |
| `map_with_hazards_1.png` | stage 1 | map_strip with the **actual sprites** drawn at every spawn position, vertically mirrored where attr bit 7 is set — reads like a level-design schematic |
| `map_with_hazards_2.png` | stage 2 | same, for stage 2 |
| `spawn_table_stage1.md` | stage 1 | decoded spawn schedule |
| `spawn_table_stage2.md` | stage 2 | decoded spawn schedule |

Stage 1: **61 spawn events** | Stage 2: **74 spawn events**

### Spawn-pin colour key (in `map_with_spawns_*.png`)

- **Green** — normal spawn.
- **Red** — `v-flip = 1`.
- **Yellow** — `type = 7` (force-field; renderer generates pixels via `lfsr_random`, no fixed sprite).

### Hazard-overlay notes (in `map_with_hazards_*.png`)

- Sprites are plotted at their resolved `lev_hazard_ptr_*` address with the level palette.
- Bit-7 v-flip is honoured — paired spawns at the same column produce ceiling-hanging + floor-rising decoration.
- `type = 7` (force-field) spawns appear as a 16×32 yellow box — the real one is a procedural noise strip (`forcefield_render`) and has no fixed sprite.
- Sprites whose `lev_hazard_ptr_*` slot resolves into GRAPHIX (slots 15 / 16 / 19) are drawn from `$.GRAPHIX` with the level palette so they pick up the per-scenario colours.

## Raw data dumps (`data/`)

| File | Source |
|------|--------|
| `data/stage1_spawn.bin` | 128 B `lev_spawn_col` |
| `data/stage1_attr.bin` | 128 B `lev_spawn_attr` |
| `data/stage1_map_upper.bin` | 240 B `lev_map_upper` |
| `data/stage1_map_lower.bin` | 240 B `lev_map_lower` |
| `data/stage2_spawn.bin` | 128 B `lev_spawn_col` |
| `data/stage2_attr.bin` | 128 B `lev_spawn_attr` |
| `data/stage2_map_upper.bin` | 240 B `lev_map_upper` |
| `data/stage2_map_lower.bin` | 240 B `lev_map_lower` |
