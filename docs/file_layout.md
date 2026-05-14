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
| `&3680`  | 16×16 (64)     | `muzzle_flash_frame0` — player gun flash, frame 0                   |
| `&36C0`  | 16×16 (64)     | `muzzle_flash_frame1` — player gun flash, frame 1                   |
| `&3700`  | 16×32 (128)    | `enemy_slot15` — LEVD2/3 ptr-table slot 15 (shared cross-scenario)  |
| `&3780`  | 16×32 (128)    | `enemy_slot16` — LEVD2/3 ptr-table slot 16                          |
| `&3800`  | 24×16 (96)     | `text_wow` — "WOW!" inter-stage banner                              |
| `&3860`  |  8×12 (24)     | `ball_frame0` — chomping-orb animation, frame 0                     |
| `&3878`  |  8×12 (24)     | `ball_frame1`                                                       |
| `&3890`  |  8×12 (24)     | `ball_frame2`                                                       |
| `&38A8`  |  8×12 (24)     | `ball_frame3`                                                       |
| `&38C0`  |  8×12 (24)     | `ball_frame4`                                                       |
| `&38D8`  |  8×12 (24)     | `ball_frame5`                                                       |
| `&38F0`  | — (16)         | Alignment pad — pushes the next sprite onto a page boundary         |
| `&3900`  | 12×24 (72)     | `enemy_saucer_frame0` — rotating saucer, frame 0                    |
| `&3948`  | — (24)         | Blank separator column (1×24)                                       |
| `&3960`  | 12×24 (72)     | `enemy_saucer_frame1`                                               |
| `&39A8`  | — (24)         | Blank separator                                                     |
| `&39C0`  | 12×24 (72)     | `enemy_saucer_frame2`                                               |
| `&3A08`  | — (24)         | Trailing blank                                                      |
| `&3A20`  |  4×8 (8) ×8    | `icon_00..icon_07` — 8 small 4×8 glyphs (small-char bank, first 8)  |
| `&3A60`  |  4×8 (8) ×10   | `digit_0..digit_9` — 10 small 4×8 digits                            |
| `&3AB0`  |  4×8 (8) ×2    | `icon_08`, `icon_09` — two more small 4×8 glyphs                    |
| `&3AC0`  | — (64)         | Blank pad — unused tail of the 28-slot small-char bank              |
| `&3B00`  | 32×8 (64)      | `flame_frame0` — engine flame, frame 0                              |
| `&3B40`  | 32×8 (64)      | `flame_frame1`                                                      |
| `&3B80`  | 32×8 (64)      | `flame_frame2`                                                      |
| `&3BC0`  | 80×16 (320)    | `text_press_space` — "PRESS SPACE!"                                 |
| `&3D00`  | 28×32 (224)    | `logo_4thdim` — small "4TH DIM" logo block                          |
| `&3DE0`  | 36×16 (144)    | `text_score` — "SCORE"                                              |
| `&3E70`  |  4×16 (16)     | `punct_colon` — ":"                                                 |
| `&3E80`  | 28×16 (112)    | `text_last` — "LAST"                                                |
| `&3EF0`  | 28×16 (112)    | `text_high` — "HIGH"                                                |
| `&3F60`  |  8×16 (32)     | `punct_ampersand` — "&"                                             |
| `&3F80`  | 56×16 (224)    | `text_gpr90` — "GPR'90!"                                            |
| `&4060`  |  8×16 (32)     | `pickup_red` — red pickup                                           |
| `&4090`  |  8×16 (32)     | `pickup_yellow` — yellow pickup                                     |
| `&40C0`  |  8×16 (32)     | `pickup_checker` — checker pickup                                   |
| `&40E0`  | — (32)         | Pre-text pad                                                        |
| `&4100`  | 64×16 (256)    | `text_get_ready` — "GET READY!"                                     |
| `&4200`  | 32×16 (128)    | `text_game` — "GAME"                                                |
| `&4280`  | 32×16 (128)    | `text_over` — "OVER"                                                |
| `&4300`  | 24×16 (96)     | `text_on` — "ON!"                                                   |
| `&4360`  | 16×32 (128)    | `enemy_slot19` — LEVD2/3 ptr-table slot 19                          |
| `&43E0`  | — (48)         | Pre-missile pad                                                     |
| `&4410`  | 20×8 (40)      | `missile_0` — projectile sprite, frame 0                            |
| `&4438`  | 20×8 (40)      | `missile_1`                                                         |
| `&4460`  | 20×8 (40)      | `missile_2`                                                         |
| `&4488`  | 20×8 (40)      | `missile_3`                                                         |
| `&44B0`  | 20×8 (40)      | `missile_4`                                                         |
| `&44D8`  | — (40)         | Post-missile pad                                                    |
| `&4500`  | — (592)        | `unknown_table` — 592 B data block, purpose TBD (no code ref yet)   |
| `&4750`  |  8×16 (32)     | `pickup_white` — 4th pickup variant                                 |
| `&4770`  | — (16)         | Pad                                                                 |
| `&4780`  | 36×14 (126)    | `text_pause` — "PAUSE"                                              |
| `&47FE`  | — (2)          | Pad                                                                 |
| `&4800`  |  4×8 (8) ×8    | `icon_10..icon_17` — 8 more small 4×8 glyphs                        |
| `&4840`  | — (8)          | Pad                                                                 |
| `&4848`  |  4×8 (8)       | `bomb` — small bomb/ball sprite                                     |
| `&4850`  | — (8)          | Pad                                                                 |
| `&4858`  | 12×24 (72)     | `enemy_small_frame0` — small enemy animation, frame 0               |
| `&48A0`  | 12×24 (72)     | `enemy_small_frame1` — frame 1                                      |
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
| `&1100`  | `main_init`                 | Entry. `JSR &3115` (init in CODE3), `JSR L1F8E` (level init), `JSR &2CCA` (in CODE2), fall through to `main_loop`. |
| `&1109`  | `main_loop`                 | Per-frame top: calls `L13D1`, polls quit key, falls through.                                                       |
| `&1141`  | `lfsr_random`               | 16-bit LFSR; results in `&116B..&116E`. Called by force-field renderer + a couple of spawn paths.                  |
| `&116F`  | `sprite_plot_default`       | Plot with X=1, Y=32. Falls through to `sprite_plot_xy`.                                                            |
| `&1173`  | `sprite_plot_xy`            | The main sprite blitter. Takes X=width-in-byte-cols, Y=height-in-scanlines, src in `&1194`/`&1195` (self-mod).     |
| `&1184`  | `sprite_plot_inner`         | The inner loop. Reads `zp_sprite_dir_flag` (`&79`) to pick forward (=1, normal) or backward (=0, **vertical flip**) traversal of the column-major source. |
| `&1193`  | `sprite_plot_lda_sm`        | The `LDA &FFFF,X` byte at `&1194`/`&1195` is *self-modified* — callers write the sprite source there before JSR.   |
| `&1209`  | `screen_row_lo_lut`         | 22 bytes, low byte of char-row start address for MODE 5 (base &5800, stride &140).                                 |
| `&121F`  | `screen_row_hi_lut`         | Paired high bytes.                                                                                                 |
| `&1236`  | `calc_screen_addr`          | Compute screen address from X (char-col) and Y (scanline). Result in `&76`/`&77`.                                  |
| `&127B`  | (tile draw, unnamed)        | Draws the new column on the right edge of the playfield: upper tile mirrored at char rows 0-3, lower tile normal at rows 16-19. |
| `&13D1`  | (per-frame, unnamed)        | Reads upper/lower tile IDs from `&7F10,X` / `&7E10,X`, advances `sprite_src` pointers by `(tile_id+1)*&80`, scrolls. |
| `&1F8E`  | (level init, unnamed)       | Zeros most state, sets player pos `&81=5, &82=&C8`, scroll counter `&80=0`, sprite pointers to `&7D80` (the erase brush). |
| `&208A`  | `spawn_check_step`          | Matches `&80` (scroll col) against `&7B00,&7B`; on hit, fills an object slot from the attribute byte at `&7B80,X` (type → `&2065,X`, Y-row → `&205C,X`, v-flip → `&206E,X`). |
| `&22B2`  | `enemy_type_dispatch`       | Switch on `&2065,X` (the type field): 4/&13 → multi-shot, 6 → CODE2 `&2A20`, 7 → `forcefield_render`, 8 → `L2464`, &10 → high-HP boss path, others → default sprite plot from `&7A80/&7AC0[type]`. |
| `&232C`  | `forcefield_render`         | Procedural vertical strip. Calls `lfsr_random`, uses the result as the **low byte of `&80XX`** (i.e. reads from whatever sideways ROM is paged in at `&8000+`) as the sprite source, then plots 2 bytes × 32 lines. |
| `&234D`  | `forcefield_draw_or_erase`  | The draw path within `forcefield_render`.                                                                          |
| `&23A8`  | `forcefield_erase`          | The "blank out" path — plots 2 × 32 from `&7D80` (= zero-fill region = transparent erase).                          |

### In-code data tables

The tracer auto-labelled these as `tbl_XXXX` (referenced via absolute-
indexed addressing from code):

| Address       | Size | Description                                                                 |
|---------------|------|------------------------------------------------------------------------------|
| `tbl_1A55-95` | 64×5 | 5 parallel arrays × ≤11 entries: object slot X position, Y position, type/alive flag, ?, attribute carry. Used by the "secondary object" (= bullet / spark / pickup) subsystem. |
| `tbl_2052-86` | 9×6+ | Active-enemy object slots. Fields per slot: spawn column (`&2052,X`), spawn Y (`&205C,X`), type (`&2065,X`), v-flip (`&206E,X`), HP / timer (`&2077,X`), state (`&2080,X`). |
| `tbl_2065`    | 9    | Subset of the above — the type field, read by `enemy_type_dispatch`.        |
| `tbl_268F`    | 4    | NOP-pad before routine at `&2693` (no semantic content).                    |

(Several smaller `data_XXXX` blocks in the disasm are 2-4 byte state
variables embedded inline; see the cfg comments for any that have
been identified.)

---

## `$.CODE2` (2537 bytes at `&2800`)

Currently unannotated. Known facts:

- Starts with a sound-queue setup: `LDA #&07 / LDX #&09 / LDY #&28 /
  JMP OSWORD`. So the top of CODE2 is the SFX driver.
- Contains the routine at `&2A20` reached from `enemy_type_dispatch`
  (type 6) — purpose not yet identified.
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
| `0x0000-0x06FF`| `&7380-&7A7F`  | 1792 | **In-scenario enemy sprite graphics.** 14 sprites of 128 bytes each (4×32 col-major), filling slots 1-14 of the pointer table.    |
| `0x0700-0x073F`| `&7A80-&7ABF`  |   64 | **Enemy sprite pointer LOW byte** (64 slots).                                                                                     |
| `0x0740-0x077F`| `&7AC0-&7AFF`  |   64 | **Enemy sprite pointer HIGH byte** (paired with LOW). Slot N's sprite address = `(hi[N]<<8) \| lo[N]`. Resolves into one of GRAPHIX / LEVD1 / inside LEVD2 itself. |
| `0x0780-0x07FF`| `&7B00-&7B7F`  |  128 | **Spawn-column schedule.** Sorted ascending list of scroll-column indices at which an enemy spawns. `&FF` terminator.             |
| `0x0800-0x087F`| `&7B80-&7BFF`  |  128 | **Spawn attribute byte** per schedule entry. Bits 0-4 = type (→ `enemy_type_dispatch`); bits 5-6 = Y-row (0=&DF, 1=&BF, 2=&9F, 3=&7F → char rows 4/8/12/16); bit 7 = v-flip. |
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
