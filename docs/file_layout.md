# Nevryon disk file reference

What each file on the disk image contains, where it loads, and what's
inside. Source: `extracted/_manifest.tsv` plus reverse-engineering
notes from `disasm/CODE.cfg.json`, `disasm/GRAPHIX.cfg.json`, and the
BASIC loader chain.

Working disk image: `4thDimension/Nevryon.ssd` — the stairwaytohell.com
40-track image (101632 bytes, md5 `fbd3ddef3dff2f74190531d73ae63fea`).
This is the original, unmodified release. (An 80-track version from
bbcmicro.co.uk also exists but has had the original boot chain stripped
out — it rolls `$.LOADER3` + `$.Runner` + `$.Loader4` into a single
beefed-up `$.Loader3` and bulks out `$.NEVRYON` with extra intro
content. The core game files — `$.CODE`, `$.CODE2`, `$.CODE3`,
`$.GRAPHIX`, all twelve `N.LEVD*` — are byte-identical between the
two images, so any disassembly / level-data work done against the
bbcmicro one is still valid.)

Addresses use the BBC `&hex` convention. File offsets use `0x`.

The four runtime binaries (`CODE`, `CODE2`, `CODE3`, `GRAPHIX`) are
reproduced byte-for-byte from `disasm/*.6502` via BeebAsm. Run
`./build.sh` (or `build.bat` on Windows) from the repo root — it
assembles `disasm/Nevryon.6502` (which `INCLUDE`s the four per-binary
sources in the right order) and writes outputs to `build/`,
verifying each against `extracted/`.

---

## At a glance

```
$.!BOOT       → $.!LOAD            (boot stub)
              → $.LOAD             (publisher loader)
              → $.4THDIM           ("THE 4TH DIMENSION" logo screen)
              → $.options          (option screen)
              → $.Loader2          (title + scenario menu + palette setup)
              → $.LOADER3          (loads CODE/CODE2/CODE3, chains to RUNNER)
              → $.Runner           (stage-cycle driver: runs game, loads LEVD3, runs again)
              → $.Loader4          (on stage end: next scenario or game over)
                  ↳ $.Loader2      (next scenario)
                  ↳ $.GmOv         (game over)
              → $.WELLDON          (victory)
```

| File              | Load   | Size   | Kind                | Purpose                                          |
|-------------------|--------|--------|---------------------|---------------------------------------------------|
| `$.!BOOT`         | &0000  |    14  | BASIC               | Boot stub                                         |
| `$.!LOAD`         | &0000  |    87  | machine code        | Publisher boot loader (loads `$.LOAD`)            |
| `$.LOAD`          | &1900  |   272  | machine code        | Stage-2 loader (loads `$.4THDIM` + chains)        |
| `$.4THDIM`        | &7E00  |   320  | MODE 1 graphic data | "THE 4TH DIMENSION" publisher logo bitmap pieces  |
| `$.NEVRYON`       | &1900  |   164  | BASIC               | Tiny intro stub (extracted-version-dependent)     |
| `$.options`       | &0E00  |  3588  | BASIC               | Option screen (skill, speed, start level…)        |
| `$.Loader2`       | &1100  |  5370  | BASIC               | Title, scenario menu, palette setup (PROCL34/L56/L78), installs palette IRQ via `CALL &497E` |
| `$.LOADER3`       | &0E00  |    97  | BASIC               | Loads CODE/CODE2/CODE3, then `CHAIN "RUNNER"`     |
| `$.Runner`        | &3200  |   159  | BASIC               | Stage cycle: `CALL &1100`, increment level, load `N.LEVD3` if needed, run again, then `CHAIN "LOADER4"` |
| `$.Loader4`       | &0E00  |    55  | BASIC               | On end-of-scenario: `CHAIN "GmOv"` if game over, else `CHAIN "LOADER2"` for next scenario |
| `$.GmOv`          | &0E00  |   714  | BASIC               | Game-over screen                                  |
| `$.WELLDON`       | &3000  | 10240  | MODE 1 bitmap       | Victory screen — "VICTORY"               |
| `$.SCR`           | &2E00  |  8192  | MODE 1 bitmap       | Title-screen "NEVRYON" logo image        |
| `$.OPSC`          | &3000  | 17408  | MODE 2 bitmap       | Option screen background                 |
| `$.SCOREBD`       | &7100  |   640  | MODE 5 bitmap       | Scoreboard band (char rows 20-21)        |
| `$.GRAPHIX`       | &3680  |  4992  | sprite atlas + code | Shared sprites + palette IRQ handler     |
| `$.CODE`          | &1100  |  5863  | 6502                | Main game logic                          |
| `$.CODE2`         | &2800  |  2537  | 6502                | SFX queue + extras                       |
| `$.CODE3`         | &3300  |   912  | 6502                | Inter-stage transitions / messages       |
| `N.LEVD1`         | &4A00  |  3584  | sprite atlas + tiles | Per-scenario tile catalog + decorations |
| `N.LEVD2`         | &7380  |  3200  | level data          | Stage-1 enemies + spawn + map tables     |
| `N.LEVD3`         | &7380  |  2176/3200 | level data       | Stage-2 enemy overlay (and map for lev4) |

Notes:

- **The catalog load addresses for `3.LEVD1` and `4.LEVD1` are `&6000`,
  but Loader2 line 1030 explicitly overrides them with
  `LOAD N.LEVD1 4A00`** — so in practice all four `LEVD1` files load
  at `&4A00`. Same story for `LEVD2` and `WELLDON` (forced &7380 and
  &3000 respectively).
- `$.GmOv` and `$.Options` both list exec address `&802B`, which is
  the BBC BASIC `*RUN` entry — they're chained as BASIC programs, not
  raw machine code.

---

## Boot / loader chain

### `$.!BOOT`
One-liner BASIC: `*BASIC` then `PAGE=&1900 / CHAIN "NEVRYON"`.

### `$.NEVRYON`
The story-text intro screen. Line 70 chains to `Options`.

### `$.Options`
The option screen — joystick/keys, sound on/off, start level (1-8),
colour/mono, fast/slow, etc. Writes the user's selections into zero
page (`?&9D`=level, `?&9E`=speed, `?&9F`=control). Chains to
`LOADER2`.

### `$.Loader2`
The big one. It:

1. Draws the title screen and the options-preview screen (the one
   showing four labelled level icons with a marker bar).
2. Loads `OPSC`, `ScoreBd` and `GRAPHIX` into their respective
   addresses.
3. Loads the current scenario's `LEVD1` (forced to `&4A00`) and
   `LEVD2` (forced to `&7380`).
4. Patches the per-scenario palette into `&493F` using one of four
   PROCs (`PROCLV12` / `PROCL34` / `PROCL56` / `PROCL78`, chosen by
   `IF L%=… PROC…` on lines 940-970). See **Palette mechanism**
   below.
5. Installs the split-screen palette IRQ handler with `CALL &497E`
   (the install routine inside `GRAPHIX`).
6. Pokes a tiny 8-byte pattern into the LEVD2 `&7E00-&7E07` erase
   region (`119 119 - - - - 112 112`).
7. Chains to `LOADER3`.

### `$.LOADER3`
97 bytes. Loads `CODE`, `CODE2`, patches `?&283D` with `256-V%` (sound
volume), then loads `CODE3` and chains to `RUNNER`.

```basic
10 HIMEM=&3300
20 *FX200,3
30 *L.CODE 1100
40 *LO.CODE2
50 ?&283D=256-V%
60 *L. CODE3
70 CHAIN"RUNNER"
```

### `$.Runner`
The stage-cycle driver. Calls the game (`CALL &1100`), and on return
either fires the second half of the scenario (loading `N.LEVD3` and
calling the game again) or chains to `LOADER4`.

```basic
10 CALL&1100:?&9D=?&9D+1:IF?&9D<2 THEN PAGE=&1100:CHAIN"LOADER4"
20 A%=?&9D+1:A%=A%/2:$&7B00="L."+STR$(A%)+".LEVD3":X%=0:Y%=&7B:CALL&FFF7:
    CALL&1100:?&9D=?&9D+1:PAGE=&1100:CHAIN"LOADER4"
```

`?&9D` is the per-stage counter — incremented after each `CALL &1100`.
On the first call (`?&9D == 0`) it falls through to line 20, which
constructs `"L." + STR$(scenario) + ".LEVD3"`, OSCLI-loads it (which
overlays the LEVD2 enemy region at `&7380`), and re-enters the game.
After that re-entry, increments `?&9D` again and chains to LOADER4.

### `$.Loader4`
End-of-scenario dispatch. If `?&9D < 2` chain to `GmOv` (game over),
otherwise chain to `LOADER2` for the next scenario menu.

```basic
10 *FX200,3
20 ?&9C=1:IF ?&9D<2 CHAIN"GmOv"
30 CHAIN"LOADER2"
```

### `$.GmOv` / `$.WELLDON`
End-screen overlays. `GmOv` is a BASIC program loaded over `CODE`;
`WELLDON` is a pre-rendered MODE 1 bitmap.

### `$.!LOAD` / `$.LOAD` / `$.4THDIM`
The publisher boot chain. `!BOOT` `*RUN`s `!LOAD`, which loads `LOAD`,
which displays the "THE 4TH DIMENSION" logo (from the `4THDIM`
graphic-data file) before chaining into `options`. We haven't yet
disassembled these — they're not in the gameplay path.

---

## Static screen bitmaps

### `$.SCR` (8192 bytes at `&2E00`, MODE 1)
The "NEVRYON" logo strip used on the title screen, plus credits text:
"NEVRYON / BY GRAEME RICHARDSON 1990 / (C) 1990 THE 4TH DIMENSION".

### `$.OPSC` (17408 bytes at `&3000`, MODE 2)
The option screen — 16-colour image with the yellow Nevryon ship,
red/blue alien previews, planet/galaxy art and the icon bar. Use
`NEVRYON_LOADER_PALETTE` to render (since the loader sets cyan for
logical 2 before this is shown).

### `$.SCOREBD` (640 bytes at `&7100`, MODE 5)
The scoreboard graphic. It lives at `&7100` in RAM but the engine
copies it into the MODE 5 screen's char rows 20-21 (the bottom 16
pixel rows). The split-screen palette IRQ ensures the scoreboard is
always rendered in `palette_bottom` (black / blue / cyan / white)
regardless of which scenario palette is active for the playfield.

### `$.WELLDON` (10240 bytes at `&3000`, MODE 1)
The victory bitmap. Drawn after completing scenario 4.

---

## `$.GRAPHIX` (4992 bytes at `&3680`)

The file is in two halves: a shared sprite atlas at `&3680-&48FF`
(4736 B, file offset `0x0000-0x127F`) followed by the palette /
split-screen IRQ handler at `&4900-&49FF` (256 B, file offset
`0x1280-0x137F`).

### Sprite atlas — `&3680-&48FF`

All sprites are **column-major** at 2 bpp (1 byte = 4 pixels wide).
Dimensions below are in pixels (W × H), with the on-disk byte size
in parentheses. Renders of every sprite are in `graphix/`.

| CPU addr | Size px (B)    | Name / description                                                  |
|----------|----------------|---------------------------------------------------------------------|
| `&3680`  | 16×16 (64)     | `gfx_muzzle_flash_frame0` — player gun flash, frame 0                   |
| `&36C0`  | 16×16 (64)     | `gfx_muzzle_flash_frame1` — player gun flash, frame 1                   |
| `&3700`  | 16×32 (128)    | `gfx_enemy_slot15` — LEVD2/3 ptr-table slot 15 (shared cross-scenario)  |
| `&3780`  | 16×32 (128)    | `gfx_enemy_slot16` — LEVD2/3 ptr-table slot 16                          |
| `&3800`  | 24×16 (96)     | `gfx_text_wow` — "WOW!" inter-stage banner                              |
| `&3860`  |  8×12 (24)     | `gfx_ball_frame0` — chomping-orb animation, frame 0                     |
| `&3878`  |  8×12 (24)     | `gfx_ball_frame1`                                                       |
| `&3890`  |  8×12 (24)     | `gfx_ball_frame2`                                                       |
| `&38A8`  |  8×12 (24)     | `gfx_ball_frame3`                                                       |
| `&38C0`  |  8×12 (24)     | `gfx_ball_frame4`                                                       |
| `&38D8`  |  8×12 (24)     | `gfx_ball_frame5`                                                       |
| `&38F0`  | — (16)         | Alignment pad — pushes the next sprite onto a page boundary         |
| `&3900`  | 12×24 (72)     | `gfx_pod_frame0` — player force-pod (rotating saucer) frame 0. Plotted as 4×24 by `draw_player_pod`; the 4th byte-col is the blank pad below. (Originally mis-labelled `gfx_enemy_saucer_*` — no enemy ptr-table slot references these, only `draw_player_pod` does.) |
| `&3948`  | — (24)         | Blank separator column (1×24), absorbed into the 4-col pod blit     |
| `&3960`  | 12×24 (72)     | `gfx_pod_frame1`                                                    |
| `&39A8`  | — (24)         | Blank separator                                                     |
| `&39C0`  | 12×24 (72)     | `gfx_pod_frame2`                                                    |
| `&3A08`  | — (24)         | Trailing blank                                                      |
| `&3A20`  |  4×8 (8) ×8    | `icon_00..icon_07` — 8 small 4×8 glyphs (small-char bank, first 8)  |
| `&3A60`  |  4×8 (8) ×10   | `digit_0..digit_9` — 10 small 4×8 digits                            |
| `&3AB0`  |  4×8 (8) ×2    | `gfx_icon_missile_rocket`, `gfx_icon_lives` — two more small 4×8 glyphs (the second is the in-game lives icon; pairs with `gfx_icon_lives_blink` at &4838 for the blink-state-1 flash) |
| `&3AC0`  | — (64)         | Blank pad — unused tail of the 28-slot small-char bank              |
| `&3B00`  | 32×8 (64)      | `gfx_flame_frame0` — engine flame, frame 0                              |
| `&3B40`  | 32×8 (64)      | `gfx_flame_frame1`                                                      |
| `&3B80`  | 32×8 (64)      | `gfx_flame_frame2`                                                      |
| `&3BC0`  | 80×16 (320)    | `gfx_text_press_space` — "PRESS SPACE!"                                 |
| `&3D00`  | 28×32 (224)    | `gfx_logo_4thdim` — small "4TH DIM" logo block                          |
| `&3DE0`  | 36×16 (144)    | `gfx_text_score` — "SCORE"                                              |
| `&3E70`  |  4×16 (16)     | `gfx_punct_colon` — ":"                                                 |
| `&3E80`  | 28×16 (112)    | `gfx_text_last` — "LAST"                                                |
| `&3EF0`  | 28×16 (112)    | `gfx_text_high` — "HIGH"                                                |
| `&3F60`  |  8×16 (32)     | `gfx_punct_ampersand` — "&"                                             |
| `&3F80`  | 56×16 (224)    | `gfx_text_gpr90` — "GPR'90!"                                            |
| `&4060`  |  8×16 (32)     | `gfx_pickup_red` — red pickup                                           |
| `&4090`  |  8×16 (32)     | `gfx_pickup_yellow` — yellow pickup                                     |
| `&40C0`  |  8×16 (32)     | `gfx_pickup_checker` — checker pickup                                   |
| `&40E0`  | — (32)         | Pre-text pad                                                        |
| `&4100`  | 64×16 (256)    | `gfx_text_get_ready` — "GET READY!"                                     |
| `&4200`  | 32×16 (128)    | `gfx_text_game` — "GAME"                                                |
| `&4280`  | 32×16 (128)    | `gfx_text_over` — "OVER"                                                |
| `&4300`  | 24×16 (96)     | `gfx_text_on` — "ON!"                                                   |
| `&4360`  | 16×32 (128)    | `gfx_enemy_slot19` — LEVD2/3 ptr-table slot 19                          |
| `&43E0`  | — (48)         | Pre-missile pad                                                     |
| `&4410`  | 20×8 (40)      | `gfx_missile_0` — projectile sprite, frame 0                            |
| `&4438`  | 20×8 (40)      | `gfx_missile_1`                                                         |
| `&4460`  | 20×8 (40)      | `gfx_missile_2`                                                         |
| `&4488`  | 20×8 (40)      | `gfx_missile_3`                                                         |
| `&44B0`  | 20×8 (40)      | `gfx_missile_4`                                                         |
| `&44D8`  | — (40)         | Post-missile pad                                                    |
| `&4500`  | — (592)        | `enemy_pattern_1..4` — four NPC motion-script tables: `&4500` (len &78), `&4574` (&9C), `&4614` (&60), `&4680` (&D6). Each is a sequence of `(dy_dir, dx_dir)` byte pairs walked per-enemy-per-frame by `enemy_select_motion` (CODE &1B87). Indexed via `enemy_pattern_ptr_lo / _hi / _len_lut` LUTs at CODE &16FB+. (Was originally mis-labelled `gfx_orphan_4500` and assumed dead; corrected in Session 27.) |
| `&4750`  |  8×16 (32)     | `gfx_pickup_white` — 4th pickup variant                                 |
| `&4770`  | — (16)         | Pad                                                                 |
| `&4780`  | 36×14 (126)    | `gfx_text_pause` — "PAUSE"                                              |
| `&47FE`  | — (2)          | Pad                                                                 |
| `&4800`  |  4×8 (8) ×8    | `icon_10..icon_17` — 8 more small 4×8 glyphs                        |
| `&4840`  | — (8)          | Pad                                                                 |
| `&4848`  |  4×8 (8)       | `gfx_bomb` — small bomb/ball sprite                                     |
| `&4850`  | — (8)          | Pad                                                                 |
| `&4858`  | 12×24 (72)     | `gfx_enemy_small_frame0` — small enemy animation, frame 0               |
| `&48A0`  | 12×24 (72)     | `gfx_enemy_small_frame1` — frame 1                                      |
| `&48E8`  | — (24)         | Trailing blank                                                      |

The sprite-engine entry point (`sprite_plot_xy` at `&1173` in CODE)
takes width-in-byte-cols in X and height-in-scanlines in Y, with the
source pointer self-modified into `&1194`/`&1195`. Callers in
CODE/CODE2/CODE3 are how each sprite address above was identified —
either via `LDA #lo;STA &1194; LDA #hi;STA &1195` immediate pairs,
or via the enemy-pointer tables in LEVD2/3 (slots 15, 16, 19 listed
above).

### Palette + IRQ — `&4900-&49FF`

| File off       | CPU            | Size  | Contents                                                                                       |
|----------------|----------------|-------|------------------------------------------------------------------------------------------------|
| `0x1280-0x12BE`| `&4900-&493E`  |    63 | `irq_palette_split` — vsync IRQ handler. Saves A/X/Y, picks vsync vs T1 path, primes T1 latch for mid-frame, then writes 12 bytes from `palette_top` to `&FE21`. |
| `0x12BF-0x12CE`| `&493F-&494E`  |    16 | `palette_top` — playfield palette table. **Only entries 0-11 are used by the IRQ**; the trailing 4 entries are unused padding. On disk these bytes hold the scenario-1 palette (`07 17 47 57 26 36 66 76 84 94 C4 D4 A0 B0 E0 F0` → red / yellow / white). |
| `0x12CF-0x12DE`| `&494F-&495E`  |    16 | `palette_bottom` — scoreboard palette table. Same 12-effective-entries layout. Always `07 17 47 57 23 33 63 73 81 91 C1 D1 A0 B0 E0 F0` → blue / cyan / white. |
| `0x12DF-0x12FD`| `&495F-&497D`  |    32 | `irq_palette_split_b` — T1-timer IRQ entry (mid-frame). Writes `palette_bottom` to `&FE21`, then optionally uninstalls if `zp_irq_enable != 0`. |
| `0x12FE-0x1324`| `&497E-&49A4`  |    39 | `irq_install` — called by Loader2 line 1000 (`CALL &497E`). Saves the prior IRQ1V at zp `&64`/`&65`, installs `irq_palette_split` as the new vector, and primes the User VIA T1L-H + IER + ACR. |
| `0x1325-0x137F`| `&49A5-&49FF`  |    91 | Trailing data — small lookup tables, purpose TBD. |

---

## `$.CODE` (5863 bytes at `&1100`)

The main game binary. Annotated in `disasm/CODE.beebasm` (driven by
`disasm/CODE.cfg.json` — reachability-traced from a single entry at
`&1100`, with two forced-data regions for the screen-line LUTs).

### Notable named routines

| Address  | Label                       | Notes                                                                                                             |
|----------|-----------------------------|-------------------------------------------------------------------------------------------------------------------|
| `&1100`  | `main_init`                 | Entry. `JSR restore_score_from_loader` (CODE2), `JSR init`, `JSR draw_title_screen` (CODE2), fall through to `main_loop`. Called as `CALL &1100` from BASIC Runner/Loader4 on each level start. |
| `&1109`  | `main_loop`                 | Per-frame top: calls `L13D1`, polls `KEY_QUIT` via `check_key_pressed`, branches to `game_over_or_continue` (CODE3) on game-over or to the stage transition on level complete. |
| `&1141`  | `lfsr_random`               | 40-bit Galois LFSR over `zp_0D..zp_11`; four outputs at `rndval256` / `rndval64` / `rndval32` / `rndval16` (raw, raw>>2, raw>>3, raw>>4). Called by force-field renderer + a couple of spawn paths. |
| `&116F`  | `sprite_plot_default`       | Plot with X=1, Y=32. Falls through to `sprite_plot_xy`.                                                            |
| `&1173`  | `sprite_plot_xy`            | The main sprite blitter. Takes X=width-in-byte-cols, Y=height-in-scanlines, src in `sprite_src_lo/hi` (`&1194`/`&1195`, self-mod). |
| `&1184`  | `sprite_plot_inner`         | The inner loop. Reads `zp_sprite_dir_flag` (`&79`) to pick forward (=1, normal) or backward (=0, **vertical flip**) traversal of the column-major source. |
| `&1193`  | `sprite_plot_lda_sm`        | The `LDA &FFFF,X` byte at `sprite_src_lo`/`_hi` is *self-modified* — callers write the sprite source there before JSR. |
| `&1209`  | `screen_row_lo_lut`         | 22 bytes, low byte of char-row start address for MODE 5 (base &5800, stride &140).                                 |
| `&121F`  | `screen_row_hi_lut`         | Paired high bytes.                                                                                                 |
| `&1236`  | `calc_screen_addr`          | Compute screen address from X (char-col) and Y (scanline). Result in `&76`/`&77`.                                  |
| `&127B`  | (tile draw, unnamed)        | Draws the new column on the right edge of the playfield: upper tile mirrored at char rows 0-3 (src = `zp_tile_upper_lo/hi`), lower tile normal at rows 16-19 (src = `zp_tile_lower_lo/hi`). |
| `&13BC`  | `frame_delay`               | Frame-rate regulator (busy-wait). Loops until `(zp_frame_progress)` budget is exhausted; reset to `zp_game_speed` for the next frame. See routine comment in `CODE.cfg.json` for the math. |
| `&13D1`  | (per-frame, unnamed)        | Reads tile IDs from `&7E10,X` / `&7F10,X`, advances the two `zp_tile_upper_lo/hi` and `zp_tile_lower_lo/hi` pointers by `(tile_id+1)*&80`, scrolls. (See [open Q] below on which table is upper vs lower.) |
| `&1478`  | `draw_player`               | Plot `lev_player_sprite` (6×22, from `&4E80` in LEVD1) at `(zp_player_x, zp_player_y)`. If `data_25A3 == 1` (force-pod power-up active), also call `draw_player_pod` at `(player_x+5, player_y+1)`. JSR `check_player_collisions`, JMP `update_bullets`. |
| `&14B5`  | `draw_player_pod`           | Plot the player's force-pod (rotating saucer that orbits the ship after a power-up). Selects one of three frames at `gfx_pod_frame0/1/2` (`&3900/&3960/&39C0`) based on `pod_anim_frame` (cycles 1↔2↔3 with each player vertical move). |
| `&14D9`  | `read_input`                | If joystick mode (`zp_9F == 1`) → `read_joystick`; else scan `KEY_RIGHT / KEY_LEFT / KEY_DOWN / KEY_UP / KEY_FIRE` in turn via `check_key_pressed`. |
| `&1517`  | `read_joystick`             | OSBYTE &80 reads analog joystick 1 X/Y axes (low/high thresholds `&40` / `&C8`) and the fire button bit, dispatching the same `move_player_*` / `on_fire_pressed` routines as the keyboard path. |
| `&155B`  | `check_key_pressed`         | Wraps OSBYTE &81 (negative INKEY scan). Z=1 → not pressed, Z=0 → pressed. Pre-defined `KEY_*` constants for the 7 keys the game polls. |
| `&1565`  | `move_player_left`          | `DEC zp_player_x`, clamped at min `&02`.                                                                           |
| `&16A6`  | `move_player_right`         | `INC zp_player_x`, clamped at max `&14`.                                                                           |
| `&16B0`  | `move_player_down`          | `zp_player_y += 4`, clamped at max `&DC`. Also `INC pod_anim_frame` (wraps 4→1).                                   |
| `&16CC`  | `move_player_up`            | `zp_player_y -= 4`, clamped at min `&98`. Also `DEC pod_anim_frame` (wraps 0→3).                                   |
| `&17B9`  | `on_fire_pressed`           | If `zp_8A` cooldown elapsed, find an empty `player_bullet_x` slot, store player position there, reload cooldown from `fire_cooldown_reload`, play `sfx_fire`. |
| `&17E7`  | `update_bullets`            | Per-frame: iterate the 6 player_bullet slots; for each active one move +2 px/frame to the right; erase + clear off-screen; else replot the 3×2 bullet sprite and run `check_bullet_hits`. Finally decrement `zp_8A`. |
| `&1847`  | `check_bullet_hits`         | Two collision loops over the current bullet's position: (a) X=8..1 over the enemy slots in `enemy_x/_y/enemy_state` — INC `enemy_state[X]`, milestones at values 3/5/7 play OSWRCH 7 + INC `pickup_kill_count`; (b) X=0..7 over the hazard slots in `hazard_x/_y/hazard_type` — DEC `hazard_hp`, on kill mutate `hazard_type` to `&14` to start the death animation. Bullet erases itself either way. |
| `&198B`  | `check_player_collisions`   | Per-frame player collision check. Two 6×&18 bounding-box loops: (a) X=8..1 over enemy slots (active iff `enemy_state` in 1..9), (b) X=0..7 over hazard slots (active iff `hazard_type < &14`). Hit → OSWRCH 7 (the Loader2-redefined bell, used as a short blip) + the slot marked expired + `lose_a_life`. |
| `&1AEB`  | `update_enemies`            | Per-frame enemy-pool driver. Iterates X = n_enemies..1; for each active slot calls `enemy_check_collisions`, `enemy_select_motion` (reads next `(dy_dir, dx_dir)` from the active pattern script), then `L1B2D` to apply motion + erase/redraw + maybe fire. Slot deactivates and is erased when `enemy_state` drops to 0. |
| `&1DEE`  | `lose_a_life`               | Plays OSWRCH 7; toggles `lives_blink_state`, decrements `player_hp` every other call; redraws the lives icon (`gfx_icon_lives` or `gfx_icon_lives_blink` per blink state). When `player_hp` hits 0 + blink-state 1 → `death_anim`. |
| `&1F8E`  | `init`                      | Per-level init. Player pos `&05, &C8`, scroll counter `&80=0`, zero-fills the combined 9-slot state arrays at `&2052..&208A` (covers both hazard and enemy state), the 6 player_bullet slots, force-pod registers; sets `fire_cooldown_reload=6` and the 7 `npc_bullet_x` slots to `&FF` (inactive). |
| `&208A`  | `spawn_check_step`          | Matches `zp_scroll_col` against `lev_spawn_col[zp_7B]`; on hit, fills a hazard slot from the attribute byte at `lev_spawn_attr[X]`: bits 0..4 → `hazard_type`, bits 5..6 → Y-row, bit 7 → `hazard_flip`. |
| `&22B2`  | `hazard_type_dispatch`      | Per-frame per-active-hazard immediate-action dispatch. Switch on `hazard_type[X]`: `&04` / `&13` → `enqueue_npc_bullet` (fires a leftward 4×2-px bullet); `&06` → CODE2 `spawn_hazard_missile` (homing rocket); `&07` → `forcefield_render` (the slot IS the force-field strip); `&08` → `spawn_flame` (one-shot 32×8-px flame, mutates self to `&09`); else → RTS. |
| `&232C`  | `forcefield_render`         | Procedural vertical strip. Calls `lfsr_random`, uses the result as the **low byte of `&80XX`** (i.e. reads from whatever sideways ROM is paged in at `&8000+`) as the sprite source, then plots 2 bytes × 32 lines. |
| `&234D`  | `forcefield_draw_or_erase`  | The draw path within `forcefield_render`.                                                                          |
| `&23A8`  | `forcefield_erase`          | The "blank out" path — plots 2 × 32 from `&7D80` (= zero-fill region = transparent erase).                          |
| `&2656`  | `starfield_init`            | One-shot at level start: walks the three 60-entry starfield arrays and plants each star's initial pixel byte at its starting screen address. Called from `L126C` when scroll counter hits `&F0`. |
| `&1309`  | `starfield_update`          | Per-frame: walk all 60 stars, erase, move left by 8 px (with row-wrap from left edge back to row 16 on right), re-plot. |

**[open Q] Tile-table upper/lower assignment.** Direct trace of `L13D1` / `L127B` says `tbl_7E10` is the table whose value drives `zp_tile_upper` (drawn mirrored at row 0), and `tbl_7F10` drives `zp_tile_lower` (drawn normally at row 16). The older docs / `render_map.py` had it the other way around. Since the rendered maps look right with the renderer's current labelling, this is either (a) an accident of the test cases being symmetric or (b) my assembly trace is missing something. Needs visual A/B against a live game capture to settle — for now the disassembly uses the names derived from the code trace.

### In-code data tables

The tracer auto-labelled these as `tbl_XXXX` (referenced via absolute-
indexed addressing from code):

| Address       | Size | Description                                                                 |
|---------------|------|------------------------------------------------------------------------------|
| `&1A55..&1A98` | 7×11 | Enemy slot pool: `enemy_x[11]` / `enemy_y[11]` / `enemy_state[11]` / `enemy_pattern_step[11]` / `enemy_pattern_id[10]` at `&1A55/&1A60/&1A6B/&1A76/&1A81`, then `npc_bullet_x[7]` / `npc_bullet_y[7]` at `&1A8B/&1A92` (the shared NPC bullet pool, used by both enemies and hazards). Only slots 1..8 of each are active; slot 0 is unused. |
| `&2052..&2088` | 6×9  | Hazard slot pool: `hazard_x` / `hazard_y` / `hazard_type` / `hazard_flip` / `hazard_hp` / `hazard_step` at `&2052/&205C/&2065/&206E/&2077/&2080`. 9 entries wide; slots 0..7 active. The arrays at `&2065..` overlap the parallel `enemy_state` clear region used by `init`. |
| `&2065`       | 9    | `hazard_type[X]` — read by `hazard_type_dispatch` and `hazard_anim_advance`. |
| `tbl_268F`    | 4    | NOP-pad before routine at `&2693` (no semantic content).                    |

(Several smaller `data_XXXX` blocks in the disasm are 2-4 byte state
variables embedded inline; see the cfg comments for any that have
been identified.)

---

## `$.CODE2` (2537 bytes at `&2800`)

Currently unannotated. Known facts:

- Starts with a sound-queue setup: `LDA #&07 / LDX #&09 / LDY #&28 /
  JMP OSWORD`. So the top of CODE2 is the SFX driver.
- Contains `spawn_hazard_missile` at `&2A20`, reached from
  `hazard_type_dispatch` (type 6). Launches a vertical 4×6-px
  yellow-red rocket that homes horizontally on the player.
- Contains some of the trampoline routines that JMP back into
  `sprite_plot_xy` after configuring `sprite_src` for specific
  decoration sprites.

---

## `$.CODE3` (912 bytes at `&3300`)

Inter-stage transition + the "LEVEL X COMPLETED / BONUS XXXX" message
display. Has the OSWRCH loops that print the inter-stage text strings
at file offsets `0x320`+ ("LOADING…PLEASE WAIT", "WOW! LEVEL X
COMPLETED", "BONUS", etc.).

---

## `N.LEVD1` (3584 bytes, loaded at `&4A00` for all scenarios)

Per-scenario tile graphics. Same internal layout for all four
scenarios; only the bytes differ:

| File off       | CPU            | Size  | Contents                                                                                                                                                       |
|----------------|----------------|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `0x0000-0x047F`| `&4A00-&4E7F`  | 1152  | **Decoration sprite bank.** Referenced by enemy-ptr-table slots 17 (`&5180`), 18 (`&5100`), 21 (`&4A00`), 22 (`&4A80`), 23 (`&4B00`), 24 (`&4B80`). Standard 4×32 column-major sprites. |
| `0x0480-0x04FF`| `&4E80-&4EFF`  |   128 | **Player ship sprite.** Hardcoded into the engine at `&4E80` (see `JMP L1478` paths in CODE that plot it with `LDX #&06, LDY #&16`).                            |
| `0x0500-0x0DFF`| `&4F00-&57FF`  | 2304  | **Tile catalog.** Each tile is 128 bytes = 4 byte-columns × 32 scanlines column-major (16 px wide × 32 px tall). Up to 18 tiles per scenario; the actual catalog usually only fills the first ~12-15. Tile *id N* lives at file offset `0x500 + N*0x80`. |

The decoration sprites visible in the gameplay screenshots (gun
turrets at the floor, pillars, etc.) come from this bank.

---

## `N.LEVD2` (3200 bytes, loaded at `&7380`)

The stage-1 data for each scenario. The single most information-
dense file on the disk.

| File off       | CPU            | Size | Contents                                                                                                                          |
|----------------|----------------|------|-----------------------------------------------------------------------------------------------------------------------------------|
| `0x0000-0x06FF`| `&7380-&7A7F`  | 1792 | **In-scenario hazard sprite graphics** (14 sprites × 128 B each, 4×32 col-major; slots 0-13 in `lev_hazard_*`). Includes the 8 frames of the hazard death-anim used by `hazard_death_step` at types `&14..&1B`. |
| `0x0700-0x073F`| `&7A80-&7ABF`  |   64 | `lev_hazard_ptr_lo` — sprite-pointer LO byte, 32 slots. Slots 21..26 are aliased as `lev_explosion_ptr_lo` (the player-explosion frame pointers). |
| `0x0740-0x077F`| `&7AC0-&7AFF`  |   64 | `lev_hazard_ptr_hi` — paired HI byte. Slot N's sprite address = `(hi[N]<<8) \| lo[N]`. Resolves into one of GRAPHIX (slots 15/16/19), LEVD1 (per-scenario sprite slots), or LEVD2 itself. |
| `0x0780-0x07FF`| `&7B00-&7B7F`  |  128 | `lev_spawn_col` — sorted ascending list of scroll-column indices at which a hazard spawns. `&FF` terminator. |
| `0x0800-0x087F`| `&7B80-&7BFF`  |  128 | `lev_spawn_attr` — paired attribute byte per schedule entry. Bits 0..4 = `hazard_type` (→ `hazard_type_dispatch`); bits 5..6 = Y-row (0=&DF / 1=&BF / 2=&9F / 3=&7F); bit 7 = `hazard_flip` (vertical-mirror, INVERTED: 0 in attr = upright). |
| `0x0880-0x08FF`| `&7C00-&7C7F`  |  128 | **Shootable item sprite — intact frame** (slot 25 in the ptr table). Per-scenario: arch / egg / figure-8 / organic blob.          |
| `0x0900-0x097F`| `&7C80-&7CFF`  |  128 | **Shootable item sprite — damaged frame** (slot 26).                                                                              |
| `0x0980-0x0A8F`| `&7D00-&7E0F`  |  272 | **All-zero region.** Doubles as the universal "erase brush" — `&7D80` (referenced by the default `zp_sprite_src` init in `L1F8E` and many small-effect erase calls) and `&7E02` (small 3×2 / 2×2 effect erases). |
| `0x0A90-0x0B7F`| `&7E10-&7EFF`  |  240 | **Map LOWER tile-id table.** One byte per column, indexes a tile in the LEVD1 catalog. Rendered at char rows 16-19.                |
| `0x0B80-0x0B8F`| `&7F00-&7F0F`  |   16 | 16 bytes of padding between the lower and upper tile tables. Same value per scenario (`0D`/`00`/`03`/varying) — likely a wrap-around-column safety byte. |
| `0x0B90-0x0C7F`| `&7F10-&7FFF`  |  240 | **Map UPPER tile-id table.** Same indexing, rendered at char rows 0-3 with **vertical mirror** (the engine plots the upper tile with `zp_sprite_dir_flag = 0`). |

---

## `N.LEVD3` (2176 or 3200 bytes, loaded at `&7380`)

The stage-2 data. The format is identical to `LEVD2` byte-for-byte
within whatever range it covers — but the **size differs** by
scenario:

| File        | Size  | Covered range (file offset) | What it overwrites                                                                                  |
|-------------|-------|-----------------------------|------------------------------------------------------------------------------------------------------|
| `1.LEVD3`   | 2176  | `0x000-0x87F`               | Enemy sprites + ptr tables + spawn schedule + attributes. **Leaves the LEVD2 map tables intact.**    |
| `2.LEVD3`   | 2176  | `0x000-0x87F`               | Same as above.                                                                                       |
| `3.LEVD3`   | 2176  | `0x000-0x87F`               | Same as above.                                                                                       |
| `4.LEVD3`   | 3200  | `0x000-0xC7F`               | Full overlay including the map tables — but the tile-id tables happen to be **byte-identical** to `4.LEVD2`'s, so the map geometry is still unchanged. |

**Net effect:** stage 2 of every scenario uses the same ceiling /
floor tile geometry as stage 1; only the enemy cast (sprite graphics,
pointer table, spawn schedule, attributes) changes. The shootable-
item sprites at `&7C00`/`&7C80` are not touched by `LEVD3` in
scenarios 1-3, so the same "arch / egg / etc." is reused for both
halves.

In every `LEVD3` the enemy pointer table layout is **identical
across all four scenarios**: slot 0 = `&7D80` (blank), slots 1-14 =
the per-scenario sprite slots at `&7380..&7A00`, slots 15-16 = shared
GRAPHIX, slots 17-18 = LEVD1, slot 19 = GRAPHIX, slots 21-24 = LEVD1
decorations, slots 25-26 = the shootable items in LEVD2's upper area.
What differs between scenarios' `LEVD3` files is just the *sprite
data* the slots 1-14 point at and the *spawn schedule*.
