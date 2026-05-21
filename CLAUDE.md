# Nevryon Reverse-Engineering Project

Reverse-engineering the BBC Micro game **Nevryon** (The Fourth Dimension,
1990) — a MODE 5 sideways-scrolling R-Type clone — with the aim of
recovering sprites and level maps, and (stretch) producing a full BeebAsm
disassembly toward a remake.

The source disk image was downloaded from
<https://stairwaytohell.com/bbc/archive/diskimages/4thDimension/Nevryon.zip>.

## Repository layout

```
README.md                    # public-facing intro; credits Graeme Richardson + The Fourth Dimension
LICENSE                      # MIT for project artefacts (with explicit scope note re: the original game)

4thDimension/Nevryon.ssd     # full 80-track DFS disk image (do not modify)
extracted/                   # files unpacked from the disk image
  _manifest.tsv              # per-file load/exec/length/start-sector
  $.<NAME> / N.<NAME>        # extracted file payloads (dir letter prefix)

tools/                       # Python utilities (DFS, sprite, map decode)
  dfs_extract.py             # parses SSD catalog, extracts files (standard DFS byte-6 packing)
  bbcbasic_detoken.py        # BBC BASIC II/IV detokeniser (handles junk preamble)
  disasm6502.py              # 6502 → BeebAsm disassembler with annotations
  render_screen.py           # MODE 1 / 2 / 5 raw bitmap → PNG
  render_strip.py            # linear strip view of arbitrary bytes
  render_sprite.py           # column-major sprite + grid viewer
  render_graphix_sprites.py  # GRAPHIX atlas renderer
  render_map.py              # LEVD1 tiles + LEVD2/3 column streams → strip
  render_level_summary.py    # composite map + enemies + spawn pins
  render_level.py            # per-level full output: sprite PNGs + maps + spawn tables

disasm/                      # BeebAsm-format reconstruction (byte-identical roundtrip)
  Nevryon.6502               # master — INCLUDEs all four per-binary sources + shared equates
  CODE.6502 + CODE.cfg.json  # annotated disassembly of $.CODE
  CODE2.6502 + CODE2.cfg.json
  CODE3.6502 + CODE3.cfg.json
  GRAPHIX.6502 + GRAPHIX.cfg.json

build/                       # output of build.sh — byte-identical to $.CODE etc.
build.sh / build.bat         # regen disasm sources + invoke BeebAsm + verify byte-identity

levels/1/ levels/2/ ...      # per-scenario reverse-engineered data + visualisations
  explosion_NN.png           # see "Per-level naming convention" below
  enemy_NN.png  enemy_hit_NN.png  player_sprite.png  tile_NN.png
  hazard_stage{1,2}_NN.png   # 14 hazards per stage — DIFFERENT bytes per stage
  map_strip.png              # full 240-col playfield strip (both stages share)
  map_with_spawns_{1,2}.png  # strip + spawn-pin overlay (per stage)
  map_with_hazards_{1,2}.png # strip with actual hazard sprites at spawn positions
  spawn_table_stage{1,2}.md  # decoded spawn schedule per stage
  data/                      # raw 128/240-byte binary dumps
  README.md                  # byte-by-byte memory map + index→sprite

graphix/                     # per-sprite atlas dumps from $.GRAPHIX
work/                        # PNG previews, scratch

docs/
  engine_overview.md         # how Nevryon actually runs — pipeline, NPC pools, state machines, projectiles, pickups
  file_layout.md             # per-file content reference (load addrs, byte maps, routine names)
  memory_map.md              # single-page CPU memory layout (zp, each binary, LEVD data, ...)
CLAUDE.md                    # this file — workflow & conventions
JOURNAL.md                   # running log of discoveries & decisions
```

## Hard-won lessons (read before editing)

### DFS catalog byte-6 packing
Byte 6 of each file's metadata in catalog sector 1 packs the high bits
of load/exec/length/start_sector. The standard DFS packing is:
  - bits 0-1: start-sector bits 9-8
  - bits 2-3: load-address bits 17-16
  - bits 4-5: file-length bits 17-16
  - bits 6-7: exec-address bits 17-16

There is only ONE DFS catalog format — Watford / 1770 / Acorn DFS all
share it for compatibility. The early "Acorn vs Watford" framing in
Session 1 was wrong (see Session 25 correction); the initial
`dfs_extract.py` bug was a mis-packed bit layout, not a separate
format variant. If a freshly-extracted file looks like text where you
expect binary (or vice versa), suspect the bit packing.

### Disassembly target is BeebAsm, not da65
`tools/disasm6502.py` emits BeebAsm syntax (`&hex`, `.label`, `EQUB`,
`ORG`, `\ comment`) in `disasm/<file>.6502`. Goal: a roundtrip-able
source that BeebAsm can re-assemble into the original binary. Drive
it via the annotation JSON (`disasm/<file>.cfg.json`) — add a
region/label/comment any time we identify one, then re-run. Do not
hand-edit `.6502` output.

`disasm/Nevryon.6502` is the **master** — it declares the shared
extern equates (OS, hardware regs, ZP, cross-file refs) once and
`INCLUDE`s each per-binary `.6502` in order, with `SAVE` between
`CODE3.6502` and `GRAPHIX.6502` because those overlap in RAM at
`&3680..&368F`. Per-binary cfgs set `"emit_externs": false` so the
externs aren't duplicated when included. When the disasm tool adds
or removes externs (auto-promoted mid-instruction labels, new
cross-file refs), the master's preamble must be kept in sync.

### Self-modifying code
Several routines patch their own operand bytes at runtime — the
sprite engine's `LDA &XXXX,X` source operand at `L1194/L1195`, and
the playfield's soft-scroll inner loop at `&12BE..&12CB` (four
`LDA/STA` pairs, all 8 operand bytes patched per call).

Convention: declare each self-modified operand byte as an entry in
the cfg's `extern_labels` block (e.g. `"0x12BF":
"scroll_lower_src_lo"`). The disassembler emits these inline,
**directly above** the instruction whose operand they patch, as
`name = * + N` (BeebAsm PC-relative):

```
.scroll_inner_loop
scroll_lower_src_lo = * + 1
scroll_lower_src_hi = * + 2
    LDA &FFFF
scroll_lower_dst_lo = * + 1
scroll_lower_dst_hi = * + 2
    STA &FFFF
```

The runtime placeholder operand value `&FFFF` is intentionally not
auto-promoted to a synthetic label — it renders as the literal hex
so it's clear at a glance that the instruction is patched.



### Numeric notation
- Use BBC-style hex with `&` (e.g. `&3000`, `&7380`) in commentary and Beeb
  contexts. Use `0x` only in Python/JS code.
- Addresses given as 6-digit DFS values (e.g. `&14A00`) are the catalog's
  combined load address with the top-2-bit tube/host hint. The CPU-visible
  address is the low 16 bits (e.g. `&14A00` → load to `&4A00`).
- Sector numbers are 256-byte DFS sectors.

### MODE 5 facts (cheat-sheet)
- Resolution: 160 × 256 logical pixels, 4 colours (2 bits/pixel).
- Screen RAM: `&5800`–`&7FFF` (10 KB). **NOT** `&3000`-`&7FFF` — that's
  MODE 0/1/2. MODE 5's smaller buffer leaves more user RAM available.
- Bytes per scanline: 40. Each byte = 4 pixels.
- Char cell: 8 px wide × 8 lines tall = 16 bytes (2 byte-cols × 8 lines).
- Memory layout per char-row: 20 cells × 16 bytes = 320 bytes contiguous.
  Within a cell, the 8 left-half bytes precede the 8 right-half bytes.
- Pixel bit layout in a byte: 8 bits = 4 pixels.
  Pixel `n` (left-to-right) uses bits `(7-n)` (colour-bit-1) and
  `(3-n)` (colour-bit-0) — BBC's standard interleaved layout.

### Nevryon screen budget (MODE 5)
- Playfield: char rows 0-19 (160 px tall × 160 px wide).
- Scoreboard: rows 20-21 (16 px tall) — loaded from `$.SCOREBD` at `&7100`.
- Rows 22-31 (`&7380`-`&7FFF`): screen RAM, but CRTC trimmed off-display.
  Used as storage for LEVD2/LEVD3 data.

### Per-level palette
Each scenario (1-4) uses a different MODE 5 palette. The mechanism:

  - `irq_palette_split` (GRAPHIX file off `0x1280`, CPU `&4900`) is
    an IRQ handler that writes 12 bytes from `palette_top` (`&493F`)
    to the Video ULA palette latch (`&FE21`) at vsync, and 12 bytes
    from `palette_bottom` (`&494F`) mid-frame on a User VIA T1 timer
    IRQ. This split gives the top of the screen one palette and the
    scoreboard another within the same frame.
  - `irq_install` (`&497E`) hooks IRQ1V (`&0204`/`&0205`) to point at
    `&4900`, saving the prior vector at zp `&64`/`&65`. Loader2 line
    1000 (`?&9C=0:IF Q%<>1 CALL&497E`) does the install.
  - The bytes in the on-disk GRAPHIX file at `&493F` are the scenario-1
    palette (black/red/yellow/white). `&494F` is the always-on
    scoreboard palette (black/blue/cyan/white).
  - Scenarios 2-4 rewrite `&493F[0..11]` at level load via
    **Loader2 PROCs** dispatched from lines 940-970 based on start
    level `L% = ?&9D`:

    | L%       | PROC called  | Effect                                |
    |----------|--------------|---------------------------------------|
    | 1, 2     | `PROCLV12`   | none — keeps shipped lev1 palette     |
    | 3, 4     | `PROCL34`    | `READT%?&493F` over DATA line 1160    |
    | 5, 6     | `PROCL56`    | `READT%?&493F` over DATA line 1180    |
    | 7, 8     | `PROCL78`    | `READT%?&493F` over DATA line 1200    |

    Each POKE loop runs `FOR T%=0 TO 15: READ T%?&493F: NEXT`, so it
    writes 16 bytes — but only the first 12 are read by the IRQ.

MODE 5 pixel→palette mapping: `pixel V → palette latch entry
[0, 3, 12, 15][V]` (the BBC ULA bit-replicates the 2-bit pixel into
a 4-bit palette index; other entries are spares unused by MODE 5).
Decoded:

| Scenario | Pixel 0 | Pixel 1 | Pixel 2 | Pixel 3 |
|----------|---------|---------|---------|---------|
| 1        | black   | red     | yellow  | white   |
| 2        | black   | blue    | cyan    | white   |
| 3        | black   | red     | green   | white   |
| 4        | black   | red     | magenta | white   |

Use `palette_for_level(scenario)` from `render_screen.py` to pick the
right palette. `NEVRYON_GAME_PALETTE` defaults to scenario 1.

**Loader screens** (title/options/scoreboard, before in-game IRQ
takes over): Loader2 line 990 sets `VDU 19,3,7;0; 19,2,6;0; 19,1,1;0;` →
0=black, 1=red, 2=cyan, 3=white. Use `NEVRYON_LOADER_PALETTE`.

### Map tile layout
- Upper tile id table at `&7E10` (LEVD2 file offset `&A90`), 240 entries.
- Lower tile id table at `&7F10` (file offset `&B90`), 240 entries.
- Tile catalog at `&4F00` in LEVD1, 128 bytes per tile (4 col × 32 lines).
- **Upper tile is rendered vertically mirrored** (`zp_sprite_dir_flag=0`
  in `L127B` draw routine — read column-major bytes in reverse).
- Upper tile at screen char rows 0-3 (top of playfield), lower tile at
  rows 16-19 (bottom). 12-row (96 px) gap between is shared with
  player ship, enemies, force-fields, and starfield.

### Per-level data — naming convention
Every byte the engine reads from the LEVD files falls into one of six
sprite categories. Use these names consistently in cfgs, comments,
docs and PNG filenames; **don't** reintroduce older umbrella names
like `lev_decor_sprites`, `lev_enemy_sprites`, `lev_death_anim_*`,
`lev_hazard_sprite_a/b` (those were dropped in Session 13 because
they hid the per-frame structure).

| Category         | `lev_*` constant(s)         | PNG filename(s)       | Shape  | Bytes |
|------------------|-----------------------------|-----------------------|--------|------:|
| Player explosion | `lev_explosion_0..5`        | `explosion_00..05`    | 4×32   | 128 each, 6 frames; frames 0..3 in LEVD1, 4..5 in LEVD2 |
| Small enemy      | `lev_enemy_0..3`            | `enemy_00..03`        | 4×24   | 96 each, 4 frames in LEVD1 (column-shared) |
| Enemy hit        | `lev_enemy_hit_1..3`        | `enemy_hit_01..03`    | 4×24   | 96 each, 3 frames in LEVD1 (column-shared) |
| Player ship      | `lev_player_sprite`         | `player_sprite`       | 6×22   | 132, LEVD1 |
| Tile catalog     | `lev_tile_catalog + N*&80`  | `tile_00..17`         | 4×32   | 128 each, 18 slots in LEVD1 |
| Hazards          | `lev_hazard_0..13`          | `hazard_stage{1,2}_00..13` | 4×32   | 128 each, 14 in LEVD2 (stage 1) + 14 in LEVD3 (stage 2) — stages share offsets in the file, the sprite bytes differ. The 14 ptr LUT entries at `&7A80..&7A8D / &7AC0..&7ACD` are byte-identical between LEVD2 and LEVD3 in every scenario. |

The 32-entry `lev_hazard_ptr_lo/hi` table also has fixed aliasing:
slots 21..26 are the explosion-frame source pointers
(`lev_explosion_ptr_lo/hi` = `lev_hazard_ptr_*[21..26]`); slots
17/18 reuse `lev_tile_catalog` tile 5/4 bytes; slots 15/16/19 point
into `$.GRAPHIX`. See `docs/memory_map.md` and
`levels/<n>/README.md` for the full index-to-sprite tables.

### Sprite format (column-major)
- Stored as W byte-columns × H scanlines.
- A byte-column is 4 pixels wide (one MODE 5 byte = 4 px).
- Bytes are laid out: column-0 top-to-bottom, then column-1 top-to-bottom, ...
- `tools/render_sprite.py` decodes this.

### File conventions
- Python tools: kept dependency-free where possible; standard library only.
  Pillow is acceptable for image output if added — call it out in the tool.
- All decoders should be deterministic and re-runnable against
  `extracted/` to produce identical output.
- Document any "magic number" or offset you discover in JOURNAL.md the moment
  you find it, even if not yet confirmed.

## Git workflow

Remote: `git@github.com:waitingforvsync/nevryon.git` (origin, not yet pushed).

- Working branch: `main`.
- Commit only when the user asks. Do not push without explicit instruction.
- Never include the disk image's *contents* in commits if doing so would
  redistribute the game illegally; the `.ssd` itself ships as part of public
  archives, so we currently version it. Re-evaluate before publishing.

## Where we are

See JOURNAL.md for the latest status. The top of JOURNAL.md always reflects
the current state of the investigation.

For a per-file content reference (load addresses, byte-map of LEVD1/
LEVD2/LEVD3/GRAPHIX, boot chain summary, named routines in CODE),
see `docs/file_layout.md`.

For a single-page picture of the whole CPU memory map (zero page,
each binary's window, screen RAM, per-level data sub-blocks, and
the spawn-attribute encoding), see `docs/memory_map.md`.

For a walk through how the engine actually runs — the per-frame
pipeline, the two NPC pools and their state machines, hazard types
(including the force-field's spawn-pair convention and the flame's
one-shot dispatch), enemy motion patterns 1..6, the pickup tier
ladder, force-pod / player-missile unlocks, animation cycles —
see `docs/engine_overview.md`.

For per-level visualisations (tile catalog, enemies, hazards, the
map strip with and without spawn pins, raw binary table dumps, and
a decoded spawn-table per stage), see `levels/<n>/README.md`.

## How to update these docs

- **CLAUDE.md** changes when the workflow/conventions change — keep stable.
- **JOURNAL.md** gets an entry every working session, newest at the top, with
  a date heading (YYYY-MM-DD) and a short narrative of what was attempted,
  what worked, what didn't, and the next planned step.
