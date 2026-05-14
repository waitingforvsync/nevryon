# Nevryon RE Journal

Newest entries at the top.

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
