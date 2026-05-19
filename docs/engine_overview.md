# Nevryon engine overview

A guided tour of how the runtime actually works, from the main
loop down to the per-pixel detail of each NPC type. Reflects the
post-Session-35 understanding of the engine; for the absolute
ground truth read the disassembly itself, but this should let
you locate any routine quickly.

## Contents

* [Per-frame pipeline](#per-frame-pipeline)
* [The two NPC pools — enemies vs hazards](#the-two-npc-pools--enemies-vs-hazards)
* [Hazards](#hazards)
  * [Spawn schedule](#hazard-spawn-schedule)
  * [`hazard_type` state machine](#hazard_type-state-machine)
  * [Animation cycles](#hazard-animation-cycles)
  * [Force-field (type 7)](#force-field-type-7)
  * [Flame (type 8 / 9)](#flame-type-8--9)
  * [NPC bullets (types 4 and &13)](#npc-bullets-types-4-and-13)
  * [Homing missiles (type 6)](#homing-missiles-type-6)
  * [Death animation (types &14..&1C)](#death-animation-types-1414c)
* [Enemies](#enemies)
  * [Periodic spawner](#enemy-periodic-spawner)
  * [Motion patterns (1..6)](#motion-patterns-16)
  * [`enemy_state` state machine](#enemy_state-state-machine)
  * [Enemy bullet firing](#enemy-bullet-firing)
* [Player projectiles](#player-projectiles)
* [Pickups + power-up ladder](#pickups--power-up-ladder)
* [Player state](#player-state)
* [Force-pod (the orbital companion)](#force-pod-the-orbital-companion)
* [Glossary of zero-page state](#glossary-of-zero-page-state)

---

## Per-frame pipeline

Three-level loop, top to bottom:

```
main_loop                                     CODE &1109
 └─ game_step                                 CODE &13D1   ONE TILE COLUMN of progress
     ├─ try_spawn_pickup                      CODE &25AA   pickup milestone check
     ├─ spawn_periodic_enemy                  CODE &1712   enemy-pool spawner
     ├─ spawn_check_step                      CODE &208A   hazard-pool spawner
     ├─ tile_upper_ptr_calc/_advance          CODE &13ED   pre-resolve the new column's tiles
     ├─ tile_lower_ptr_calc/_advance          CODE &1411
     ├─ INC zp_scroll_col                                  advances the map cursor
     └─ play_subframe (×4)                    CODE &143C   each runs:
         ├─ update_hazard_missiles            CODE2 &2AA2
         ├─ draw_score                        CODE2 &29E7
         ├─ force_pod_anim                    CODE2 &28D7   (subject to force_pod_state)
         ├─ frame_delay                       CODE &13BC   (waits for vsync — gates the speed)
         ├─ update_enemies                    CODE &1AEB
         ├─ scroll_step                       (= scroll_playfield + update_hazards)
         ├─ update_pickup                     CODE &2693
         └─ read_input                        CODE &14D9
```

Each `game_step` call advances the map by one tile column (16
horizontal pixels), animated over 4 sub-frames of 4 px each. The
hazard pool moves and animates in `update_hazards` (which
`scroll_step` calls each sub-frame); the enemy pool moves and
animates in `update_enemies`. Both run every sub-frame, so each
slot updates four times per game_step.

`game_step` exits early once `lives_left` reaches 0 → main_loop
JMPs to `game_over_or_continue` (CODE3 &3432).

The map ends at `zp_scroll_col = &F0`. Once it reaches that
value, scrolling stops and the player flies forever in a
"map-end" state until they trigger the stage-clear flag (TBD —
the trigger condition isn't fully understood yet) or die.

---

## The two NPC pools — enemies vs hazards

Nevryon's threats come in two flavours that don't share a state
representation, lifetime model, or rendering path:

| Property | **Enemies** (moving spawned NPCs) | **Hazards** (scrolling destructible scenery) |
|----------|-----------------------------------|----------------------------------------------|
| Slot count | 8 (1..n_enemies; slot 0 unused) | 8 (0..n_hazards-1) |
| Backing arrays | `enemy_x/_y/_state/_pattern_step/_pattern_id` at `&1A55..&1A8A` | `hazard_x/_y/_type/_flip/_hp/_step` at `&2052..&2088` |
| Per-slot key | `enemy_state` byte (state machine via INC) | `hazard_type` byte (state machine via mutation) |
| Movement | Per-frame `(dy, dx)` from a pattern script in GRAPHIX; player-homing for patterns 5/6 | DECs `hazard_x` by 1 per frame; never moves vertically |
| HP model | 2 player-bullet hits → dies (`enemy_state` walks 1→3 or 3→5 or 5→7) | `hazard_hp` counter, DECs on hit; death at 0 |
| Death anim | 3 hit-frames (`enemy_state` &0A..&0C) then erase (&0D) | 8 explosion frames (`hazard_type` &14..&1B) then clear |
| Spawn source | `spawn_periodic_enemy` — time-paced (one per game_step, no map reference); pattern selector cycles 1..6 deterministically. Same on every run of every scenario. | `spawn_check_step` — column-driven schedule from `lev_spawn_col / lev_spawn_attr`. Per-scenario AND per-stage. |
| Per-frame driver | `update_enemies` (CODE &1AEB) | `update_hazards` (CODE &210A) |
| Plays NPC bullets via | `enemy_try_fire_bullet` (random chance) | `hazard_type_dispatch` (deterministic on `hazard_type == 4 / &13`) |

The two pools share **one** NPC bullet pool (`npc_bullet_*`,
7 slots) and **one** projectile pool for homing missiles
(`hazard_missile_*`, 2 slots — only hazards fire these).

---

## Hazards

### Hazard spawn schedule

Hazards are placed at deterministic positions on the map. The
two parallel tables are loaded with `LEVD2` (stage 1) or
`LEVD3` (stage 2):

* `lev_spawn_col` at `&7B00`  — 128 bytes, sorted ascending list
  of scroll-column indices at which a hazard spawns.  `&FF`
  terminates the list.
* `lev_spawn_attr` at `&7B80` — 128 bytes, paired with the above.

Each attr byte packs three fields:

```
bit 7 6 5 4 3 2 1 0
    └─┘ └─┘ └─────┘
     │   │     └─ bits 0..4: hazard_type  (0..31)
     │   └─ bits 5..6: spawn-row 0..3 → Y = &DF / &BF / &9F / &7F
     │                  (4 evenly-spaced lines spanning the playfield gap)
     └─ bit 7: hazard_flip (INVERTED — 0 in attr = upright,
                                       1 in attr = vertical flip)
```

`spawn_check_step` (CODE `&208A`) is called once per `game_step`.
It compares `lev_spawn_col[zp_7B]` against `zp_scroll_col`, and
on match decodes the attr byte into a new slot in the hazard
pool (round-robin via `zp_7C`). Initial slot state:

* `hazard_x = &28`         (one column off-screen-right)
* `hazard_y = &DF / &BF / &9F / &7F`   (from attr bits 5..6)
* `hazard_type` = attr bits 0..4
* `hazard_flip` = attr bit 7 ⊕ 1
* `hazard_hp = &14`   (for type &10)
            ` &06`   (for type &07 and types < 3)
            ` &08`   (otherwise)
* `hazard_step = 4`

On any non-spawning type (3..6 special-cased — TBD documenting
the exact rules) the routine re-enters itself to drain
back-to-back spawns at the same column. This is how a
force-field's paired entries both land at the same scroll
column (see [Force-field](#force-field-type-7)).

The 14 hazard sprites that types 1..14 reference live in
LEVD2 (stage 1) / LEVD3 (stage 2) at `&7380..&7A7F` — see
`levels/<n>/hazard_stage{1,2}_NN.png` for the per-stage
renders. The ptr LUT entries at `&7A80..&7A8D` /
`&7AC0..&7ACD` are byte-identical between LEVD2 and LEVD3 in
every scenario, so slot N points at the same file offset in
both stages; only the sprite content changes.

### `hazard_type` state machine

The full state table — values directly read by
`hazard_type_dispatch` (per-frame action) and
`hazard_anim_advance` (per-frame frame-step):

| Value | Name (`hazard_type_*`) | Per-frame action               | Animation                          |
|------:|------------------------|--------------------------------|------------------------------------|
| `&00` | `_inactive`            | RTS (slot free)                | —                                  |
| `&01` |                        | —                              | INC → 2 → 3 → 1 (3-frame loop)     |
| `&02` |                        | —                              | INC                                |
| `&03` |                        | —                              | INC; type 4 wraps back to 1        |
| `&04` | `_fires_bullet_a`      | `enqueue_npc_bullet`           | Bumped momentarily then wrapped → 1|
| `&05` |                        | RTS                            | No anim                            |
| `&06` | `_fires_missile`       | `spawn_hazard_missile` (CODE2) | No anim                            |
| `&07` | `_forcefield`          | `forcefield_render`            | No anim — this slot IS the force-field |
| `&08` | `_fires_flame`         | `spawn_flame` → mutates to &09 | EOR #1 ↔ &09 (2-state ping-pong)   |
| `&09` | `_flame_idle`          | RTS                            | EOR #1 ↔ &08                       |
| `&0A`-`&0E` |                  | RTS                            | No anim                            |
| `&0F` | `_anim_ping_a`         | RTS                            | → &10                              |
| `&10` | `_anim_ping_b`         | RTS                            | → &0F (2-frame ping-pong)          |
| `&11`-`&13` |                  | RTS                            | No anim                            |
| `&13` | `_fires_bullet_b`      | `enqueue_npc_bullet`           | (overrides the "no anim" — types 4 + &13 share the bullet path) |
| `&14` | `_death_start`         | (death path)                   | INC each anim tick                 |
| `&15`-`&1B` |                  |                                | INC                                |
| `&1C` | `_death_clear`         | Clear slot (hazard_type / _x / _y = 0) | —                          |

The numeric values are referenced by name through
`immediate_overrides` in `disasm/CODE.cfg.json` — see Session 30
in `JOURNAL.md` for the full constant list.

### Hazard animation cycles

The animation phase tick lives in `zp_7F`, which oscillates 3/4
across frames (cycled at the tail of `update_hazards`). The
`update_hazard_slot` body (CODE `&2253`) calls
`hazard_type_dispatch` first (the per-frame ACTION) and then
gates the frame-step on `zp_7F == 4` — so each hazard slot
advances its frame every other frame on average.

`hazard_anim_advance` (CODE `&2267`) dispatches by current
`hazard_type[X]`:

```
type < &04     →  anim_loop_1_to_3   INC type; wrap 4→1
type &08/&09   →  anim_toggle_8_9    EOR #&01 (flame fires every other tick)
type &0F       →  anim_set_type_10   set type = &10
type &10       →  anim_set_type_F    set type = &0F
&04-&07, &0A-&0E, &11-&13 → hazard_anim_done   (RTS — no frame change)
type >= &14    →  hazard_death_step  INC type; clear slot at &1C
```

Because the slot's sprite is selected by
`lev_hazard_ptr_*[hazard_type]`, INCing the type IS advancing
the frame — there's no separate frame counter per slot.

### Force-field (type 7)

The visual is a vertical strip with two caps: hazard 6
(mirrored) at the top, procedural noise in the middle,
hazard 6 (upright) at the bottom. It's built from **two**
spawn entries at the same scroll column:

```
attr1 = &87  →  type=7, row=0, attr-bit-7=1  → hazard_flip=0
attr2 = &47  →  type=7, row=2, attr-bit-7=0  → hazard_flip=1
```

Each slot runs through the standard `update_hazards` pipeline:

1. **Cap plot**: `update_hazards` reads
   `lev_hazard_ptr_*[hazard_type]`. For type 7 this resolves to
   `hazard_06` (the SAME slot in every scenario — see the per-
   stage hazard_06 PNG). The cap is plotted at `(hazard_x,
   hazard_y)`, 4 byte-cols × 32 lines, flipped per
   `hazard_flip`. `hazard_06`'s visible content sits in the
   middle 2 cols of the 4-col stamp (cols 0/3 are nearly empty).
2. **Noise plot**: `hazard_type_dispatch` calls
   `forcefield_render` (CODE `&232C`), which plots a 2 byte-col
   × 32-line strip 32 px away from the cap. Direction depends
   on `hazard_flip`:
   * `hazard_flip == 0`: strip at `hazard_y - &20` (= 32 px
     BELOW the cap in screen-space; recall the Y-bottom origin)
   * `hazard_flip == 1`: strip at `hazard_y + &20` (= 32 px
     ABOVE the cap)
3. Noise content: read from the sideways-ROM page at `&80XX`
   with `XX = lfsr_random` — i.e. it grabs 64 effectively
   random bytes from whatever's paged in at &8000+. That's the
   shimmering visual.

The `forcefield_active` flag (RAM byte at `&2329`) serialises
the noise plot: only the first type-7 slot the engine
encounters per frame actually draws noise. Both slots in a
pair compute the same target Y though — so the visible noise
is at the same position regardless of which slot wins. The
strip is erased at the START of the next frame's
`update_hazards` and redrawn fresh, hence the shimmer.

The render-side schematic in `levels/<n>/map_with_hazards_*.png`
shows the cap mirrored at the top, noise filling the
mid-strip, cap upright at the bottom.

### Flame (type 8 / 9)

A one-shot 32×8-px horizontal flame. Only one in flight at a
time (`flame_state` flag).

* Type 8 hazard slot is the "primed flame": `hazard_type_dispatch`
  calls `spawn_flame` (CODE2 `&2464`).
* `spawn_flame` refuses if `flame_state != 0` (already firing)
  or if `hazard_x < &0C` (firing slot has scrolled too far
  left). On success it mutates the firing slot to type 9
  (`flame_idle`), copies its position into `flame_x` / `flame_y`
  (with a per-`hazard_flip` Y offset), and sets `flame_state = 1`
  to start the 6-frame animation.
* `hazard_anim_advance` toggles `hazard_type` between 8 and 9
  (EOR `#&01`) — so after firing the slot eventually returns to
  type 8 and can re-fire.

The flame projectile itself runs separately from the hazard
pool, with its own state at `flame_x` / `flame_y` /
`flame_state` and 3 frames at `gfx_flame_frame0..2`.

### NPC bullets (types 4 and &13)

`enqueue_npc_bullet` (CODE `&22E5`) is called from
`hazard_type_dispatch` for hazard types `&04` and `&13` (two
different bullet-firing hazards that share the same firing
code). It scans `npc_bullet_x[6..1]` for a `&FF` (free) slot
and on found stores `hazard_x[firer] - 1` and
`hazard_y[firer] - &10` (Y lifted by 16 px to fire from above
the hazard).

If `hazard_x[firer] < &08` the fire is suppressed (the hazard
has nearly scrolled off-screen left — no room left to fly).

The bullet sprite is `npc_bullet_sprite` at `&7E00` (4×2 px
white). It moves 2 px LEFT per frame, erases its own trail
via the 3-byte sprite-pad trick, and self-deactivates when
`npc_bullet_x` drops to 0/1.

The 7-slot `npc_bullet_*` pool is SHARED with the enemy bullet
firing code — enemies fire into the FIRST 4 slots
(`n_enemy_npc_bullets = 4`), hazards can fire into any of the
6 active slots. Slot 0 is initialised to `&FF` but never used.

### Homing missiles (type 6)

`hazard_type_dispatch` calls CODE2's `spawn_hazard_missile`
(`&2A20`) for type 6 hazards. The missile is a vertical 4×6-px
yellow-red rocket that picks a horizontal-homing direction at
spawn time based on the player's X relative to the missile's
position.

Pool: `hazard_missile_x / _y` (2 slots only, hard-coded
LDX #&00 / LDX #&01 loops; no shared state). Per-frame movement
in `step_hazard_missile` (CODE2 `&2AC4`) — homing X plus
forward Y, bounds-checked.

### Death animation (types &14..&1C)

When `check_bullet_hits` (CODE `&1847`) detects a player bullet
hit on an active hazard:

1. DEC `hazard_hp[X]`. On `hazard_hp == 0`, mutate `hazard_type`
   to `hazard_type_death_start` (`&14`) — this starts the death
   anim path.
2. `hazard_anim_advance` then INCs the type each anim tick:
   `&14` → `&15` → ... → `&1B` (8 frames sourced from
   `lev_hazard_ptr_*[&14..&1B]`).
3. On reaching `hazard_type_death_clear` (`&1C`),
   `hazard_death_step` clears the slot completely:
   `hazard_type = 0`, `hazard_x = 0`, `hazard_y = 0`.

`check_player_collisions` (CODE `&198B`) uses the same `&14`
threshold (`hazard_type < &14` → "alive, can damage player").

---

## Enemies

### Enemy periodic spawner

Enemies are **time-paced, not map-positioned**. Unlike the
hazard pool there's no per-column schedule — the same six-
pattern cycle plays on every run of every scenario, only
gated by an end-of-map cutoff.

`spawn_periodic_enemy` (CODE `&1712`) runs once per `game_step`.
It paces on `zp_87` (sub-counter, cycles 0..&0A):

* On the **`zp_87 == &0A`** call: waits for the enemy field to
  fully empty (every slot's `enemy_state == 0`), then advances
  `zp_86` (pattern selector, cycles 1..6 wrapping back to 1),
  pre-loads the per-pattern parameters into zero-page:
  ```
  enemy_pattern_ptr_lo[zp_86] → zp_88   (script ptr LO)
  enemy_pattern_ptr_hi[zp_86] → zp_89   (script ptr HI)
  enemy_pattern_len_lut[zp_86] → enemy_pattern_len
  ```
  Doesn't spawn an enemy this call — just refreshes the
  pattern state.
* On the **other 10 calls** per cycle: INCs `zp_87` and spawns
  one enemy into the first free slot.

So each pattern produces ~10 enemies over ~10 game_step calls
(= ~10 tile columns of progress), then the cycle drains, then
the next pattern starts.

The only `zp_scroll_col` reference in the whole routine is a
hard cutoff at `&F0` (end-of-map) — the routine returns
immediately after that, so no more enemies spawn for the rest
of the level. Otherwise enemy pacing has no relation to where
the player is on the map.

**Design consequence**: the level-design data
(`lev_spawn_col` / `lev_spawn_attr` in LEVD2/3) only describes
hazards. Whatever editor Graeme used in 1990 had to support
hazard placement only; enemy difficulty is identical across all
four scenarios because both the pacing (`spawn_periodic_enemy`
in CODE) and the four pattern scripts (`enemy_pattern_1..4` in
GRAPHIX) are level-agnostic. That's also why the per-stage
`levels/<n>/` directories only ship per-stage hazard renders +
spawn tables; there's no equivalent "stage 1 enemy spawn map"
because the answer is uniformly "just off the right edge, one
per game_step".

Initial enemy slot state per pattern:

| Pattern (`zp_86`) | `enemy_state` | `enemy_y`          | Notes |
|------------------:|:-------------:|--------------------|-------|
| 1..4              | &01 (`_initial_pat14`) | &9A (fixed) | Script-driven motion |
| 5                 | &03 (`_initial_pat5`)  | random in [&97..&D7] | Player-homing |
| 6                 | &05 (`_initial_pat6`)  | random in [&97..&D7] | Straight-at-player |

In all cases `enemy_x = &25` (one column off-screen right).

### Motion patterns (1..6)

The four script tables (patterns 1..4) live in the GRAPHIX
binary at:

| Pattern | Script address | Length |
|--------:|----------------|-------:|
| 1       | `enemy_pattern_1` = &4500 | &78 (= 60 pairs) |
| 2       | `enemy_pattern_2` = &4574 | &9C (= 78 pairs) |
| 3       | `enemy_pattern_3` = &4614 | &60 (= 48 pairs) |
| 4       | `enemy_pattern_4` = &4680 | &D6 (= 107 pairs) |

Each script is a sequence of **`(dy_dir, dx_dir)` byte pairs**.
Per frame, `enemy_select_motion` (CODE `&1B87`, formerly L1B87)
reads the next pair using `enemy_pattern_step[X]` as the
byte-offset into the pointed-at script.

The direction encoding is the `pattern_dir_*` enumeration:

```
pattern_dir_none = &00    no motion on this axis
pattern_dir_pos  = &01    dy: Y += 4 (UP)     /  dx: X += 1 (right)
pattern_dir_neg  = &03    dy: Y -= 4 (DOWN)   /  dx: X -= 1 (left)
                          (any non-0, non-1 value falls through to "negative")
```

Patterns 5 and 6 are special-cased — they don't walk a stored
script:

* **Pattern 5 (homing)**: every frame, picks `dx_dir = neg`
  (constant leftward motion) and `dy_dir = pos / neg` based on
  whether the player is above or below this enemy. Throttled to
  one direction-pick per 4 frames (`zp_7F == 4`).
* **Pattern 6 (straight)**: `dx_dir = neg`, `dy_dir = none` —
  flies straight at the player's altitude on each spawn.

### `enemy_state` state machine

`enemy_state[X]` doubles as the slot's hit-counter and animation
selector. Values 1..7 = alive (different patterns start at
different initial states), 8..9 = transient kill markers,
`&0A`..`&0D` = death-anim frames, `&00` = free.

```
Pattern 1..4 path:    &01 → INC → &02 → INC → &03 (kill)
Pattern 5 path:       &03 → INC → &04 → INC → &05 (kill)
Pattern 6 path:       &05 → INC → &06 → INC → &07 (kill)

On kill: enemy_state := &0A → &0B → &0C → &0D (slot freed)
```

`check_bullet_hits` (CODE `&1847`) drives the alive walk: any
player bullet hit on an enemy slot whose `enemy_state` is in
`[1, enemy_state_invincible_min)` (= 1..8) INCs the state. At
the kill thresholds (3 / 5 / 7) it plays the OSWRCH 7 bell,
INCs `pickup_kill_count`, and mutates `enemy_state` to `&0A`
(`enemy_state_hit_frame_1`).

`enemy_anim_dispatch` (CODE `&1BE3`) selects the sprite per
state:

* `enemy_state` 0..6 → indexes into the parallel
  `enemy_anim_ptr_lo / _hi` LUT (slots 1..4 = `lev_enemy_0..3`
  in LEVD1; slots 5..6 = `gfx_enemy_small_frame0/1` in GRAPHIX)
* `&0A` → `enemy_hit_frame1` (`lev_enemy_hit_1`)
* `&0B` → `enemy_hit_frame2`
* `&0C` → `enemy_hit_frame3`
* `&0D` → `enemy_hit_erase` (`lev_erase_brush + &80`; clears
  `enemy_state` to 0, freeing the slot)

### Enemy bullet firing

`enemy_try_fire_bullet` is called per-frame per-enemy. It uses
`lfsr_random` to pick whether to fire; on success it allocates
a slot in the SHARED `npc_bullet` pool via `npc_bullet_alloc`
(CODE `&1AB6`). Enemies are restricted to the first
`n_enemy_npc_bullets = 4` slots — slots 5..6 are reserved for
hazards.

---

## Player projectiles

* **Player bullets** — 6-slot pool at `player_bullet_x / _y`
  (`&16E6` / `&16ED`). `on_fire_pressed` (CODE `&17B9`) allocates
  one of slots 1..4 (`n_player_fire_slots`) on KEY_FIRE; slots
  5..6 are reserved for the force-pod's twin shot.
  `update_bullets` moves each active slot +2 px right per frame
  and runs `check_bullet_hits` against both NPC pools.
  Sprite: `player_bullet_sprite` at `&7E06` (4×2 px coloured —
  yellow / cyan / green / magenta per scenario).
* **Player missiles** — paired upper/lower, available only after
  the player has collected 7 power-ups (= tier 7,
  `player_missiles_unlocked = 1`). Launch via
  `fire_player_missiles` (CODE `&1577`); per-frame mover is
  `update_player_missiles` (CODE `&15C4`). Sprite is one of
  `gfx_missile_0..4` selected by `player_missile_frame` (5
  frames of vertical animation).
* **Force-pod twin shot** — pulse drawn by the orbital companion
  (see [Force-pod](#force-pod-the-orbital-companion)).

---

## Pickups + power-up ladder

The kill-milestone counter `pickup_kill_count` is INCed by
`check_bullet_hits` at the kill thresholds (state values 3/5/7
for enemies, and any hazard kill via `check_bullet_hits`'s
hazard branch).

`try_spawn_pickup` (CODE `&25AA`) runs once per `game_step` and
triggers when `pickup_kill_count` reaches `&0A`:

* Refuses if `pickup_state != 0` (a pickup is already on-screen)
  or `player_missiles_unlocked == 1` (player is at the cap — no
  more pickups spawn after tier 7).
* On success: stashes `player_y` in `pickup_y`, sets
  `pickup_x = &27` (right edge col 39), `pickup_state = 1`, and
  plays sfx_level_start.

The pickup drifts leftward at 1 px per sub-frame, flashing
through `pickup_state` 1..&0A (which cycles two sprites,
`gfx_pickup_yellow` and `gfx_pickup_red`). On player contact
(`pickup_collected`, CODE `&275F`), the tier ladder fires:

| Tier (`pickup_count` after INC) | Effect |
|---:|--------|
| 1  | `fire_cooldown_reload = 3` (= fast fire) |
| 2  | dead flag (no visible effect) |
| 3  | `pod_attached = 1` (force-pod appears + collides for the player) |
| 4  | dead flag |
| 5  | `force_pod_state = 1` (twin-shot enabled), `zp_8A = 8` (reset fire timer) |
| 6  | dead flag |
| 7  | `player_missiles_unlocked = 1` (paired missiles enabled, no more pickups) |
| 8+ | clamped — no effect |

The "dead flag" tiers (2, 4, 6) ARE written but nothing reads
them. They look like scaffolding for power-ups that were planned
but never wired up; we noted this as a finding in Session 32.

Score-wise, each pickup awards +100 via `add_score_x10` and
plays sfx_level_start. The currently-collected pickup count is
displayed on the status row by `+1` icons.

---

## Player state

* **`player_hp`** at `&2050` — per-life HP. Initialised from
  `zp_9A` (`?&9A`, default 6, configurable via the options BASIC).
  DEC'd in pairs by `lose_a_life` (every other call); when it
  hits 0 the next `lose_a_life` jumps to `death_anim`.
* **`lives_left`** at `&2051` — number of ships REMAINING before
  the current one. Initialised by `restore_score_from_loader`
  from the loader-persistence area (default 3). DEC'd by
  `death_anim` after the explosion plays. `main_loop` checks
  each `game_step`: when it hits 0 → `game_over_or_continue`.
* **`lives_blink_state`** at `&1E46` — 0/1 toggle stepped by
  `lose_a_life`. Used both to swap the lives-icon sprite
  (`gfx_icon_lives` ↔ `gfx_icon_lives_blink`) and to halve the
  rate at which `player_hp` decrements.
* **`zp_player_x / _y`** at `&81` / `&82` — player position. Set
  by `read_input` based on the four direction keys. `init`
  starts the player at `(&05, &C8)`.
* **`pod_anim_frame`** at `&14D8` — force-pod animation frame
  index (1..3). INCed by `move_player_up` (wraps 4→1), DECed by
  `move_player_down` (wraps 0→3). Drives which of
  `gfx_pod_frame0..2` the orbital companion renders.

Player death triggers `death_anim` (CODE `&1E47`): plays
sfx_explode and runs 6 explosion frames at the player's last
position, then DECs `lives_left`, redraws the lives indicator,
and (if any lives remain) plays the GET-READY intro and
re-`init`s.

---

## Force-pod (the orbital companion)

The force-pod is a chomping ball that floats alongside the
player ship after tier-3 pickup unlock. Two distinct subsystems
under the same name:

1. **Attached force-pod** (`pod_attached = 1`, from tier 3): a
   3-frame sprite drawn at `(player_x + 5, player_y + 1)`,
   animated by `draw_player_pod` (CODE `&14B5`). Provides
   collision damage to enemies via `pod_collide_enemy` (CODE
   `&2555`): tests the pod's hitbox each frame; on hit, kills
   the enemy + scores + INCs `pickup_kill_count`.

2. **Floating power-up form** (`force_pod_state = 1`, from
   tier 5): rendered by `force_pod_anim` (CODE2 `&28D7`) as a
   6-frame animated ball at `(force_pod_x, force_pod_y)`. Can be
   collected by the player (proximity collision) or dismissed by
   any keypress. Enables the twin-shot — the player's fire
   button now puts bullets into slots 5..6 of the player_bullet
   pool in addition to 1..4 (see `pod_fire` in CODE2 `&2975`).

The two states aren't mutually exclusive in the data, but
tier 3 unlocks `pod_attached` and tier 5 unlocks
`force_pod_state` — so by the time you've got the twin-shot the
attached pod is also present.

---

## Glossary of zero-page state

The frequently-touched zero-page locations, with where they're
set:

| Addr | Name | Role |
|------|------|------|
| `&64/&65` | `zp_old_irq_vec_lo/_hi` | Saved IRQ1V before `irq_install` patched it |
| `&70/&71` | `zp_screen_ptr_lo/_hi` | Sprite-engine destination pointer |
| `&76/&77` | `zp_dest_x_lo/_hi`     | calc_screen_addr output → sprite_plot_xy input |
| `&7B`     | (lev_spawn cursor)     | Index into `lev_spawn_col` / `lev_spawn_attr` |
| `&7C`     | (hazard round-robin)   | Next hazard slot for spawn_check_step |
| `&7E`     | (npc bullet cooldown)  | Global enemy-fire cooldown |
| `&7F`     | (anim phase)           | Oscillates 3/4 — gates `hazard_anim_advance` (`zp_7F == 4`) |
| `&80`     | `zp_scroll_col`        | Map column cursor (0..&F0 = end-of-map loop) |
| `&81/&82` | `zp_player_x/_y`       | Player ship position |
| `&83/&84` | `zp_test_x/_y`         | Scratch box for collision tests |
| `&86/&87` | (pattern selector / sub-counter) | Used by `spawn_periodic_enemy` |
| `&88/&89` | (active pattern script ptr) | `(zp_88,Y)` is the per-frame motion-script read |
| `&8A`     | (fire cooldown)        | DEC'd per frame in `update_bullets`; refuses fire while != 0 |
| `&9A`     | (player_hp init)       | Per-life HP default (configurable in options) |
| `&9D`     | `zp_level_num`         | Current scenario (set by Runner / Loader) |
| `&9F`     | (zp scratch)           | Various |

See `disasm/Nevryon.6502` for the authoritative list — every
named zp is declared at the top of the master file as
`zp_NN = &NN`.
