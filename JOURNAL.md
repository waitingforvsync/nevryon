# Nevryon RE Journal

Newest entries at the top.

---

## 2026-05-15 — Session 11: bullets / hazards / tile-pointer pair

### `L17E7` is the real `update_bullets`

Last session I'd called `L1AEB` "update_bullets", but the second look
through the per-frame chain showed the real player-bullet update lives
at `&17E7`: iterate the 6 `player_bullet_x/y` slots, advance each by
+2 px/frame to the right, erase + clear when it crosses col `&25`,
otherwise replot the 3×2 bullet sprite and run `check_bullet_hits`
(`L1847`). Decrements the fire cooldown (`zp_8A`) at the end. Now
named `update_bullets`.

### `L1847` → `check_bullet_hits`

Called once per active player-bullet by `update_bullets`. Two
collision loops over the current bullet's position:

  - **X=8..1** over the 8-slot "hazard" track (`hazard_x` /
    `hazard_y` / `hazard_state`, formerly `tbl_1A55..tbl_1A6B`). A hit
    INCs `hazard_state[X]`; values 3 / 5 / 7 trigger an OSWRCH 7
    milestone (the Loader2-redefined bell — see Session 10) and bump
    `data_25A0`; `>=9` retires the hazard.
  - **X=0..7** over the active enemy table. A hit decrements
    `enemy_hp`, plays explode, and on kill clears the slot.

The bullet erases itself (3×2 brush) and frees its slot regardless.

### `L1AEB` → `update_hazards`

The 8-slot mover for the same hazard track that
`check_player_collisions` and `check_bullet_hits` both reference.
Each frame moves an active hazard by ±1 X / ±4 Y (depending on the
`data_16F6` / `data_16F7` direction flags), erases + redraws the 4×24
sprite, deactivates the slot when `hazard_state == 0`. Renamed the
backing tables to `hazard_x` / `hazard_y` / `hazard_state` (= the
3 parallel 11-byte arrays at `&1A55` / `&1A60` / `&1A6B`).

### `zp_sprite_src` / `zp_sprite_src2` were misnamed

The two zp pairs at `&8D/&8E` and `&8B/&8C` are NOT the sprite
engine's source bytes (those are the self-modified operand at
`sprite_src_lo/hi` = `&1194` / `&1195` inside `sprite_plot_inner`).
They are the **per-column map-tile pointers** used by `L13D1`:
each frame walks the LEVD2 tile-id table and computes where to read
the current column's tile from in the LEVD1 catalog at `&4E80`. Two
pairs because the upper and lower tile bands are drawn in the same
column-update cycle from different sources:

| New name             | Old name              | Tile band  | Drawn at      | dir_flag           |
|----------------------|-----------------------|------------|---------------|--------------------|
| `zp_tile_upper_hi/lo` | `zp_sprite_src_hi/lo` (`&8D/&8E`)   | top (mirror) | row 0  | 0 = vertical mirror |
| `zp_tile_lower_hi/lo` | `zp_sprite_src2_hi/lo` (`&8B/&8C`) | bottom    | row 16 | 1 = normal          |

Renamed in `Nevryon.6502` and both per-binary cfgs that reference
them, with a multi-line comment in the master explaining the
historical confusion.

### Open question: which tile-id table is upper vs lower?

A direct trace of `L13D1` followed into `L127B` says
`tbl_7E10` feeds `zp_tile_upper` (drawn mirrored at row 0) and
`tbl_7F10` feeds `zp_tile_lower` (drawn normally at row 16) — i.e.
the opposite of how `docs/file_layout.md` and `render_map.py` had
them labelled. Since the rendered maps look right with the
renderer's current assignment, the resolution is either (a) the
test cases happen to be visually similar with either assignment,
or (b) my assembly trace is missing something subtle. Captured the
discrepancy in the docs with an "[open Q]" marker; for now the
disassembly uses the names the code trace implies.

### `docs/file_layout.md` updated

Routine table now lists all the new identifications:
`frame_delay`, `draw_player`, `draw_player_pod`, `read_input`,
`read_joystick`, `check_key_pressed`, the four `move_player_*`
helpers, `on_fire_pressed`, `update_bullets`, `check_bullet_hits`,
`check_player_collisions`, `update_hazards`, `lose_a_life`, `init`,
`starfield_init`, `starfield_update`. GRAPHIX table rebranded
the three "enemy saucer" frames to `gfx_pod_frame0/1/2`.

All four binaries continue to build byte-identical.

### Next

  - Settle the tile-table upper/lower question (visual A/B against a
    live game capture).
  - Trace `data_25A3`'s set path — gates the force-pod drawing, so
    it's the "force-pod attached" flag.
  - `data_2050` looks like a 4-bit shield / damage counter from
    `lose_a_life`'s every-other-call decrement; would be nice to
    confirm.
  - The remaining `L<addr>` entry points in CODE2 (`L28A9`, `L2975`,
    `L2998`, `L2FF0`, `L3058`).

---

## 2026-05-15 — Session 10: player rendering + collision + readability

### Routines named

| Addr     | Name                       | Purpose |
|----------|----------------------------|---------|
| `&13BC`  | `frame_delay`              | (named last session — restated for completeness.) |
| `&1478`  | `draw_player`              | Plot `lev_player_sprite` (6×22 from `&4E80`) at `(zp_player_x, zp_player_y)`. If `data_25A3 == 1` (force-pod power-up active), also call `draw_player_pod` at `(player_x+5, player_y+1)`. Then JSR `check_player_collisions`, JMP to update_player_bullets. |
| `&14B5`  | `draw_player_pod`          | Plot the player's force-pod (the rotating saucer that orbits the ship after a power-up). Selects one of three frames at `gfx_pod_frame0/1/2` (`&3900/&3960/&39C0`) based on `pod_anim_frame` (= `data_14D8`). |
| `&14D8`  | `pod_anim_frame`           | 1/2/3 frame selector for `draw_player_pod`. Cycles on every player vertical move: `move_player_down` INCs it (wraps 4→1), `move_player_up` DECs it (wraps 0→3). |
| `&198B`  | `check_player_collisions`  | Per-frame player collision check. Two loops over slots 1..8 / 0..7 testing player vs 6×&18 bounding boxes around (a) entries in `tbl_1A55/tbl_1A60/tbl_1A6B` and (b) entries in the active-enemy table (`enemy_x/y/type < &14`). The "delay" appearance is two parallel 8-slot iterations, not actual delay loops. On hit: OSWRCH &07 (see "OSWRCH 7 = blip" below) + JSR `lose_a_life`. |
| `&1DEE`  | `lose_a_life`              | Plays the OSWRCH 7 collision blip, toggles `data_1E46` (0↔1), decrements `data_2050` every other call (two-step blink), and redraws the lives icon at row `&5F`. |

### The "enemy_saucer" sprites are actually the player force-pod

The three 4×24 sprites at `&3900` / `&3960` / `&39C0`, previously
labelled `gfx_enemy_saucer_frame0..2`, were a session 3 misidentification.
A grep across all binaries shows **zero** code references to those
addresses except via `draw_player_pod`. No LEVD2 enemy ptr-table slot
points at them either — they're solely the player's orbiting force-pod
animation, three rotation frames driven by `pod_anim_frame`. Renamed
to `gfx_pod_frame0` / `gfx_pod_frame1` / `gfx_pod_frame2` in
`disasm/GRAPHIX.cfg.json`.

### OSWRCH &07 — the redefined BBC bell

`check_player_collisions` and `lose_a_life` both do `LDA #&07 / JSR
OSWRCH`. That's the BBC's "ring bell" character — normally a quarter-
second piano-like beep. Loader2 lines 5-9 redefine it via OSBYTE
`*FX211 / *FX212 / *FX213 / *FX214` to be a short un-musical blip with
duration 1, used in-game as a generic "collision / hit / pickup" SFX
without burning a `OSWORD &07` slot.

### Disassembler — blank line before each routine entry

`disasm/CODE.6502` was getting hard to read with subroutine bodies
running into each other. Three sources of "routine entry" addresses
now trigger a leading blank line in the code emitter:

  1. Any address that's a JSR destination (from any code region).
  2. Any address in `cfg.entries`.
  3. Any address with a user-supplied name in `cfg.labels` —
     auto-generated `L<addr>` / `data_<addr>` labels are excluded
     so local branch targets inside a routine don't break the flow.

`collect_branch_targets` got a `jsr_targets` out-param, and
`disasm_code_region` got a matching input set that gates a leading
`""` line before each named label. The check skips the very first
label in a region (no leading blank) and de-dupes adjacent blanks.

All four binaries still build byte-identical.

### Next

  - Decode `tbl_1A55 / tbl_1A60 / tbl_1A6B / tbl_1A76` — the 11-slot
    parallel array `check_player_collisions` iterates as "objects in
    the world that aren't in the main enemy slot table". Candidates:
    enemy bullets, hazards, or item pickups.
  - Trace `data_25A3`'s set/reset path — it gates the force-pod
    drawing in `draw_player`, so it's the "have-power-up" flag.
  - Document `data_2050` (`lose_a_life` decrements every other call)
    — looks like a 4-bit "damage absorbed" / "shield" counter.

---

## 2026-05-15 — Session 9: init routine + input layer named

### Per-level init (`&1F8E`) renamed

`L1F8E` → `init`. Called once per level by `main_init`. The
nine-iteration loop at `&1FB6` is the clear-enemy-slots pass —
zero-fills six parallel 9-byte tables. Each got a real name:

| Old name   | New name      | Purpose |
|------------|---------------|---------|
| `tbl_2052` | `enemy_x`     | X coord per slot. `&FF` would mean "off-screen right" but here 0 = empty (`tbl_2065,X==0` is the canonical empty test). |
| `tbl_205C` | `enemy_y`     | Y coord per slot (rows 0/1/2/3 of the playfield map to &DF/&BF/&9F/&7F). |
| `tbl_2065` | `enemy_type`  | Spawn type (0 = empty, else index into the LEVD2 enemy ptr table at `&7A80`/`&7AC0`; `&14` = "exploding" pseudo-type). |
| `tbl_2077` | `enemy_hp`    | Hit points; init `&08`, special types `&14` (boss) or `&06`. |
| `tbl_2080` | `enemy_step`  | Slide-in / animation counter (initial `&04`, decrements until 1 then erases). |
| `tbl_206E` | `enemy_flip`  | Vertical flip flag (drives `zp_sprite_dir_flag`; set from spawn-attribute bit 7). |

(`tbl_1A6B` is also zeroed in the same loop but is a separate
9-byte table used by the bullet update path — left as `tbl_1A6B`
until the bullet system is fully traced.)

The trailing singleton stores from `&1FC9` onwards initialise:
the four (well, 7) player-bullet slots at `player_bullet_x` /
`player_bullet_y` (= old `tbl_16E6` / `tbl_16ED` at `&16E6` /
`&16ED`); the force-pod registers at `&25A0..&25A9`; the
bullet-inactive markers at `&1A8B..&1A91` (init `&FF`); and
`fire_cooldown_reload = &06` (= `data_2554` rebranded, since
`on_fire_pressed` reloads `zp_8A` from it after each shot).

### Input handler — symbolic key constants

`L155B` → `check_key_pressed`: thin wrapper over `OSBYTE &81`
(INKEY -X) with Y=&FF. Returns Z=1 when the key whose internal
scan code is in X is NOT pressed, Z=0 when pressed. Seven call
sites, each with a hard-coded `LDX #&XX` — now rewritten via
immediate-overrides so they read as named constants:

| Hex (X reg) | INKEY -N | New constant |
|-------------|----------|--------------|
| `&BD` | `-67`  | `KEY_RIGHT` ("X" key) — calls `move_player_right` |
| `&9E` | `-98`  | `KEY_LEFT`  ("Z" key) — calls `move_player_left` |
| `&B7` | `-73`  | `KEY_DOWN`  — calls `move_player_down` |
| `&97` | `-105` | `KEY_UP`    — calls `move_player_up` |
| `&B6` | `-74`  | `KEY_FIRE`  — calls `on_fire_pressed` |
| `&C8` | `-56`  | `KEY_PAUSE` — calls `pause_game` |
| `&8F` | `-113` | `KEY_QUIT`  — abandons the run (resets level_num=0, saves score, plays death sequence, returns to stage_loading_screen) |

Constants are declared once in `disasm/Nevryon.6502` so every binary
can reference them. The matching player-movement routines and the
fire-button handler were named in the same pass:

| Addr     | New name              |
|----------|-----------------------|
| `&14D9`  | `read_input`          |
| `&1517`  | `read_joystick`       |
| `&1565`  | `move_player_left`    |
| `&16A6`  | `move_player_right`   |
| `&16B0`  | `move_player_down`    |
| `&16CC`  | `move_player_up`      |
| `&17B9`  | `on_fire_pressed`     |
| `&1AEB`  | `update_bullets`      |

CODE.cfg gained comments explaining what each routine does (clamp
bounds for movement, find-empty-slot logic for fire, etc.). All
four binaries still build byte-identical.

### Side-effects

- CODE2.cfg externs updated to use the new names (`player_bullet_x`,
  `enemy_x/y/type/flip`, `fire_cooldown_reload`) so the same address
  shows the same identifier across all three CODE binaries.
- `data_2051` confirmed: != 0 means alive / playing; == 0 means
  game over (see `main_loop`: `LDA data_2051 / BNE L1114 /
  JMP game_over_or_continue`). Worth a `lives_remaining` rename
  in a future pass.

### Next

  - Decode the bullet system at `tbl_1A55 / tbl_1A60 / tbl_1A6B /
    tbl_1A76` — the 11-slot parallel arrays look like a separate
    weapon-projectile track (maybe enemy bullets, or the force-pod
    pellet stream).
  - Trace the remaining `L<addr>` entry points in CODE2 (`L28A9`,
    `L2975`, `L2998`, `L2FF0`, `L3058`) — most likely the
    title-screen state machine.
  - Rename `data_2051` → `lives_remaining` once a few more
    accesses are confirmed.
  - Inspect the four offset-into-named sprite call sites
    (CODE2 &2C0B, &2D5F, &2D8F, &2FAE).

---

## 2026-05-15 — Session 8: zero raw addresses + cumulative-master build

The disassembler now auto-promotes EVERY absolute (abs / abs,X / abs,Y)
and zero-page operand reference to a label — no more raw `INC &28D5`
or `STA &16E6,X` lines surviving in the output.

### Disassembler changes (`tools/disasm6502.py`)

  - `collect_table_targets` extended to return a third set
    `zp_addrs` in addition to indexed/plain absolute targets, and to
    INCLUDE targets that fall inside reached code (BBC code often
    reuses an instruction operand byte as scratchpad RAM — e.g.
    `play_death_sequence`'s 200-frame counter at `&28D8`, which is
    actually the LO operand byte of the `LDA force_pod_state` at
    `&28D7`). Mid-instruction targets get promoted to mid-instruction
    equates (the existing `code_emit_points` machinery already
    handled the emit; we just had to feed it the right addresses).
  - `DisasmConfig` gained two new dicts:
      - `auto_extern_labels`: out-of-range names auto-promoted by the
        tool (`zp_XX`, `data_XXXX`, `tbl_XXXX`). Always emitted
        inline so the per-binary `.6502` builds without help.
      - `master_externs`: parsed from the master file (see below).
        If an address has a master name, that name is adopted as a
        cfg extern (no inline equate) — the master's preferred name
        wins over an auto-generated fallback.
  - `--master <path>` CLI flag parses `name = &VAL` lines from a
    BeebAsm source so the disassembler knows which addresses are
    pre-declared. Trivial regex; ignores everything else.
  - The header dump now has a dedicated section
    *"Auto-promoted externs (zp/data outside this binary)"* listing
    the inline equates added by the tool, separate from the
    user-supplied externs.

### Build script (`build.sh`)

Build now regenerates the four `.6502` files from `extracted/` +
`*.cfg.json` before running BeebAsm — the source of truth is the
cfg, not the on-disk `.6502`. Each binary's regen uses a
**cumulative master** built from `Nevryon.6502` plus every
already-regenerated `.6502` file, in the same order they're
`INCLUDE`d in the final master. That guarantees an auto-promoted
`zp_9A = &9A` declared inside `CODE.6502` is visible (and skipped
inline) by the time `CODE2.6502` is regenerated — exactly once
across the whole build.

### Result

| File           | Raw 16-bit refs | Raw zp refs |
|----------------|-----------------|-------------|
| `CODE.6502`    | 0               | 0           |
| `CODE2.6502`   | 0               | 0           |
| `CODE3.6502`   | 0               | 0           |
| `GRAPHIX.6502` | 0               | 0           |

(Numerical offsets like `gfx_text_press_space + &A0` inside
`LO()/HI()` expressions don't count — those are arithmetic
constants, not address references.)

The `INC &28D5` the user flagged at CODE2 line 679 now reads
`INC data_28D5`. Same treatment for every other previously-raw
operand. CODE.cfg.json also gained explicit cross-binary names for
`force_pod_x/y/frame` and `score_d0..d3` so CODE and CODE2 use the
same labels for the same addresses.

All four binaries continue to build byte-identical against the
originals.

### Next

  - Trace the remaining `L<addr>` entry points in CODE2 (`L28A9`,
    `L2975`, `L2998`, `L2FF0`, `L3058`) and CODE — most likely
    candidates for naming: the title-screen state machine, the
    enemy-fire path, and the bullet/object update routines.
  - Many of the auto-promoted `tbl_XXXX` / `data_XXXX` names are
    placeholders. The next pass should rename the well-known ones
    (`tbl_1A6B` = active-enemy table, `tbl_2065` = enemy attribute
    cache, etc.) to descriptive identifiers.
  - Inspect the four offset-into-named sprite call sites
    (CODE2 &2C0B, &2D5F, &2D8F, &2FAE).
  - Label LEVD1 decoration sprite slots so CODE &1C25/&1C36 can
    use explicit names.

---

## 2026-05-15 — Session 7: CODE2 cross-references and routine names

CODE2 was the last binary still full of raw `JSR &1236` / `STA &1194`
forms — readable to nobody. Switched it to entries-mode tracing
(matching CODE / CODE3) and built out the cross-binary symbol table
in `disasm/CODE2.cfg.json`. The disasm now uses real names
everywhere:

  - `JSR calc_screen_addr` instead of `JSR &1236`
  - `STA sprite_src_lo` instead of `STA &1194`
  - `LDA force_pod_state` instead of `LDA &25A5`
  - `LDA score_d3,X` instead of `LDA &2A02,X`
  - `LDX force_pod_x` / `LDY force_pod_y` instead of raw `&2972/&2973`

### Newly named routines

| Addr     | Name                       | Purpose |
|----------|----------------------------|---------|
| `&2800`  | `sfx_fire`                 | Shot/fire SOUND (ch &13, pitch &4B) — tail-calls OSWORD &07 with param block at `sfx_fire_params`. |
| `&2811`  | `sfx_hit_lo`               | Lower-pitched single-tone SOUND (ch &12, pitch &28). |
| `&2822`  | `sfx_explode`              | Two queued SOUNDs in sequence: noise burst on ch 0 then tone on ch 1 — the classic explosion. |
| `&28D7`  | `force_pod_anim`           | Per-frame: if `force_pod_state` (&25A5) == 1, animates the 6-frame chomping-ball pod at (`force_pod_x`, `force_pod_y`) cycling through gfx_ball_frame0..5. |
| `&29E7`  | `draw_score`               | Plots the 6-digit BCD score at char-col 9 row &5F. |
| `&2A08`  | `draw_score_digit`         | Helper: takes A=digit, X=offset, picks gfx_digit_N (`&3A60 + 8*N`). |
| `&2A20`  | `spawn_enemy_missile`      | Allocates one of the two homing-missile slots (`tbl_2B9A[0..1]`), copies enemy XY in, sets direction, beeps. |
| `&2AA2`  | `update_enemy_missiles`    | Per-frame: step + collide both missile slots. |
| `&2AC4`  | `step_enemy_missile`       | Erase + move ±2 px + redraw one missile (`gfx_icon_08`). |
| `&2B48`  | `missile_player_collide`   | Box-test missile vs player; jump to death path on hit. |
| `&2BA4`  | `intro_get_ready`          | Level-start: draws 7 lives icons + shutter_fade + sfx_explode + 75-frame loop blitting `gfx_text_get_ready` (split as two 8-col halves). |
| `&2CCA`  | `draw_title_screen`        | Title screen: 4th Dimension logo + `&` + `GPR '90` + `PRESS SPACE`. Called from `main_init`. |
| `&2E83`  | `sfx_score_tick`           | Medium beep (ch &12 pitch &64 dur 3) — used both during BONUS roll-up and as the missile-launch confirmation. |
| `&2E94`  | `play_death_sequence`      | Shutter-fade + explosion sound + state clear. Used on death and on game-over reset. |
| `&2EED`  | `sfx_level_start`          | Long high-pitched fanfare on ch 1 (pitch &FF, duration &0F). |
| `&2EFF`  | `intro_or_scoreboard`      | Branch: if `data_2051 == 6` (fresh game) → ship intro; else → final scoreboard. |
| `&2F09`  | `ship_intro_anim`          | Four-frame slide-in of the player ship from the right edge, columns 5→2. |
| `&2F20..&2F47` | `ship_intro_frame_5..2` | The four ship-arrival animation frames, each blitting a successively wider slice of `lev_player_sprite`. |
| `&2F54`  | `ship_intro_blit_setup`    | wait_one_frame → calc_screen_addr (0, &C8) → sprite_src_hi=&4E. |
| `&2F66`  | `wait_one_frame`           | starfield_update + busy-loop delay + OSBYTE &13. |
| `&30F8`  | `save_score_to_loader`     | Copy score / hi-score / lives to the loader persistence area at `&0CF3..&0CFF` (read back by the BASIC chain). |
| `&3115`  | `restore_score_from_loader`| Reverse of the above — called by `main_init` at game start. |
| `&3170`  | `pause_game`               | Plot `gfx_text_pause` at col &10 row &D0, wait for SPACE, erase with `lev_erase_brush + &80`. |
| `&31B1`  | `draw_final_scoreboard`    | shutter_fade + 4 ship-tween helpers + 6-iteration plot loop — the end-of-game high-score screen. |

### Sound-effect param blocks

Each `LDA #&07 / LDX #lo / LDY #hi / JMP|JSR OSWORD` is paired with
an 8-byte SOUND parameter block, now declared as explicit
`width: 8` data regions:

| Routine            | Params at  | ch    | amp     | pitch | dur  |
|--------------------|------------|-------|---------|-------|------|
| `sfx_fire`         | `&2809`    | &0013 | 2       | &4B   | 1    |
| `sfx_hit_lo`       | `&281A`    | &0012 | 2       | &28   | 1    |
| `sfx_explode` (A)  | `&283B`    | &0010 | &00F1   | 7     | &28  |
| `sfx_explode` (B)  | `&2843`    | &0011 | 3       | &FF   | 1    |
| `sfx_score_tick`   | `&2E8C`    | &0012 | 4       | &64   | 3    |
| `sfx_level_start`  | `&2EF6`    | &0011 | 4       | &FF   | &0F  |

### Tooling

Switched CODE2.cfg from legacy region mode to entries-mode tracing
with explicit entry points. The tracer now correctly carves the
sound-param blocks as data (since `JMP &FFF1` tail-calls exit the
trace) rather than mis-decoding them as nonsense `EQUB &13 BRK ORA`
soup. Same fix applied for the 9-byte starfield-state region split.

Master `Nevryon.6502` ZP equates expanded so per-binary cfgs can
reference any named slot (`zp_player_x`, `zp_player_y`, `zp_test_x`,
`zp_test_y`, …) without forward-reference. Cross-file refs in
`CODE.cfg` and `CODE3.cfg` updated to the new names so all four
binaries continue to build byte-identical.

### Holdouts in CODE2

Some routines still carry their auto-generated `L<addr>` names —
the call patterns aren't clear enough for confident naming:

  - `L28A9`, `L2975`, `L2998`, `L2FF0`, `L3058` — entry points
    from CODE / CODE3 but their purposes need more context tracing.
  - The various `tbl_2BXX` slots (missile state) — named-by-address
    but their meanings (other than X/Y/dir) need more decoding.

### Next

  - Trace the remaining `L<addr>` entry points in CODE2 — most likely
    candidates for naming: the title-screen state machine and the
    bullet-fire path.
  - Inspect the four offset-into-named sprite call sites
    (CODE2 &2C0B, &2D5F, &2D8F, &2FAE) to confirm the
    "wide-text split blit" hypothesis.
  - Label LEVD1 decoration sprite slots so CODE &1C25/&1C36 can
    use explicit names.
  - The 91 B of trailing data at `&49A5-&49FF` after `irq_install`
    — undecoded.

---

## 2026-05-15 — Session 6: CODE3 fully decoded (string table + doubled font)

CODE3 turned out to be the inter-stage / game-over / GET READY!
overlay binary. Five top-level routines, one shared text engine, one
shared OSWORD param block, and a 112-byte ASCII string table at the
tail (the previous disasm decoded those bytes as 6502 instructions,
which is what made the file look obscure).

### Named routines (CODE3 entry points)

| Addr     | Name                       | Purpose |
|----------|----------------------------|---------|
| `&3300`  | `stage_loading_screen`     | "LOADING" / "PLEASE WAIT" then `JMP &30F8` (level-load handoff in CODE2). |
| `&3325`  | `stage_clear_screen`       | "WOW!" / "LEVEL X COMPLETED" / "BONUS X000" with a score roll-up (carries through `score_d0..d3` = `&2A05..&2A02`), then optional "+ EXTRA SHIP!" if the threshold at `&2051` triggers. Returns RTS. |
| `&3432`  | `game_over_or_continue`    | If `&91` (continues left) is non-zero, decrement and run the "PRESS SPACE TO / CONTINUE PLAY!" `10..0` countdown via INKEY (`OSBYTE &81`); times out to game-over. Resets score on continue and re-enters via `stage_loading_screen`. |
| `&3513`  | `get_ready_overlay`        | In-game overlay during the `&E2..&EC` window of the per-frame scroll counter `&80`. Plots `gfx_text_get_ready` (or `lev_erase_brush`) at col 13, row `&C0` via the standard sprite blitter. |
| `&3560`  | `print_doubled_string`     | The shared text renderer all the above call into (see below). |
| `&350A`  | `osword_read_char_def`     | `LDA #&0A / LDX #&01 / LDY #&35 / JMP OSWORD` — wraps OSWORD &0A. The 9 "NOP" bytes immediately preceding it (`&3501..&3509`) are not padding: they're the `chardef_buf` / `chardef_r0..r6` OS-overwritten parameter block. |

### `print_doubled_string` — the text engine

The five routines all funnel through `&3560`, which renders a
zero-page-pointed (`&95/&96`) CR-terminated string at colour `A`,
position `(X,Y)`, with a scanline-stretched two-cell-tall version of
the BBC OS font:

  - VDU 17,A sets foreground colour; VDU 31,X,Y positions the cursor.
  - `(&95/&96)` is patched into a self-modified `LDA &XXXX,X` at
    `&3587` (operand bytes at `&3588/&3589` — now labelled
    `print_str_src_lo / print_str_src_hi`).
  - Per character: `OSWORD &0A` reads the 8-row source font bitmap
    into `chardef_r0..r6`; VDU 23 redefines char 225 as
    `[0, r0, r0|r1, 0, r2, 0, r3, 0]` (top half) and char 226 as
    `[r4, r4, 0, r5, r5|r6, r6, 0, 0]` (bottom half) — i.e. each
    source row gets doubled, with blank rows interleaved for the
    classic "scanline" look. Then `PRINT 225, BACK, DOWN, 226, UP`
    renders the two stretched cells stacked.
  - CR (`&0D`) terminates and jumps to the shared `.L355F` RTS.

### String table — `&3620..&368F`, ten entries

| Addr     | Label                       | Text                  | Used by |
|----------|-----------------------------|-----------------------|---------|
| `&3620`  | `str_loading`               | `"LOADING"`           | `stage_loading_screen` |
| `&3628`  | `str_please_wait`           | `"PLEASE WAIT"`       | `stage_loading_screen` |
| `&3634`  | `str_wow`                   | `"WOW!"`              | `stage_clear_screen` |
| `&3639`  | `str_level_x_completed`     | `"LEVEL X COMPLETED"` | `stage_clear_screen`. The `'X'` at `&363F` is overwritten with the level digit. |
| `&364B`  | `str_bonus_xnnn`            | `"BONUS X000"`        | `stage_clear_screen`. `'X'` at `&3651` becomes the level digit; the `"000"` at `&3652..&3654` is animated to mirror `score_d0..d3` during the roll-up. |
| `&3656`  | `str_extra_ship`            | `"+ EXTRA SHIP!"`     | `stage_clear_screen` (only when `&2051` < 6, i.e. fewer than 6 lives in reserve). |
| `&3664`  | `str_press_space_to`        | `"PRESS SPACE TO"`    | `game_over_or_continue` |
| `&3673`  | `str_continue_play`         | `"CONTINUE PLAY!"`    | `game_over_or_continue` |
| `&3682`  | `str_two_digits`            | `"10"`                | `game_over_or_continue` — first char displays the tens digit, second rolls `'0'..'9'` during the per-second countdown. |
| `&3685`  | `str_credits_nn`            | `"CREDITS:00"`        | `game_over_or_continue` — the trailing `"00"` is the credit count. |

### Disassembler — EQUS / string regions

Added a `kind: "string"` data-region type. The data emitter now
greedily packs printable ASCII into `EQUS "..."` literals, breaks at
the next label, and emits non-printable bytes (e.g. the `&0D`
terminator) as `, &XX` continuations on the same line. This lets the
CODE3 string table roundtrip as readable BeebAsm source instead of
the previous nonsense mis-decoded as opcodes.

Bonus fix in the same pass: `synthesise_regions` was using
`r.kind` to decide forced-data vs forced-code as "data → data, else
code". With the new `string` kind that mis-routed strings into the
code partition. Flipped to "code → code, else data" and made the
forced-region restoration preserve the cfg's original `kind`.

### Shared externs hardening

The build failed with a spurious "Trying to assemble over existing
code" at GRAPHIX once CODE3 started using named ZP labels
(`zp_string_ptr_lo`, `zp_print_idx`, `zp_continues`, `zp_scroll_col`,
`zp_get_ready_erase`) that weren't declared anywhere. BeebAsm's
multi-pass sizing diverged between passes when those symbols stayed
unresolved, leaving a leftover byte at `&3690` that then collided
with the start of `GRAPHIX`. Adding the missing equates to the master
`Nevryon.6502` (plus `data_2051` and `score_d0..d3`) restored a clean
byte-identical build for all four binaries.

Lesson logged: any per-binary cfg that names an out-of-range
address (ZP, hardware, cross-file) **must** have a matching equate
in `Nevryon.6502`, otherwise pass divergence corrupts the layout
without flagging an obvious error.

### Next

  - Inspect the four offset-into-named sprite call sites
    (CODE2 &2C0B, &2D5F, &2D8F, &2FAE) to confirm/refute the
    "wide-text split blit" hypothesis.
  - Label LEVD1 decoration sprite slots so CODE &1C25/&1C36 can
    use explicit names.
  - Trace `&2E83` / `&29E7` / `&2E94` / `&30F8` in CODE2 (called
    from CODE3) — these are the actual level/score state managers.
  - The 91 B of trailing data at `&49A5-&49FF` after `irq_install`
    — undecoded.

---

## 2026-05-15 — Session 5: `&4500..&474F` declared orphaned

Detokenised every BASIC file on the disk (`NEVRYON`, `Loader2`,
`LOADER3`, `Loader4`, `options`, `GmOv`, `Runner`) and grepped each
for the 592-byte range:

  - All `&4500`..`&47FF` hex literals — none.
  - Decimal forms (17664..18431) — none.
  - All `?&` / `!&` / `$&` POKEs — touch only zp, palette_top (`&493F`),
    score area (`&CF3+`), VDU regs, Runner filename buffer (`&7B00`),
    and small VDU char defs at `&7E00`. None hit `&4500..&47FF`.
  - All `FOR..TO` loops — none traverse the range.

Combined with the previous CODE/CODE2/CODE3 scan finding zero code
refs, the block is genuinely **dead**. Renamed `gfx_unknown_table` →
`gfx_orphan_4500` in cfgs/docs. Block content is `00 03 00 03 …`
(MODE 5 pixel pattern `....X` in column-major form), so the bytes
look like leftover sprite data from the build — possibly a cut
graphic that the linker kept emitting.

Manifest confirms only GRAPHIX (`&3680..&4A00`) lands in that range.
LEVD1 loads to `&4A00` (Loader2 forces this via explicit `LOAD x.LEVD1 4A00`
in line 1030, overriding the `&6000` catalog claim on 3/4.LEVD1), so
no in-game file ever overwrites these bytes either.

### Next

  - Inspect the four offset-into-named sprite call sites
    (CODE2 &2C0B, &2D5F, &2D8F, &2FAE) to confirm/refute the
    "wide-text split blit" hypothesis.
  - Label LEVD1 decoration sprite slots so CODE &1C25/&1C36 can
    use explicit names.
  - The 91 B of trailing data at `&49A5-&49FF` after `irq_install`
    — undecoded.

---

## 2026-05-15 — Session 4: unified build + gfx_ prefix + sprite-source overrides

### Starfield engine identified

The 183-byte data block at `&3041-&30F7` in CODE2 (which the legacy
disasm was decoding as nonsense instructions) is the **starfield
state** — three parallel 61-byte arrays:

  - `starfield_pos_lo` (`&3041..&307D`) — per-star screen-address LO byte
  - `starfield_pos_hi` (`&307E..&30BA`) — per-star screen-address HI byte
    (range &5E..&6C maps to playfield char-rows 6..16)
  - `starfield_type`   (`&30BB..&30F7`) — per-star type flag (&03 slow / &02 fast)

Loop bound is `CPX #&3C` so 60 stars are active; the 61st slot in
each array is unused padding. The on-disk bytes are the initial
positions; the engine mutates them in place every frame.

Two access sites in CODE:

  - `starfield_update` (`&1309`) — per-frame: read pos → erase →
    `SBC #&08` to move left → on underflow decrement hi, on hi == &5C
    reset to &6B (wrap from left edge back to row 16 on the right).
    Called from `&127B` (in-game), plus seven CODE2 sites where stars
    keep moving even with game logic paused (get-ready, game-over,
    inter-stage screens).
  - `starfield_init` (`&2656`) — one-shot at level start: walks the
    arrays and writes the per-type pixel byte (`&20` slow / `&02` fast)
    to each starting position. Called from CODE `&126C` when the
    scroll counter `&80` hits `&F0`.

CODE2.6502 dropped from 1349 → 1229 lines once the data was carved.

Also: `L284C` (the rotor-shutter fade routine in CODE2 that runs on
inter-stage transitions) renamed to `shutter_fade` for clarity.

### Build system

Renamed `disasm/*.beebasm` → `disasm/*.6502`. New master
`disasm/Nevryon.6502` declares the shared externs (OS, ZP, IRQ
vectors, hardware-VIA regs) once and `INCLUDE`s each per-binary file
in order, with `SAVE` between `CODE3` and `GRAPHIX` (and a `CLEAR`)
because they overlap at `&3680..&368F` (GRAPHIX is loaded last in
the real boot chain, so its bytes win in memory after loading; we
SAVE CODE3 first so we capture its true on-disk contents).

`build.sh` / `build.bat` wrap BeebAsm and verify byte-identity for
all four binaries against `extracted/$.CODE` etc. — all four
currently rebuild byte-identical.

### Disasm tool changes

- `emit_externs: false` cfg flag suppresses the inline extern block
  in each per-binary `.6502` (the master declares them once).
- Externs split at emit time: **in-range** (mid-instruction equates
  like `sprite_src_lo = &1194` that fall inside the binary) are
  always emitted in the per-binary file; **out-of-range** (OS / HW /
  cross-file refs) are gated by `emit_externs`.
- `immediate_overrides` keyed by the PC of an `LDA #imm` instruction
  to substitute a BeebAsm expression (e.g. `LO(gfx_pickup_yellow)`)
  for the raw byte. Mechanics already existed — now actually used
  at scale.
- Cross-file refs use the auto-generated `LXXXX` label naming
  (defined in the target file), replacing the previous `code2_*` /
  `code3_*` alias scheme. Per-binary cfgs now list the cross-file
  entry addresses in their `labels` block so the included file
  actually defines the symbol.

### gfx_ prefix + sprite-source overrides

All 85 GRAPHIX sprite-atlas labels (sprites + pads + the still-
unknown table) gained a `gfx_` prefix. IRQ-handler / palette labels
at `&4900+` kept their existing names. `docs/file_layout.md` and
`render_graphix_sprites.py` updated.

Scanned CODE / CODE2 / CODE3 for the canonical
`LDA #lo ; STA &1194 ; LDA #hi ; STA &1195` self-modified sprite-
source pattern. **69 sites** total (28 in CODE, 38 in CODE2, 3 in
CODE3). Generated immediate_overrides so each pair renders as
`LDA #LO(gfx_xxx) ; … ; LDA #HI(gfx_xxx)` in the .6502 output.

Two new master externs were needed:

  - `lev_player_sprite = &4E80` — player ship in LEVD1 (drawn at
    `&1483`, plus three sites in CODE2 — see CODE2.cfg overrides).
  - `lev_erase_brush = &7D00` — the LEVD2 zero region; the engine
    touches it at `+&80`, `+&B0`, `+&100`, `+&102` as the universal
    erase brush.

### Inexact references — to revisit

Four sites target a sprite address that's *inside* a named sprite
rather than its base. Worth a closer look at what's drawn there:

| Site         | Target | Expression                        | Hypothesis                                                          |
|--------------|--------|-----------------------------------|---------------------------------------------------------------------|
| CODE2 &2C0B  | &4180  | `gfx_text_get_ready + &80`        | 2nd half of GET READY! (16 cols → drawn as two 8-col blits)         |
| CODE2 &2D5F  | &3FE0  | `gfx_text_gpr90 + &60`            | 2nd half of GPR'90! (14 cols → 6+8 split)                           |
| CODE2 &2D8F  | &3C60  | `gfx_text_press_space + &A0`      | 2nd half of PRESS SPACE! (20 cols → 10+10 split)                    |
| CODE2 &2FAE  | &3690  | `gfx_muzzle_flash_frame0 + &10`   | reads from column 1 of muzzle_flash — partial-tip plot? unclear     |

First three are likely "split wide text into two narrower blits"
because the sprite blitter's max width per call is ≤16 byte-cols.
The muzzle_flash one is the odd one out — when we trace the caller
context we should figure out why it skips the leftmost column.

### Other holdouts

- **CODE @ &1C25 / &1C36** → &4C20 / &4C68 (both LEVD1). These have
  a split setup (LO byte set in a small subroutine, HI byte set
  later in a different code path with an RTS in between) so the
  scan picks them up with `dist=12`. Left as raw hex for now — they
  point into the LEVD1 decoration sprite bank, which we haven't yet
  named slot-by-slot. Once those slots are labelled, add overrides.
- **`gfx_unknown_table` at &4500..&474F**: a thorough scan
  (`tools/find_sprite_refs.py`) found **zero** code references —
  no direct (`LDA/STA abs`), no indexed (`abs,X/Y`), no indirect
  (`(zp),Y` via any zp pointer set to anywhere in &4400..&47FF).
  Likely either dead data left over from compilation or referenced
  only by the BASIC loaders. Worth a peek at `Loader2` / `LOADER3`
  for `?&XXXX` POKEs into that range, but otherwise it can sit.

### Next

  - Check BASIC loaders for any references to `&4500..&474F`.
  - Inspect the four offset-into-named sprite call sites listed
    above to confirm the hypotheses (and maybe carve `text_get_ready`
    into two distinct half-labels if that's what the code reads).
  - Label LEVD1 decoration sprite slots so the &1C25/&1C36 sites
    can become explicit too.
  - The 91 B of trailing data at `&49A5-&49FF` after `irq_install`
    — likely small LUTs, not yet decoded.

---

## 2026-05-15 — Session 3: GRAPHIX sprite catalog

Carved the entire shared sprite atlas at `&3680-&48FF` into named
sub-ranges. Method: progressive probes — render the whole region at
multiple candidate column heights with column / address tickmarks,
then iterate with the user on what each block actually is.

New sprites identified this session:

  - **Ball-chomp animation** at `&3860-&38EF` — 6 frames of 8×12 px
    (24 B each). Was previously mis-labelled `sprite_helix` 6×16 at
    `&3860`. The Pac-Man-style mouth open/close cycle is unmistakable
    once rendered at H=12.
  - **Enemy saucer animation** at `&3900-&3A1F` — 3 frames of 12×24 px
    (72 B each), at `&3900` / `&3960` / `&39C0`, with 24-byte blank
    columns separating them (and a trailing blank at `&3A08`). The
    16-byte gap at `&38F0` is alignment pad to push the saucers onto
    the `&3900` page boundary.
  - **Small enemy animation** at `&4858-&48E7` — 2 frames of 12×24 px
    (72 B each) at `&4858` / `&48A0`. Bounded by an 8-byte head pad
    at `&4850` and a 24-byte trailing blank at `&48E8`.

Several other sprites were nailed down (or had their dimensions
corrected) earlier in the same session: 5 missile sprites at 20×8,
`text_pause` at 36×14 (not 8×16), the four pickup colours at 8×16
with 4-pixel blank gaps between, the 8 small icons at `&4800`, the
`bomb` glyph at `&4848`, plus the `unknown_table` block at
`&4500-&474F` (592 B, no code ref yet).

Round-trip via BeebAsm of `GRAPHIX.beebasm` is byte-identical against
the original `extracted/$.GRAPHIX` after all label changes.

The catalog now spans the full atlas without unidentified gaps — only
named pad regions (alignment, separators) and the still-mysterious
`unknown_table`.

`docs/file_layout.md` gets the full sprite table; renders of every
sprite are in `graphix/` at 1:1 native resolution (`graphix_<addr>_<name>.png`).

The probe tooling lives in `tools/probe_*.py` — kept for the next
investigation rather than deleted.

### Next

  - Trace what code references `unknown_table` at `&4500`. The
    disassembler should already have flagged any indexed loads against
    it; if none, it may be the *destination* of data copies rather
    than read from code.
  - The 91 B of "trailing data" at `&49A5-&49FF` after `irq_install` —
    likely small LUTs, not yet decoded.

---

## 2026-05-14 — Session 2: maps and LEVD format

### Disassembler — reachability tracing

Added an `entries` field to the cfg. When present, the disassembler
traces code reachability from those addresses (following JMP / JSR /
branches, stopping at RTS / RTI / BRK / JMP-out) and synthesises the
region list. Untraced bytes become EQUB data with auto-labels
`data_XXXX`; absolute-indexed loads (`LDA tbl,X` etc.) into untraced
bytes get a `tbl_XXXX` label so RAM tables are named at first use.

Also added a "dead-stub recovery" heuristic: each gap of unreached
bytes is decoded forward; if the decode terminates cleanly at an
unconditional flow break (RTS / RTI / BRK / JMP into reached code or
back into the same gap), the gap-start is treated as a recovered
entry point. This catches:

  - Lone `JMP main_loop` left after a `JMP &3300` (call-out to
    CODE3).
  - Trampoline routine stubs (`LDA #x; STA sprite_src_lo; LDA #y;
    STA sprite_src_hi; JMP sprite_plot_xy`) called only from CODE2 /
    CODE3 — there are several of these in CODE's `&271D..&2737`
    region.

Also added `immediate_overrides` so a `LDA #&XX` / `LDA #&YY` pair
can render as `LDA #LO(label)` / `LDA #HI(label)` in the output
(used in `irq_install` to clarify that the bytes form a vector
pointing at `irq_palette_split`).

`disasm/CODE.cfg.json` and `disasm/GRAPHIX.cfg.json` now both use
the tracer; declared regions are mostly limited to the LUTs and the
sprite atlas. The CODE disassembly is down to ~9 `data_XXXX` blocks
(all genuine in-code state tables / padding), and GRAPHIX to 2.

### Per-level palettes — solved (mechanism + tables + override code)

User confirmed each scenario uses a different MODE 5 palette and
that the palette source must be the IRQ split routine. Both the
IRQ side and the per-scenario override side are now decoded.

Rendering mechanism:

  - `$.GRAPHIX` at file offset `0x1280` (CPU `&4900`) is the
    `irq_palette_split` IRQ handler. On a vsync IRQ it walks
    `palette_top` (`&493F`, 12 bytes) and pours them straight into
    the Video ULA palette latch (`&FE21`). On a User VIA T1 timer
    IRQ (set up by the same handler for mid-frame), it walks
    `palette_bottom` (`&494F`, 12 bytes) and writes those too —
    that's the screen split.
  - `irq_install` at `&497E` hooks IRQ1V (`&0204`/`&0205`) to
    `&4900` and saves the prior vector at zp `&64`/`&65`. Loader2
    line 1000 calls it via `CALL&497E`.
  - The IRQ only writes 12 entries per band (not 16) — the last 4
    bytes of each table are present but never reach `&FE21`. In
    MODE 5 only ULA entries 0, 3, 12, 15 are actually displayed
    (the BBC's "interleaved" 4-color bit-replication), so the 12
    writes cover entries 0, 1, 4, 5, 2, 3, 6, 7, 8, 9, 12, 13. The
    "white" at entry 15 is set once by Loader2's `VDU 19,3,7;` and
    never overridden.

Per-scenario palette override (Loader2 lines 940-970, defs at
1130-1200):

  - Loader2 reads start-level `L% = ?&9D` and dispatches one of
    four PROCs.
  - `PROCLV12` (L%=1,2): no-op, keeps the lev1 palette already
    shipped in GRAPHIX at `&493F`.
  - `PROCL34` (L%=3,4): `RESTORE 1160: FOR T%=0 TO 15: READ T%?&493F: NEXT`
    pokes 16 bytes from `DATA 7,23,71,87,35,51,99,115,129,145,193,209,160,176,224,240` into `&493F`.
  - `PROCL56` (L%=5,6): same loop from `DATA 7,23,71,87,38,54,102,118,133,149,197,213,160,176,224,240`.
  - `PROCL78` (L%=7,8): same loop from `DATA 7,23,71,87,38,54,102,118,130,146,194,210,160,176,224,240`.

(Note: my earlier round of searches missed these because the BASIC
DATA values are stored as ASCII digit-strings, not raw bytes, so
`grep`-ing for the expected hex bytes turned up nothing. The PROC
defs were also outside the line range I'd been scanning. Lesson
logged.)

The MODE 5 pixel→latch-entry mapping is the BBC's "interleaved" form:
`pixel V → entry [0, 3, 12, 15][V]`. With that, each scenario's
palette decodes cleanly (entries 0 and 15 are constant black/white;
entries 3 and 12 carry the scenario primary/secondary):

| Scenario | Pixel 0 | Pixel 1 | Pixel 2 | Pixel 3 |
|----------|---------|---------|---------|---------|
| 1        | black   | red     | yellow  | white   |
| 2        | black   | blue    | cyan    | white   |
| 3        | black   | red     | green   | white   |
| 4        | black   | red     | magenta | white   |

All four match the user's stated colour schemes exactly.
`render_screen.NEVRYON_LEVEL_PALETTES` carries all four, and
`palette_for_level(n)` is the public selector. `render_map.py`,
`render_level_summary.py` and `extract_enemies.py` all accept a
`--level` argument and pick the right palette.

Disassembly state: `disasm/GRAPHIX.beebasm` (+ `.cfg.json`) now
covers the IRQ handler and both palette tables. The `data` regions
in GRAPHIX still need to be carved up further (the sprite atlas is
not yet decoded into named ranges).

### Cleanup pass on `work/`

Pruned `work/` from 84 stale iteration files to 20 canonical PNGs:

  - `map_lev{1-4}.png` — full playfield map (160 px tall, mirrored
    ceiling + gap + floor) using each scenario's palette
  - `enemies_lev{1-4}.png` — enemy ptr-table grid per scenario
  - `summary_lev{1-4}.png` (+ `_preview.png` 2x) — full LEVD2/LEVD3
    overlay with sprites at decoded Y rows and v-flip
  - `opsc_mode2.png`, `scr_mode1.png`, `scorebd_native.png`,
    `welldone_mode1.png` — preserved loader-screen renders (these
    use `NEVRYON_LOADER_PALETTE`).

Removed: all `graphix_*`, `levd*_tiles`, `levd*_levd3_tiles`,
`map_lev*_a/b`, `ship_lev*`, `sprite_test*`, `scorebd_w*` width-
scan iterations, the wrong-mode `opsc_mode1*`/`opsc_mode5`/`scr_mode5`
renders, and old debug crops.

### Map render: ceiling mirror, gap, palette fix

User shared an in-emulator screenshot of the start of level 1 showing
the actual game in MODE 5. Several corrections fell out:

  1. **In-game palette is BBC default 4-colour** — black / red /
     YELLOW / white. `Loader2` line 990 sets logical 2 to physical 6
     (cyan), but the game CODE overrides this back to default before
     gameplay starts. (Found several `LDA #&13` patterns in
     `$.CODE2` consistent with VDU 19 calls — likely the override.)
     Renamed the old palette to `NEVRYON_LOADER_PALETTE` and made
     `NEVRYON_GAME_PALETTE` use yellow.

  2. **Upper tile is vertically mirrored**. Tile draw routine at
     `L127B` clears `zp_sprite_dir_flag` (=0) before plotting upper,
     which makes `sprite_plot_inner` start its column index at
     `height-1` and decrement — i.e. read the column-major source
     bytes in reverse, producing a vertical flip. The lower tile uses
     `dir_flag = 1` (normal forward read).

  3. **Upper at screen rows 0-3, lower at rows 16-19** — the call
     `calc_screen_addr` with `Y=&FF` resolves to char-row 0 and
     `Y=&7F` to char-row 16. That leaves a 12-char-row (96 px) gap
     in the middle of the playfield, which is where the player ship,
     enemies, force-fields and starfield all share space.

`render_map.py` now has a `playfield=True` mode (the default) that
emits a full 160-px-tall strip with the mirror, gap, and correct row
positions. The legacy `playfield=False` compact mode is retained for
inspecting raw tile sources.

`render_level_summary.py` has been rewritten to stack two 160-px
strips (LEVD2 over LEVD3) and to draw each spawned object at its
*actual* Y row in the playfield gap (derived from attribute bits 5-6
→ char rows 4/8/12/16). Force fields render as yellow-noise vertical
strips at the correct Y. Mirror-flag spawns are horizontally flipped
on display.

### 528-byte mystery block — solved

The "528 bytes at LEVD2 offset `&880`-`&A8F`" turns out to be two
unrelated regions:

| File off | Mem addr | Size | Contents |
|----------|----------|------|----------|
| `&880`-`&8FF` | `&7C00`-`&7C7F` | 128 | **Enemy sprite slot 25** (4×32 col-major) — per-level shootable item, intact frame |
| `&900`-`&97F` | `&7C80`-`&7CFF` | 128 | **Enemy sprite slot 26** (4×32 col-major) — per-level shootable item, damaged frame |
| `&980`-`&A8F` | `&7D00`-`&7E0F` | 272 | **All zeros** — blank/erase sprite region |

Confirmed via:
  1. Enemy ptr table `&7A80/&7AC0` slot 25 = `&7C00`, slot 26 = `&7C80`
     in every LEVD2 (lev 1-4 all agree).
  2. Dumped `&7D00`-`&7E0F` for all four files — every byte is zero.
  3. Rendered slots 25/26 as 4×32 sprites: they're clearly two
     animation frames of each level's signature shootable item
     (Lev 1: horseshoe portal, Lev 2: white egg, Lev 3: figure-8
     "snowman", Lev 4: organic biomech blob; in each case slot 26 is
     the "broken/damaged" frame of slot 25).

The zero region is reached by name in the code via `&7D80` (the default
`sprite_src`/`zp_sprite_src_lo`/`hi` init in `L1F8E`) and `&7E02`
(small effect erase). Plotting any W×H sprite from a zero source just
writes color-0 (background) — i.e. it ERASES a screen rectangle. Used
for: erasing destroyed enemies (4×24 from `&7D80`), erasing force
fields (2×32 from `&7D80`), erasing bullets (3×2 from `&7E02`).

### Force-field discriminator — confirmed

Traced the spawn/dispatch chain in `$.CODE`:

  - `spawn_check_step` (L208A) reads `&7B00[&7B]`, matches against
    `&80` (current scroll col); if a hit, takes a free slot from `&7C`
    and decodes the attribute byte at `&7B80[X]`:

    | Bits | Field   | Meaning |
    |------|---------|---------|
    | 0-4  | type    | 0..31 — dispatched by `enemy_type_dispatch` (L22B2) |
    | 5-6  | y_row   | 0=&DF, 1=&BF, 2=&9F, 3=&7F (Y position in MODE 5) |
    | 7    | v_flip  | 0 = normal, 1 = **vertical flip** — pipes through `&206E,X = ~bit7` → `zp_sprite_dir_flag` in the enemy plot (`L216E` lines 2213-2214) |

The "mirror" framing in earlier sessions was wrong — bit 7 toggles
`zp_sprite_dir_flag`, which is a vertical flip (the inner sprite loop
reads the column-major bytes back-to-front). This is used to pair
ceiling-hanging and floor-rising decoration sprites: e.g. lev1's arch
halves at slots 13/14 are placed at col 11-12 with v_flip=1 at y_row=0
(hanging from ceiling) and v_flip=0 at y_row=2 (rising from floor),
using the *same* sprite data both times.

  - The type field stored at `&2065,X` controls behavior dispatch:

    | type | Action |
    |------|--------|
    | 4, &13 | jump to L22E5 (special multi-shot pattern) |
    | 6    | jump to `&2A20` (handled in CODE2 overlay) |
    | 7    | **force field** — `forcefield_render` (L232C → L234D draws a 2×32 vertical strip whose source is `&80XX`, with `XX` from lfsr_random — i.e. procedural noise read from sideways ROM) |
    | 8    | jump to L2464 (TBD — possibly the rotating boss element) |
    | &10  | high-HP enemy (`&2077,X` = 20 hits) — possibly the level boss |
    | other | default: plot enemy sprite from `&7A80/&7AC0[type]` |

The level summary tool's `(attr & 0x1F) == 7` heuristic for marking
force fields is **correct**. New labels added to `CODE.cfg.json`:
`spawn_check_step`, `enemy_type_dispatch`, `forcefield_render`,
`forcefield_draw_or_erase`, `forcefield_erase`.

### Level summary visualization

`tools/render_level_summary.py` combines everything we've decoded into a
single annotated strip per scenario: 240-column map (16 px × 64 px per
column) with two enemy lanes above (LEVD2 spawn schedule) and below
(LEVD3 spawn schedule) at their actual `&7B00[i]` spawn columns. Yellow
vertical bars mark slots whose `&7B80[i]` attribute resolves to a
force-field (currently keyed on `sprite_idx & 0x1F == 0x07` as a
heuristic — the disasm dispatch at `L22D6` uses a "type" byte we
haven't fully resolved yet).

Output: `work/summary_lev1..4.png` at 3840 × 164 native, and matching
`_preview.png` crops at 2400 × 164. All four read as plausible level
layouts:

  - **Lev 1**: gun-towers and arches above; sphere drones, eggs, and
    tanks below; force fields straddle key choke points.
  - **Lev 2**: pillars and dinosaur-aliens flanking the red rock map.
  - **Lev 3**: rocket emplacements and cannons on cyan/white snowscape;
    sparse spawns matching the open-terrain feel.
  - **Lev 4**: dense biomechanical map with scattered organic enemies.

Next: 528-byte block at `&7C00`-`&7E0F` (LEVD2 offset `&880`-`&A8F`)
— probably the actual force-field position table, since the spawn
attribute byte alone doesn't have enough room to encode FF height/Y
position. Also: properly identify the force-field discriminator (the
`sprite_idx == 7` rule is a guess that happens to fire on plausible
columns; want to verify by tracing `L22D6` properly).

### OPSC corrected to MODE 2

User noted `$.OPSC` is MODE 2 (16-colour, 4 bpp), not MODE 1. Added MODE 2
support to `render_screen.py`: 160 × 256, 80 bytes/scanline, 2 px/byte,
char cell = 32 bytes (4 byte-cols × 8 lines). Re-rendered OPSC — now
shows the full 16-colour opening screen with yellow/red NEVRYON logo,
yellow spaceship, blue alien, green/red enemy, planet/galaxy, and the
icon bar at the bottom.

### Map renderer working

Traced the map-rendering setup at `L13D1` in `$.CODE`:

  - Scroll column index lives at `&80`.
  - For each column, the routine reads two 8-bit tile IDs from parallel
    tables in **LEVD2** (loaded at `&7380`):
      - `&7E10[col]` — LOWER tile id (file offset `&A90`)
      - `&7F10[col]` — UPPER tile id (file offset `&B90`)
    Each table is 240 entries (col index wraps `&F0` → `&00` via the
    explicit `CMP #&F1 / LDA #&F0` at L141E+).
  - Each tile is **16 px wide × 32 px tall**, column-major,
    `4 byte-cols × 32 scanlines = 128 bytes`.
  - Tile catalog is in **LEVD1** at `&4F00` (file offset `&500`); the
    `(tile_id + 1)`-step walk in the disassembly means tile 0 lives at
    `&4F00`, tile 1 at `&4F80`, etc. (Tile slot at `&4E80` is reserved
    for the player-ship sprite — 24×22 = 132 bytes — which actually
    overlaps the first 4 bytes of tile 0; presumably the engine doesn't
    rely on those 4 bytes of tile 0.)

`tools/render_map.py` reconstructs each level. Renders of all four LEVD2
maps look exactly like what the scenario descriptions promise:

  - **Lev 1 (Battle Cruiser)**: cyan/red metallic walls, geometric
    towers, doorways — clearly the interior of a starship.
  - **Lev 2 (Asteroid Base)**: red rock surfaces over a starfield, with
    blue gun emplacements and crystal "eggs".
  - **Lev 3 (Planet Surface/Caves)**: cyan/white snowy mountains with
    red gun turrets and what looks like a tank/transport in the middle.
  - **Lev 4 (Alien Beast)**: dense organic biomechanical patterns —
    the inside of the giant alien.

### LEVD3 layout — solved

`LEVD3` for scenarios 1-3 is **2176 bytes = `&880`** — *exactly the
size of LEVD2's lower-memory region* (`&7380`-`&7BFF`). It overwrites
just that lower half. Everything `&7C00`+ — including the map tile
tables at `&7E10`/`&7F10` — stays as LEVD2 left it. So the "second
map" in scenarios 1-3 *uses the same scenery layout*; what changes is
**enemy waves + sprite catalog**.

`4.LEVD3` is **3200 bytes**, the same as LEVD2 — replaces the full
region. But its tile tables turn out to be **byte-identical to
4.LEVD2's** (240/240 matches in both upper and lower). So even level
4's second half uses the same map geometry; only the enemy data
changes.

### Enemy sprite/pointer/spawn tables (decoded)

In LEVD2 (loaded at `&7380`):

| File off | Mem addr | Bytes | Contents |
|----------|----------|-------|----------|
| `&000`-`&6FF` | `&7380`-`&7A7F` | 1792 | **Enemy sprite graphics** (column-major; pointers below resolve here for in-LEVD2 sprites) |
| `&700`-`&73F` | `&7A80`-`&7ABF` | 64 | Enemy sprite ptr LOW (64 slots) |
| `&740`-`&77F` | `&7AC0`-`&7AFF` | 64 | Enemy sprite ptr HIGH (paired with LOW) |
| `&780`-`&7FF` | `&7B00`-`&7B7F` | 128 | **Enemy spawn-column schedule** (sorted; `&FF` = terminator) |
| `&800`-`&87F` | `&7B80`-`&7BFF` | 128 | **Enemy attribute byte** per spawn — bits 0-4 = type (→ `enemy_type_dispatch`), bits 5-6 = Y row, bit 7 = mirror |
| `&880`-`&8FF` | `&7C00`-`&7C7F` | 128 | **Enemy sprite slot 25** (4×32 col-major) — level's shootable item, intact frame |
| `&900`-`&97F` | `&7C80`-`&7CFF` | 128 | **Enemy sprite slot 26** (4×32 col-major) — level's shootable item, damaged frame |
| `&980`-`&A8F` | `&7D00`-`&7E0F` | 272 | **Zero-fill (erase brush)** — accessed via `&7D80`/`&7E02` for erasing screen rects |
| `&A90`-`&B7F` | `&7E10`-`&7EFF` | 240 | Map LOWER tile id per column |
| `&B80`-`&B8F` | `&7F00`-`&7F0F` | 16 | Gap/pad |
| `&B90`-`&C7F` | `&7F10`-`&7FFF` | 240 | Map UPPER tile id per column |

Sprite pointer table entries point into **three regions**:

  - `&73__`-`&7A__` (LEVD2 itself) — level-specific enemy sprites
  - `&3700`-`&3780` (GRAPHIX, file offset `&80`-`&100`) — **shared
    enemy sprites across all levels** (small generic enemies)
  - `&4A__`-`&5__` (LEVD1) — some enemies use level scenery palette
  - `&7C__`-`&7D__` (LEVD2 upper region, before the map tables) —
    occasional larger enemy

`tools/extract_enemies.py` follows the table back to whichever file
holds the bytes and renders the full enemy catalog per level. Results
look like the genuine enemies described in the manual:

  - **Lev 1 (Battle Cruiser)**: gun-towers, sphere drones, tank
    bodies, eye-shaped drones, arches, portal rings.
  - **Lev 2 (Asteroid Base)**: dinosaur-like aliens (!), pillars,
    cannon emplacements, crystal eggs, crescent moons.
  - **Lev 3 (Planet/Caves)**: red lanced ships, anti-aircraft cannons,
    organic blobs, spider-walkers.
  - **Lev 4 (Alien Beast)**: TBD (haven't rendered yet).

### Disasm references locked in

In CODE.beebasm:
  - `L13D1` — main per-frame routine: reads tile tables, advances
    sprite ptrs, scrolls, runs game iteration ×4 per frame.
  - `L208A` — enemy spawn checker: matches `&80` (scroll col) against
    `&7B00[&7B]`; on hit, populates active-enemy slots.
  - `L21BC` onwards — enemy plot routine: reads `&7A80[X]` / `&7AC0[X]`
    for sprite source, plots at 4×32 dims.
  - `L1F8E` — level init: zeros most state, sets player pos
    `&81=5, &82=&C8`, scroll counter `&80=0`, sprite pointers
    initialised to `&7D80` (= LEVD2 offset `&A00`, the unknown tail
    area).

### Tooling additions

```
tools/extract_enemies.py    # follow LEVD2 ptr tables → render enemy
                             # grid per level, regardless of which file
                             # the actual sprite bytes live in
```

### Next

1. Find force-field renderer (4 callers of `lfsr_random` in CODE).
2. Decode the 528-byte block at `&7C00`-`&7E0F` (LEVD2 offset
   `&880`-`&A8F`) — probably force-field positions / per-column flags
   (shootable items / pickups). Force fields are procedural so the
   table likely just gives "where to draw a vertical strip" rather
   than the strip contents themselves.
3. Render LEVD3-overlay enemies (same tool, just substitute LEVD3 in
   for LEVD2 when rebuilding the table). Should reveal the
   *second-wave* enemy lineup.
4. Annotate CODE2.beebasm with the sound queue routine at the top.

### Tooling additions

```
tools/render_map.py          # LEVD1 tiles + LEVD2/LEVD3 column tables
                             # → full level-strip PNG (3840×64 per map)
```

### Next

1. Decode LEVD3's map-table position (the second map per scenario).
2. Identify what occupies LEVD2 offsets `0`..`0xA8F` (2704 bytes before
   the tile tables). Hypotheses: enemy spawn schedule, force-field
   positions, more sprite data, scrolling-speed-per-column.
3. Look at LEVD2 references `&7A95-&7A9A` / `&7AD5-&7ADA` —
   the disasm pattern at lines 1828+ uses these as a sprite-source
   pointer table (lo/hi pair at +&40). That table addresses sprites
   at `&4Exx` (LEVD1 catalog) — so this is the **per-level decoration
   sprite list**.
4. Find the force-field renderer (calls to `lfsr_random` at lines
   908/917/1341/2458 in CODE).
5. Annotate CODE2 / CODE3 with regions.

---

## 2026-05-14 — Session 1, part 4: PAYOFF — player ship & GRAPHIX text decoded

### Major fix: catalog parser was wrong (byte-6 packing)

While trying to render the player ship from `1.LEVD1` I noticed the file
content was 92% ASCII text (lines of NEVRYON.BAS instructions). The user
flagged this — in an emulator `1.LEVD1` is entirely binary. The
discrepancy turned out to be a **byte-6 packing bug** in
`tools/dfs_extract.py`. Inspecting raw catalog bytes (and cross-checking
sector content against what the disassembler expected at known load
addresses) showed this disk uses Watford / 1770-DFS byte 6 encoding, not
Acorn DFS:

```
Acorn   : bits 0-1=load_hi, 2-3=length_hi, 4-5=exec_hi, 6-7=start_hi
Watford : bits 0-1=start_hi, 2-3=load_hi,   4-5=length_hi, 6-7=exec_hi
```

Concrete evidence: `$.CODE2` byte-6=0x01.
  - Acorn interpretation → start sector 15. Bytes at sector 15 are BBC
    BASIC tokens (continuation of `$.NEVRYON`).
  - Watford interpretation → start sector 271. Bytes at sector 271 are
    `A9 07 A2 09 A0 28 4C F1 FF` = `LDA #&07 / LDX #&09 / LDY #&28 / JMP OSWORD`
    — a proper 6502 entry point at the catalog's claimed load address
    `&2800`.

After fixing the parser, every catalog entry now lays out sequentially
on disk with no overlaps. The 12 LEVD files and CODE2/CODE3/GmOv all had
incorrect content before; now they're correct. I removed the bad
extractions and made `extracted/` canonical.

### Player ship sprite extracted

With the corrected `1.LEVD1` I re-ran the sprite renderer at the offset
the disassembly pointed to (offset `0x480` = `&4E80` in memory; CPU code
at `L1478` sets sprite source to `&4E80`, dims X=6 byte-cols, Y=22
scanlines). It rendered the **Cavern Fighter** — a red/cyan side-on
spaceship. Identical bytes at the same offset in 2/3/4.LEVD1, so every
LEVD1 includes the player ship pre-baked.

The full sprite format is now confirmed:
  - **Column-major**: bytes 0..H-1 = column 0, H..2H-1 = column 1, ...
  - **Byte-column** = 4 MODE-5 pixels wide × `H` scanlines tall, where
    `H` = sprite-height-in-scanlines.
  - Sprite size = W × H bytes total.

Engine entry points in `$.CODE`:
  - `L1141` — LFSR random number generator (NOT a sprite routine; my
    earlier guess was wrong).
  - `L116F` — sprite plot, hard-coded width=1 byte-col, height=32.
    Falls into L1173.
  - `L1173` — sprite plot, parameterised by X=width-cols, Y=height-px.
  - `L1184` — inner loop. Reads `$76/$77`=screen dest, self-modifying
    `LDA $XXXX,X` reads source via `L1194/L1195`. Writes via
    `STA ($70),Y`.
  - `L1236` — `calc_screen_addr`: X=char-col, Y=logical-Y → `$76/$77`.
  - `L1209/L121F` — MODE 5 char-row low/high byte LUTs. Confirmed:
    base = `&5800`, stride = `&140`, exact match to data.

Zero-page assignments confirmed:
  - `$70/$71` — screen scratch ptr (char-col base, advanced +320 per row)
  - `$74` — sprite cols remaining
  - `$75` — sprite height
  - `$76/$77` — destination screen addr
  - `$78` — sprite end-index within current column
  - `$79` — direction / mode flag (1 = forward read; 0 = reverse)
  - `$8D/$8E` — secondary sprite source ptr (zero-page)
  - `$9D` — current level number (1..8)
  - `$9E` — sound option, `$9F` — joystick option

### GRAPHIX layout

Rendering `$.GRAPHIX` as a grid of 16-pixel × 16-scanline column-major
sprites (4 byte-cols × 16 scanlines = 64 bytes/sprite) makes the
contents legible:

  - Small particle/projectile sprites in the first few entries.
  - **Bitmap font** of digits 0-9 and an alphabet — used by the
    score/scoreboard and status messages.
  - Pre-rendered status strings: `"PRESS SPACE"`, `"GPR '90"`
    (Graeme Richardson '90), `"GET READY GAME"`, `"OUR FILE"` (?),
    `"LAST PICK..."`, plus what look like alien/scenery sprites at the
    tail end.

So GRAPHIX = font + small constant sprites + status banners. It is not
the per-level scenery; that lives in LEVD1/LEVD2/LEVD3.

### BeebAsm-format disassembler

User asked for BeebAsm output instead of da65. Built `tools/disasm6502.py`
— a from-scratch 6502 → BeebAsm-syntax disassembler with:
  - Annotated region config (`disasm/CODE.cfg.json`) for code/data
    boundaries, labels, comments.
  - Auto-generated `L<addr>` labels for branch/JSR/JMP targets in code
    regions.
  - `EQUB` / `EQUW` for data; `&hex` literals throughout.
  - OS extern-label support (`OSWRCH` = `&FFEE`, etc.).
  - Self-modifying-code aware (annotates the patched bytes via the
    config).

Output: `disasm/CODE.beebasm` (3042 lines), plus CODE2/CODE3 unannotated.

### Tooling artefacts so far

```
tools/dfs_extract.py        DFS catalog parser (Watford-DFS variant)
tools/bbcbasic_detoken.py   BBC BASIC II/IV detokeniser (skips junk preamble)
tools/render_screen.py      MODE 1 / MODE 5 raw bitmap → PNG
tools/render_strip.py       Linear "strip" view of arbitrary bytes
tools/render_sprite.py      Column-major sprite + grid view
tools/disasm6502.py         6502 → BeebAsm disassembler
disasm/CODE.cfg.json        Annotation config for $.CODE
disasm/CODE.beebasm         Annotated disassembly (in progress)
disasm/CODE2.beebasm        Unannotated disassembly
disasm/CODE3.beebasm        Unannotated disassembly
work/                       PNG previews (ship_lev1.png is the win-shot)
```

### Next

1. Track down the per-sprite-class table (a record of source/width/height
   tuples) — needed to enumerate every sprite in GRAPHIX automatically.
2. Disassemble CODE2 (with annotation config); it starts with `LDA #&07,
   LDX #&09, LDY #&28, JMP OSWORD` — a sound queue at the top, so
   CODE2 likely contains sound effect tables + auxiliary routines.
3. Decode LEVD1 layout — at offset `0x480` we have the player ship
   (`&4E80`). The rest of LEVD1 (3584 bytes total) must be level
   tilemap and scenery sprites; LEVD2/LEVD3 likely the map proper.
4. Build map renderer once tilemap format is decoded.

---

## 2026-05-14 — Session 1, parts 1-3: setup, BASIC loaders, sprite engine

(See git history for the full unfolding.)

- Downloaded `Nevryon.zip` from stairwaytohell.com (40-track truncated)
  and a full 80-track image from bbcmicro.co.uk
  (`Disc066-NevryonP.ssd`, 204,800 bytes).
- Wrote `tools/dfs_extract.py` (initially with wrong byte-6 encoding —
  fixed later in this session).
- Wrote `tools/bbcbasic_detoken.py`. Detokenised:
  - `$.!BOOT` → `*BASIC / PAGE=&1900 / CHAIN "NEVRYON"`
  - `$.NEVRYON` → game instructions, line 70 chains to `Options`
  - `$.Options` → option screen (skill, speed, start level, colour/mono,
    resolution, volume), `CHAIN "LOADER2"`
  - `$.Loader2` → title screen w/ scenario menu; loads OPSC, ScoreBd,
    GRAPHIX, then LEVD1+LEVD2, then `CHAIN "LOADER3"`
  - `$.Loader3` → loads CODE / CODE2 / CODE3, calls game at `&1100`,
    on level end loads LEVD3 and re-enters, then `CHAIN "LOADER2"` or
    `"GmOv"` (game over)
- Wrote `tools/render_screen.py` and validated against `$.SCR` (MODE 1
  title bitmap with "NEVRYON" logo + "BY GRAEME RICHARDSON 1990 /
  (C) 1990 THE 4TH DIMENSION") and `$.OPSC` (MODE 1 options screen
  with ship/weapon previews) and `$.WELLDON` ("VICTORY" screen).
- Identified MODE 5 screen at `&5800`, playfield rows 0–19 (160 px),
  scoreboard rows 20–21 (16 px), unused-display rows 22–31 act as a
  storage region (`&7380`+) for LEVD2/LEVD3 data.
- Game palette: logical 0=black, 1=red, 2=cyan, 3=white (from VDU 19
  calls in Loader2).
- Identified sprite engine entry points and zero-page register layout
  (see Part 4 entry for the consolidated list).
