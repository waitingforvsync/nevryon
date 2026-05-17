# Nevryon CPU memory map

This is a single-page picture of where everything lives in the BBC's
6502 address space while Nevryon is running. The layout is fixed at
load time by Loader2 / Loader3 / Loader4 (see `docs/file_layout.md`
for the on-disk side) and never moves once gameplay starts; only the
per-stage LEVD2/LEVD3 reload changes the contents of the upper
region between levels.

Conventions:

- `*` after a range means the on-disk file is bigger than the listed
  CPU window because the catalog load address has a tube/host bit
  set — only the low 16 bits matter for CPU layout.
- *level-relative* labels in `lev_*` form are defined in
  `disasm/Nevryon.6502` and are reloaded each stage.
- Page numbers in parentheses (e.g. `(p.59)`) refer to the
  catalog's start-sector for that file (see `extracted/_manifest.tsv`).

```
&0000 ┌─────────────────────────────────────────────────────────┐
      │ Page 0 — zero page (engine state, see table below)      │
&0100 ├─────────────────────────────────────────────────────────┤
      │ Page 1 — 6502 stack (untouched by game code)            │
&0200 ├─────────────────────────────────────────────────────────┤
      │ Page 2 — OS workspace. Only &0204/&0205 (IRQ1V) is      │
      │ poked: irq_install hooks the per-frame palette-split    │
      │ handler at &4900 (GRAPHIX). Original vector saved at    │
      │ zp_old_irq_vec_lo/hi (&64/&65) for chaining.            │
&0300 ├─────────────────────────────────────────────────────────┤
      │ CRTC / VDU shadow workspace. Loader2 line 880 pokes:    │
      │   &30A=20   &34C=&40  &34D=1   (line stride, etc.)      │
      │   &351=&58  &352=&40  &353=1                            │
      │   &355=5    &356=2                              ┐       │
      │ ...to put the BBC into split-screen MODE 5 at &5800.    │
&0400 ├─────────────────────────────────────────────────────────┤
      │ Page 4-B — OS / BASIC workspace; not used by game.       │
&0C00 ├─────────────────────────────────────────────────────────┤
      │ Page C — Loader persistence area. Score + lives are    │
      │ saved here on level transition by                       │
      │   save_score_to_loader  (CODE2 &30F8) →                 │
      │     loader_lives_save   = &0CF3                         │
      │     loader_score_save   = &0CF4 .. &0CF9   (6 digits)    │
      │     loader_hiscore_save = &0CFA .. &0CFF   (6 digits)    │
      │ ...and read back by restore_score_from_loader           │
      │ (CODE2 &3115) on the next CALL &1100.                   │
&0D00 ├─────────────────────────────────────────────────────────┤
      │ Page D-E — OS / BASIC workspace.                         │
&0E00 ├─────────────────────────────────────────────────────────┤
      │ $.CODE  — main game engine binary                        │
      │ Load &1100..&27E6 (5863 B, p.3). See "$.CODE" below.     │
&1100 │   main engine code & data (see expanded layout below)   │
&27E7 ├─────────────────────────────────────────────────────────┤
      │ $.CODE2 — sound effects, score, intro, hazards, etc.     │
&2800 │   Load &2800..&31E8 (2537 B, p.236).                     │
&31E9 ├─────────────────────────────────────────────────────────┤
      │ Reserved gap (&31E9..&32FF, ~280 B) — unused.           │
&3300 ├─────────────────────────────────────────────────────────┤
      │ $.CODE3 — inter-stage overlays (loading screen,         │
      │   stage clear, game over, GET READY!, doubled-font      │
      │   text engine, ASCII string table).                     │
      │   Load &3300..&368F (912 B, p.232).                     │
&3680 ├─────────────────────────────────────────────────────────┤
      │ $.GRAPHIX — shared sprite atlas + IRQ palette-split     │
      │   handler. Load &3680..&49FF (4992 B, p.185).           │
      │   Note: the first 16 B (&3680..&368F) overlap with the  │
      │   tail of CODE3. GRAPHIX is loaded LAST in the boot     │
      │   chain so its bytes win.                                │
&4A00 ├─────────────────────────────────────────────────────────┤
      │ $.LEVD1 — per-scenario tile catalog + player ship +     │
      │   decoration sprites (see "$.LEVD1" below). Loaded by   │
      │   Loader2 with an explicit `*L. n.LEVD1 4A00` (overrides │
      │   the catalog's claimed &6000 load address for          │
      │   scenarios 3 & 4 — see Loader2 line 1030).             │
      │   3584 B (= &E00).                                       │
&5800 ├─────────────────────────────────────────────────────────┤
      │ Screen RAM — MODE 5 framebuffer.                         │
      │   Char rows  0-19 (160 px tall): playfield                │
      │     rows  0-3:  upper tile band (mirrored)                │
      │     rows  4-15: player + enemies + hazards + starfield   │
      │     rows 16-19: lower tile band (normal)                 │
      │   Char rows 20-21: scoreboard (loaded from $.SCOREBD     │
      │     into the BOTTOM of screen RAM around &7100, then    │
      │     the IRQ split copies it down to screen rows 20-21).  │
      │   Char rows 22-31: physical screen RAM but CRTC-clipped │
      │     off-display — repurposed as storage:                │
&7100 │     $.SCOREBD lives here (640 B).                        │
&7380 │     $.LEVD2 / $.LEVD3 are layered here (3200 B / 2176 B).│
&7FFF └─────────────────────────────────────────────────────────┘
&8000 ┌─────────────────────────────────────────────────────────┐
      │ Sideways ROM / language workspace. Not written by game  │
      │ code, but `forcefield_render` (CODE &232C) *reads* from │
      │ `&80XX` (with XX = `rndval256`) and uses whatever        │
      │ sideways ROM is paged in as a free source of procedural │
      │ pixel noise.                                            │
&BFFF └─────────────────────────────────────────────────────────┘
&C000 ┌─────────────────────────────────────────────────────────┐
      │ MOS — BBC Operating System (in ROM)                      │
      │ Game references: OSRDCH (&FFE0), OSWRCH (&FFEE),         │
      │ OSWORD (&FFF1), OSBYTE (&FFF4), OSCLI (&FFF7).          │
&FFFF └─────────────────────────────────────────────────────────┘
```

## Page 0 (zero page)

Engine variables that need fast access via 2-byte zp-mode opcodes.
Names mirror `disasm/Nevryon.6502`.

| ZP | Name | Role |
|----|------|------|
| `&0D..&11` | (lfsr state) | 5-byte LFSR state for `lfsr_random` |
| `&64/&65` | `zp_old_irq_vec_lo/hi` | Saved IRQ1V (restored on chain) |
| `&70/&71` | `zp_screen_ptr_lo/hi` | Screen-write scratch ptr (advanced +320 per char row) |
| `&72` | (shutter_fade scratch) | Working hi byte of the page-walker |
| `&74` | `zp_sprite_cols_remaining` | Sprite-blitter inner-loop count |
| `&75` | `zp_sprite_height` | Sprite height in scanlines |
| `&76/&77` | `zp_dest_x_lo/hi` | Destination screen address (output of `calc_screen_addr`) |
| `&78` | `zp_sprite_end_index` | Sprite source termination index |
| `&79` | `zp_sprite_dir_flag` | 1 = forward (normal), 0 = backward (vertical mirror) |
| `&7A` | `zp_frame_progress` | "Work done this frame" counter — drives `frame_delay` |
| `&80` | `zp_scroll_col` | Per-frame map scroll column (0..&F0, wraps to &F0) |
| `&81` | `zp_player_x` | Player X char-col (2..&14) |
| `&82` | `zp_player_y` | Player Y in pixels (&98..&DC) |
| `&83` | `zp_test_x` | Scratch — current "thing being collision-tested" X |
| `&84` | `zp_test_y` | Same for Y |
| `&8A` | (fire cooldown counter) | Counts down per frame after `on_fire_pressed` |
| `&8B/&8C` | `zp_tile_lower_hi/lo` | Per-column lower-band map-tile source pointer |
| `&8D/&8E` | `zp_tile_upper_hi/lo` | Per-column upper-band map-tile source pointer |
| `&8F` | `zp_get_ready_erase` | 1 = `get_ready_overlay` should erase rather than draw |
| `&90` | `zp_print_idx` | Per-character index in `print_doubled_string` |
| `&91` | `zp_continues` | Remaining "credits" left for `game_over_or_continue` |
| `&92` | `zp_game_speed` | User speed setting (120 = slow .. 240 = fast; cheat = 252). Reset value for `zp_frame_progress` each frame. |
| `&95/&96` | `zp_string_ptr_lo/hi` | Source pointer for `print_doubled_string` |
| `&9C` | `zp_irq_enable` | 0 = IRQ palette-split active, 1 = bypass |
| `&9D` | `zp_level_num` | Current scenario number (1..8 — odd = stage 1, even = stage 2 of that pair) |

Anything not listed here is OS workspace (Loader2 pokes `&79`,
`&7E`, `&7B`, `&7C`, etc. at game start; we tolerate it and don't
disturb).

## `$.CODE` — main engine binary

Loaded at `&1100`, length 5863 B = `&16E7`, ends at `&27E6`.

| Range | Symbol | Contents |
|-------|--------|----------|
| `&1100..&116A` | `main_init` / `main_loop` / `lfsr_random` | Entry, top-of-frame loop, LFSR PRNG |
| `&116B..&116E` | `rndval256` / `rndval64` / `rndval32` / `rndval16` | Four progressively-right-shifted slices of the latest LFSR byte |
| `&116F..&1208` | `sprite_plot_default` / `sprite_plot_xy` / `sprite_plot_inner` | The sprite blitter (column-major, optional vertical-mirror). Self-modifies the `LDA &XXXX,X` operand bytes at `sprite_src_lo/hi` (`&1194`/`&1195`). |
| `&1209..&1234` | `screen_row_lo_lut` / `screen_row_hi_lut` | 22-byte LUTs for `calc_screen_addr` (MODE 5 base `&5800`, stride `&140`) |
| `&1236..&127A` | `calc_screen_addr` / `L126C` | Compute screen address from (X, Y); also the per-frame entry that bumps `zp_scroll_col` |
| `&127B..&1308` | (tile draw, unnamed) | Plots the new column on the right edge: upper tile mirrored at row 0, lower tile normal at row 16 |
| `&1309..&13BB` | `starfield_update` | Per-frame star animator (60 stars × 3-array state) |
| `&13BC..&13D0` | `frame_delay` | Frame-rate regulator (see CODE.cfg.json comment for the math) |
| `&13D1..&146B` | (per-frame, unnamed) | Reads tile IDs from `lev_map_upper/lower`, advances `zp_tile_upper/lower` pointers by `(id+1)*&80`, scrolls, dispatches frame work |
| `&146C..&1477` | (game-end shim) | Falls through to RTS once `zp_get_ready_erase >= 4` |
| `&1478..&14B4` | `draw_player` | Player ship plot + optional `draw_player_pod` + JSR `check_player_collisions` + JMP `update_bullets` |
| `&14B5..&14D7` | `draw_player_pod` | Force-pod rendering (3 frames in GRAPHIX `gfx_pod_frame*`) |
| `&14D8` | `pod_anim_frame` | Single-byte frame counter, cycled by player vertical motion |
| `&14D9..&155A` | `read_input` / `read_joystick` | Per-frame input dispatch (keyboard `KEY_*` or analog joystick) |
| `&155B..&1564` | `check_key_pressed` | OSBYTE &81 wrapper |
| `&1565..&175D` | `move_player_left` / `*_right` / `*_up` / `*_down` + collision helpers | Movement clamps + bookkeeping |
| `&17B9..&17E6` | `on_fire_pressed` | Allocate player_bullet slot, store position, play `sfx_fire` |
| `&17E7..&1846` | `update_bullets` | Per-frame: advance the 6 player-bullet slots +2 px; erase or replot; decrement fire cooldown |
| `&1847..&19F5` | `check_bullet_hits` | Test current bullet against hazards then enemies; mark hits + spawn effects |
| `&19F6..&1A54` | (collision tail) | Common hit-resolution code |
| `&1A55..&1A6F` | `hazard_x` / `hazard_y` / `hazard_state` | The 11-byte parallel state arrays for the 8 hazard slots |
| `&1A76..&1A98` | `tbl_1A76` / `tbl_1A81` / `tbl_1A8B..&1A91` / `tbl_1A92` | More hazard state (direction, prior-hit memory, slot-active markers initialised to `&FF`) |
| `&1A99..&1AEA` | (hazard helper) | Inner update used by `update_hazards` |
| `&1AEB..&1C11` | `update_hazards` | Per-frame mover for the 8 hazard slots (move ±1 X / ±4 Y, erase + replot 4×24) |
| `&1C12..&1DED` | (decor-sprite + LEVD1 logic) | Various LEVD1-accessing draw paths (CODE &1C25 / &1C36 push into the LEVD1 decoration banks — still TBD) |
| `&1DEE..&1E45` | `lose_a_life` | Play OSWRCH 7 + toggle/decrement the lives indicator |
| `&1E46` | `data_1E46` | 1-byte blink flip-flop for lives icon |
| `&1E47..&206D` | `death_anim` | 6-frame explosion at player position via `lev_explosion_ptr_lo/hi` (frames 0..3 from `lev_explosion_00..03` in LEVD1, frames 4..5 from `lev_explosion_04` / `lev_explosion_05` in LEVD2) |
| `&206E..&2080` | `tbl_206E` / `enemy_step` | Active enemy v-flip flag + step counter (parallel to `enemy_x/y/type/hp`) |
| `&2050..&209F` | `data_2050` / `data_2051` / `enemy_x` / `enemy_y` / `enemy_type` / `enemy_hp` | The 9-slot active-enemy state tables, plus the lives counter (`data_2051`) and "lives lost" counter (`data_2050`) |
| `&208A..&21EE` | `spawn_check_step` / `enemy_type_dispatch` | Per-frame: match `zp_scroll_col` against `lev_spawn_col`, install the next free enemy slot from `lev_spawn_attr` |
| `&232C..&23C4` | `forcefield_render` / `forcefield_draw_or_erase` / `forcefield_erase` | Procedural vertical strip (uses `lfsr_random` byte as the low byte of an `&80XX` source — i.e. reads sideways ROM as cheap noise) |
| `&23C5..&2553` | various L<addr> | Spawn + per-type dispatch helpers (TBD) |
| `&2554` | `fire_cooldown_reload` | Default cooldown value (= 6 from `init`) |
| `&25A0..&25AB` | `data_25A0..data_25AB` | Force-pod state group (`data_25A3` = "pod attached" flag) |
| `&2656..&268F` | `starfield_init` + helpers | One-shot at level start: walks the 60-star arrays and plants the initial pixel byte at each starting screen address |
| `&2690..&27E6` | various L<addr> | Trampolines + utility code (TBD) |

## `$.CODE2` — sound, score, intro, hazards

Loaded at `&2800`, length 2537 B, ends at `&31E8`.

Sub-blocks at a glance (full per-routine breakdown is in
`disasm/CODE2.6502` and `docs/file_layout.md`):

| Range          | Symbols                              | Contents |
|----------------|--------------------------------------|----------|
| `&2800..&284B` | `sfx_fire` / `sfx_hit_lo` / `sfx_explode` + their SOUND param blocks | Sound-effect trampolines (OSWORD &07) |
| `&284C..&28D6` | `shutter_fade`                       | Bit-shift fade for inter-stage transitions |
| `&28D7..&2972` | `force_pod_anim`                     | Force-pod chomping-ball animation (`gfx_ball_frame0..5`) |
| `&29E7..&2A1F` | `draw_score` / `draw_score_digit`    | 6-digit BCD score plot at char-col 9 |
| `&2A02..&2A07` | `score_d3` / `score_d2` / `score_d1` / `score_d0` (+2) | The 6-digit BCD score store (read by `draw_score`) |
| `&2A20..&2BA3` | `spawn_enemy_missile` / `update_enemy_missiles` / `step_enemy_missile` / `missile_player_collide` | Enemy bomb-drop pipeline (2 slots in `tbl_2B9A` etc.) |
| `&2BA4..&2CC9` | `intro_get_ready`                    | Level-start "GET READY!" 75-frame countdown |
| `&2CCA..&2E5F` | `draw_title_screen`                  | 4th Dimension logo + GPR '90 + PRESS SPACE renderer |
| `&2E5A..&2E5F` | `tbl_2E5A`                           | 6-byte BCD high-score store |
| `&2E83..&2E93` | `sfx_score_tick` + params            | Beep used during BONUS roll-up and as a hit confirmation |
| `&2E94..&2EEC` | `play_death_sequence`                | Shutter fade + explosion sound + state clear |
| `&2EED..&2EFE` | `sfx_level_start` + params           | Long high-pitched fanfare |
| `&2EFF..&2F08` | `intro_or_scoreboard`                | Dispatch: full lives → intro, else → scoreboard |
| `&2F09..&2F77` | `ship_intro_anim` + 4 frame helpers + `ship_intro_blit_setup` + `wait_one_frame` | The four-frame ship slide-in |
| `&2FF0..&3040` | `L2FF0` (TBD)                        | Probably "you-extra-ship" path |
| `&3041..&30F7` | `starfield_pos_lo` / `starfield_pos_hi` / `starfield_type` | 3 parallel 61-byte arrays — the live starfield state |
| `&30F8..&3114` | `save_score_to_loader`               | Copy score + lives to `loader_*_save` at `&0CF3+` |
| `&3115..&316F` | `restore_score_from_loader`          | Reverse — called by `main_init` |
| `&3170..&31E8` | `pause_game` / `pause_wait_unpause` / `draw_final_scoreboard` | Pause + end-of-game scoreboard |

## `$.CODE3` — overlays + text engine

Loaded at `&3300`, length 912 B, ends at `&368F` (the last 16 B
overlap the start of GRAPHIX, but GRAPHIX is loaded later).

| Range          | Symbol                       | Contents |
|----------------|------------------------------|----------|
| `&3300..&3324` | `stage_loading_screen`       | "LOADING" / "PLEASE WAIT" then `JMP &30F8` |
| `&3325..&3431` | `stage_clear_screen`         | "WOW!" / "LEVEL X COMPLETED" / "BONUS X000" with score roll-up |
| `&3432..&34EB` | `game_over_or_continue`      | Credit-countdown 10..0 / "PRESS SPACE TO / CONTINUE PLAY!" |
| `&3501..&3509` | `chardef_buf` / `chardef_r0..r6` | OSWORD &0A parameter block (1 input byte + 8 output font rows) |
| `&350A..&3512` | `osword_read_char_def`       | Trampoline to OSWORD &0A |
| `&3513..&355F` | `get_ready_overlay`          | In-game GET READY! sprite plot at col 13, row `&C0` |
| `&3560..&361C` | `print_doubled_string`       | The doubled-height font renderer (self-modifies its `LDA &XXXX,X` source operand at `print_str_src_lo/hi`) |
| `&3620..&368F` | `str_loading` / `str_please_wait` / `str_wow` / `str_level_x_completed` / `str_bonus_xnnn` / `str_extra_ship` / `str_press_space_to` / `str_continue_play` / `str_two_digits` / `str_credits_nn` | ASCII string table, CR-terminated; some bytes are written to mid-string (e.g. `&363F` for the level digit in "LEVEL X COMPLETED") |

## `$.GRAPHIX` — sprite atlas + IRQ palette-split

Loaded at `&3680`, length 4992 B, ends at `&49FF`.

Sprite atlas at `&3680..&48FF` (4736 B). Every named sprite has the
`gfx_` prefix in `disasm/GRAPHIX.cfg.json`. Notable groups:

| Range          | Group                                       |
|----------------|---------------------------------------------|
| `&3680..&36FF` | `gfx_muzzle_flash_frame0/1`                 |
| `&3700..&37FF` | `gfx_enemy_slot15/16` — shared enemies      |
| `&3860..&38EF` | `gfx_ball_frame0..5` (force-pod ball-chomp) |
| `&3900..&3A1F` | `gfx_pod_frame0..2` (player force-pod)      |
| `&3A20..&3AAF` | `gfx_icon_00..09`, `gfx_digit_0..9`         |
| `&3B00..&3BBF` | `gfx_flame_frame0..2`                       |
| `&3BC0..&3CFF` | `gfx_text_press_space`                      |
| `&3D00..&3DDF` | `gfx_logo_4thdim`                           |
| `&3DE0..&3FFF` | `gfx_text_score / _last / _high / _gpr90` etc. |
| `&4060..&4090..` | `gfx_pickup_red / _yellow / _checker / _white` |
| `&4100..&4360..` | `gfx_text_get_ready / _game / _over / _on` + `gfx_enemy_slot19` |
| `&4410..&44D7` | `gfx_missile_0..4`                          |
| `&4500..&474F` | `gfx_orphan_4500` (592 B — dead data, no references) |
| `&4750..&47FD` | `gfx_pickup_white / _pause`                 |
| `&4800..&484F` | `gfx_icon_10..17` + `gfx_bomb`              |
| `&4858..&48E7` | `gfx_enemy_small_frame0/1`                  |

Beyond the atlas (`&4900..&49FF`):

| Range          | Symbol                       | Contents |
|----------------|------------------------------|----------|
| `&4900..&493E` | `irq_palette_split`          | The per-frame IRQ that drives the split palette |
| `&493F..&494E` | `palette_top`                | First 12 bytes pushed to `&FE21` at vsync (the playfield) |
| `&494F..&495E` | `palette_bottom`             | First 12 bytes pushed mid-frame (the scoreboard) |
| `&495F..&497D` | `irq_palette_split_b`        | The mid-frame branch |
| `&497E..&49A4` | `irq_install`                | Called by Loader2 `CALL &497E` to hook the IRQ |
| `&49A5..&49FF` | (undecoded, 91 B)            | Trailing data, purpose TBD |

## `$.LEVD1` — per-scenario tile catalog + sprites

Loaded at `&4A00`, length 3584 B = `&E00`, ends at `&5800`. Same
internal layout for all four scenarios:

| Range           | Symbol                     | Contents |
|-----------------|----------------------------|----------|
| `&4A00..&4BFF`  | `lev_explosion_00..03`     | First 4 frames of the 6-frame player-death explosion (4×32 = 128 B each). Same bytes also accessible via `lev_enemy_ptr_*[21..24]`. |
| `&4C00..&4C1F`  | (zero pad)                 | 32 B of zeros separating explosion frames from the enemy-animation strip. |
| `&4C20..&4CFF`  | `lev_enemy_hit_1..3`       | 3 frames of the per-scenario small-enemy *hit/destruction* cycle (4×24 = 96 B each, with column sharing). Read by the `L1BE3` state machine in CODE at hazard_state values `&0A..&0C`. (Numbered 1..3 to track the state-machine index — state `&0A` reuses the same animation timeline as state 1's, so the level designer never made a frame 0.) |
| `&4D00..&4DA7`  | `lev_enemy_0..1`           | First 2 frames of the small-enemy *normal* cycle. Same 4×24 shape, continuing the shared-column strip. |
| `&4DA8..&4DAF`  | (zero pad)                 | 8 B of zeros inside the strip. |
| `&4DB0..&4E6F`  | `lev_enemy_2..3`           | Last 2 frames of the small-enemy normal cycle. |
| `&4E70..&4E7F`  | (zero pad)                 | 16 B before the player ship. |
| `&4E80..&4F03`  | `lev_player_sprite`        | 132 B = 6 byte-cols × 22 lines (24 px × 22 px) — the player ship. |
| `&4F00..&57FF`  | `lev_tile_catalog`         | 18 tile slots × 128 B = 4 cols × 32 lines (16 px × 32 px). Tile id N at `lev_tile_catalog + N*&80`. The player ship overlaps tile 0's first 4 bytes; those bytes are zero in tile 0 (its top is empty), so the overlap is harmless. Not every slot is populated — typically 12-17 tiles per scenario, the rest are zero-filled. Tile slots `4` and `5` (= `&5100` / `&5180`) double as enemy sprites — `lev_enemy_ptr_*` slots `18` and `17` point at them. |

## `$.LEVD2` / `$.LEVD3` — per-stage data

Loaded at `&7380` over the off-display tail of MODE 5 screen RAM
(char rows 22-31, which CRTC trims off the visible area).

LEVD2 is always 3200 B; LEVD3 is 2176 B for scenarios 1-3 (overlays
only the lower half — sprites + spawns + hazards — and the map
tile-id streams inherit from LEVD2) or 3200 B for scenario 4 (full
overlay; its tile streams happen to be byte-identical to LEVD2 so the
geometry is unchanged).

| Range           | Symbol                     | Contents |
|-----------------|----------------------------|----------|
| `&7380..&7A7F`  | `lev_hazard_00..13`        | 14 × 4×32 (128 B each) hazard sprites — the per-stage large stationary threats (gun-towers, tanks, structures). Accessible via `lev_enemy_ptr_*[1..14]`. |
| `&7A80..&7ABF`  | `lev_enemy_ptr_lo` (32)    | Sprite pointer LO byte per enemy type (0..31). Bits 0..4 of the spawn attribute byte index this table. |
| `&7AC0..&7AFF`  | `lev_enemy_ptr_hi` (32)    | Paired HI bytes. |
| `&7A95..&7A9A`  | `lev_explosion_ptr_lo` (6) | **Same physical bytes** as `lev_enemy_ptr_lo + &15..+&1A` (slots 21..26 of the enemy pointer table). `death_anim` (CODE `&1E47`) walks these six byte-pairs as the source pointers for the 6-frame player explosion. There is no separate explosion-frame pointer table — `lev_explosion_ptr_*` is just an alias for the tail of `lev_enemy_ptr_*`. |
| `&7AD5..&7ADA`  | `lev_explosion_ptr_hi` (6) | Paired HI bytes (slots 21..26 of `lev_enemy_ptr_hi`). |
| `&7B00..&7B7F`  | `lev_spawn_col` (128)      | Spawn-column schedule. Sorted ascending; `&FF` terminates. Walked every frame by `spawn_check_step`. |
| `&7B80..&7BFF`  | `lev_spawn_attr` (128)     | Parallel attribute table. Bits 0..4 = enemy type, bits 5..6 = Y-row, bit 7 = vertical-mirror. |
| `&7C00..&7C7F`  | `lev_explosion_04` (128)   | 4×32 frame 4 of the 6-frame explosion. Same bytes accessible as `lev_enemy_ptr_*[25]`. |
| `&7C80..&7CFF`  | `lev_explosion_05` (128)   | 4×32 frame 5 of the 6-frame explosion. Same bytes accessible as `lev_enemy_ptr_*[26]`. |
| `&7D00..&7E0F`  | `lev_erase_brush` (272)    | All zeroes. `sprite_plot` from any offset here paints a transparent rectangle. The engine touches it at +&80 (4×24 erase), +&B0, +&100 (2×8 bullet erase), +&102 (3×2 bullet erase). |
| `&7E10..&7EFF`  | `lev_map_upper` (240)      | Upper tile-id stream. One byte per scroll column; resolved against `lev_tile_catalog`. Drives `zp_tile_upper`; drawn at row 0 with `dir_flag = 0` (vertically mirrored, so a floor-shaped tile appears as a ceiling). |
| `&7F00..&7F0F`  | (pad 16 B)                 | Gap between the two tile streams. Same-value-ish per scenario — possibly a wrap-around safety strip. |
| `&7F10..&7FFF`  | `lev_map_lower` (240)      | Lower tile-id stream. Drives `zp_tile_lower`; drawn at row 16 with `dir_flag = 1` (normal). |

### Enemy-pointer slot allocation

The 32 slots of `lev_enemy_ptr_*` follow a fixed-per-scenario
convention — every scenario points the *same* slot at the *same*
region; only the bytes at the resolved addresses differ. There's
also a fair amount of pointer reuse, which can be confusing when
inspecting individual sprites:

| Slot(s) | Resolves into                    | Role                                                       |
|---------|----------------------------------|------------------------------------------------------------|
| `0`     | `lev_erase_brush` (`&7D80`)      | All-zero "no enemy" placeholder. Plotting one renders blank. |
| `1..14` | `lev_hazard_00..13` (LEVD2)      | Per-stage hazard sprites at `&7380..&7A00` (gun-towers, tanks, structures). |
| `15`    | `gfx_enemy_slot15` (GRAPHIX `&3700`) | Shared across all 4 scenarios (the renderer applies the per-level palette so it still looks different per scenario). |
| `16`    | `gfx_enemy_slot16` (GRAPHIX `&3780`) | Shared cross-scenario.                                  |
| `17`    | LEVD1 `&5180`                    | Tile id 5 from `lev_tile_catalog` reused as an enemy sprite (4×32 same shape). |
| `18`    | LEVD1 `&5100`                    | Tile id 4 reused as an enemy sprite.                         |
| `19`    | `gfx_enemy_slot19` (GRAPHIX `&4360`) | Shared cross-scenario.                                  |
| `20`    | `&0000`                          | Unused (pointer pair is `00 00`).                            |
| `21..24`| `lev_explosion_00..03` (LEVD1 `&4A00..&4B80`) | Player-death explosion frames 0..3. The same enemy slots can in principle be spawned via `lev_spawn_attr` (with `type = 21..24`); in practice the explosion role is the dominant use. |
| `25`    | `lev_explosion_04` (`&7C00`)     | Explosion frame 4. |
| `26`    | `lev_explosion_05` (`&7C80`)     | Explosion frame 5. |
| `27`    | `lev_erase_brush` (`&7D80`)      | Same all-zero placeholder as slot 0. Unused.               |
| `28..31`| `&0000`                          | Unused.                                                     |

`tools/render_level.py` writes one PNG per *unique underlying memory
range* in the LEVD files (skipping any slot that resolves into
GRAPHIX, since those bytes live elsewhere). Filenames are semantic —
`explosion_NN`, `enemy_NN`, `enemy_hit_NN`, `tile_NN`, `hazard_NN`,
`player_sprite` — and the per-level `README.md` maps every table
index back to a filename. So when the same memory plays two roles
(e.g. `lev_enemy_ptr_*[25]` = `lev_explosion_04`), only one PNG
exists; the README spells out the aliasing.

### Spawn attribute encoding (recap)

The byte at `lev_spawn_attr[i]` is a packed record:

```
  bit 7      bits 5-6      bits 0-4
┌──────┐  ┌────────────┐  ┌──────────────┐
│v-flip│  │   Y-row    │  │ type (0..31) │
└──────┘  └────────────┘  └──────────────┘
   │            │                │
   │            │                └─→ index into lev_enemy_ptr_*
   │            │                    AND dispatch via enemy_type_dispatch:
   │            │                       4 / &13 = multi-shot
   │            │                       6       = enemy missile (CODE2)
   │            │                       7       = force-field
   │            │                       8       = high-HP variant
   │            │                       &10     = boss
   │            │
   │            └──→ 0 = &DF, 1 = &BF, 2 = &9F, 3 = &7F (pixel Y)
   │
   └──→ 0 = upright, 1 = vertical mirror (paired with non-flipped
        spawn at the same col for symmetric decoration)
```

Worked example: `lev1.LEVD2 col &0B` has two spawns — `attr = &8D`
(type 13, Y-row 0, v-flip 1) at the ceiling and `attr = &4D` (type
13, Y-row 2, v-flip 0) at the floor. The engine plots the same
sprite at top and bottom of the playfield gap, the top one mirrored
so the silhouettes meet in the middle.

## `$.SCOREBD` — pre-rendered scoreboard bitmap

Loaded at `&7100`, 640 B (= 20 char-cells × 2 rows × 16 B). Sits
below the LEVD2 / LEVD3 region in the off-display tail. The
`irq_palette_split` IRQ swaps in `palette_bottom` mid-frame so the
scoreboard renders with the always-blue/cyan/white palette
regardless of which scenario is active.

## Per-binary on-disk → CPU summary

| File                | CPU load | Length (dec / hex) | Catalog page |
|---------------------|----------|--------------------|--------------|
| `$.CODE`            | `&1100`  | 5863 / `&16E7`     | p.3          |
| `$.CODE2`           | `&2800`  | 2537 / `&09E9`     | p.236        |
| `$.CODE3`           | `&3300`  |  912 / `&0390`     | p.232        |
| `$.GRAPHIX`         | `&3680`  | 4992 / `&1380`     | p.185        |
| `N.LEVD1`           | `&4A00`* | 3584 / `&0E00`     | p.366/380/308/272 |
| `$.SCOREBD`         | `&7100`  |  640 / `&0280`     | p.26         |
| `N.LEVD2`           | `&7380`  | 3200 / `&0C80`     | p.353/331/295/259 |
| `N.LEVD3` (lev 1-3) | `&7380`  | 2176 / `&0880`     | p.344/322/286 |
| `N.LEVD3` (lev 4)   | `&7380`  | 3200 / `&0C80`     | p.246        |

*Loader2 line 1030 explicitly forces all LEVD1s to load at `&4A00`,
even for scenarios 3/4 whose catalog claims `&6000`.

## Active-object pools

The engine carries fixed-size slot pools for every kind of moving
object on screen. The caps are deliberate — Nevryon never allocates
at runtime; instead each routine scans a hard-coded slot range with
an `LDX #N / DEX / BNE` (or `INX / CPX #N / BNE`) loop. Magic
numbers for these caps are surfaced as named EQUs in
`disasm/Nevryon.6502` and wired up via `immediate_overrides` in the
per-binary cfgs, so the disassembly reads e.g. `LDX #n_enemies`
instead of `LDX #&08`.

| Pool                | Cap | Storage range                           | Iterator pattern               | Notes |
|---------------------|----:|-----------------------------------------|--------------------------------|-------|
| Player ship         |   1 | `zp_player_x`/`_y` (&81/&82) + `lives_left` (&2051)                                 | singleton                      | Per-life HP at `player_hp` (&2050), default 6 from `?&9A`. |
| Player explosion    |   1 | none — 6-frame anim plays inline in `death_anim`                                    | singleton                      | Frames sourced from `lev_explosion_0..5` (LEVD1/LEVD2). |
| Player bullets      |   6 | `player_bullet_x[6]` (&16E6), `player_bullet_y[6]` (&16ED)                          | `LDX #n_player_bullets / DEX BNE`  in `update_bullets` | Keyboard fire only scans slots 1..`n_player_fire_slots` (=4); slots 5..6 are reserved for the force-pod's twin shot (CODE2 `pod_fire` scans slots `n_player_bullets..n_player_bullets-n_player_fire_slots+1`). |
| Enemies             |   8 | `enemy_x`/`_y`/`_type`/`_hp`/`_step`/`enemy_flip` at &2052..&207F (parallel 9-wide arrays — see `n_state_slots`) | `INX / CPX #n_enemies / BNE` (slots 0..7); spawn round-robins `zp_7C` mod `n_enemies` | Per-type behaviour dispatched by `enemy_type_dispatch`; slot 8 of each array is unused (see below). |
| Hazards             |   8 | `hazard_x`/`_y`/`hazard_state` at &1A55/&1A60/&1A6B (8-wide each) PLUS `hazard_state` overlay at &206E..&2076 (the parallel-with-enemies array) | `LDX #n_hazards / DEX BNE` (slots 1..8 — slot 0 unused) | Hazards share a back-store with enemies via the parallel `hazard_state` array; the cap of 8 active hazards is independent of the 8 enemies, but the predec loop pattern means index 0 is always empty. The `LDX #n_hazards + 1` in `check_player_collisions` is the same loop body with a DEX-first prelude. |
| Combined slot width |   9 | union of enemy[0..7] and hazard[1..8]                                                | `init` clear loop: `CPX #n_state_slots`                              | `n_state_slots = 9` is the array width chosen so a single `INX/CPX/BNE` sweep zeroes both pools' active ranges. |
| Enemy bullets       |   6 | `enemy_bullet_x[7]` (&1A8B), `enemy_bullet_y[7]` (&1A92)                            | `LDX #n_enemy_bullets / DEX BNE` (slots 1..6) | Backing arrays are 7-wide; slot 0 is initialised to &FF by `init` but no routine ever touches it (predec loop falls off at X=0 before processing). |
| Enemy bullets (hz)  |   4 | (shares the pool above)                                                              | `LDX #n_hazard_bullets / DEX BNE` (slots 1..4)              | Hazards fire (`hazard_try_fire_bullet`) only into the first 4 slots of the shared pool, leaving slots 5..6 for enemy-type-&04/&13 fires (`enqueue_enemy_bullet`). Plus a global 8-frame cooldown at `zp_7E`. |
| Enemy missiles      |   2 | `enemy_missile_x[2]`/`_y[2]`/`_flip[2]`/`_homing_dir[2]` at &2B9A..&2BA3 (CODE2)    | hard-coded `LDX #&00` / `LDX #&01` — no loop | Spawned by enemy type &06 (`spawn_enemy_missile`); homes on the player by toggling sign each tick. |
| Force-field         |   1 | `forcefield_x`/`_y`/`_active` at &23C5..&23C7                                       | singleton                      | Enemy-type &07 is a force-field slot; `forcefield_render` re-noises the strip every frame. |
| Force pod           |   1 | `force_pod_x`/`_y`/`_frame` at &2972..&2974 (CODE2) + `force_pod_state` at &25A5 (CODE) | singleton                      | Orbits the player when state=1; can fire one bullet via `L2975` into player_bullet slots 5..6. |
| Flame               |   1 | `flame_x`/`_y`/`flame_state` at &249A..&249C                                        | singleton                      | Spawned by enemy type &08; one-shot 6-frame 32×8 sprite — `spawn_flame` refuses while `flame_state != 0`. |
| Power-up pickup     |   1 | `pickup_x`/`_y`/`pickup_state` at &2690..&2692                                      | singleton                      | Triggered every 10 hazard hits (`data_25A0 >= 10`); only one in flight at a time. |

### Why hazards and enemies share storage

The hazard arrays at &1A55..&1A72 are the *primary* per-frame state
(per-slot position, direction, animation tick). The
`hazard_state` byte at &206E..&2076 lives in the same parallel-with-
enemies block specifically so that `init`'s clear loop
(`STA hazard_state,X` interleaved with the enemy clears) can wipe
both pools in one pass. The disjoint index conventions —
enemies at [0..7], hazards at [1..8] — keep the two from clashing
even though their parallel arrays overlap at indices 1..7.

### Total moving objects on screen

Cap (excluding scenery / starfield / scoreboard):

  1 player + 6 player bullets + 8 enemies + 8 hazards + 6 enemy
  bullets + 2 enemy missiles + 1 force-field + 1 force-pod + 1
  flame + 1 pickup = **35 simultaneous game objects**.

In practice the spawn schedule rarely fills more than ~12 slots at
once.

## See also

- `docs/file_layout.md` — per-file disk byte-map + named routine list
- `levels/<n>/README.md` — per-level visualisation + spawn schedule
- `disasm/Nevryon.6502` — all the equates surfaced here as named labels
- `JOURNAL.md` — chronological dig for each region
