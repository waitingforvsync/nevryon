# Nevryon RE Journal

Newest entries at the top.

---

## 2026-05-14 — Session 2: maps and LEVD format

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
    | 7    | mirror  | 0 = no flip, 1 = horizontal mirror |

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
