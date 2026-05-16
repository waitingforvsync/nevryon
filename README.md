# Nevryon — reverse-engineering project

**Nevryon** (1990) is a MODE 5 horizontally-scrolling shoot-'em-up for the
BBC Micro, in the R-Type tradition. The game was written by
**Graeme Richardson** and published by **The Fourth Dimension**.

This repository is a community reverse-engineering effort: the original
6502 binaries are disassembled into commented, re-assemblable BeebAsm
sources; the per-level data tables are decoded and visualised; and the
sprite atlases and map tiles are dumped as PNGs. None of this project's
output is the original game — the game's bytes remain
Copyright © 1990 Graeme Richardson / The Fourth Dimension and are
included only for research and preservation purposes (see `LICENSE`).

The disk image originates from the publicly archived dumps at
[Stairway to Hell](https://stairwaytohell.com/bbc/).

## Aim

The project has three layered goals:

1. **Preserve and document the game.** A complete byte-by-byte explanation
   of every file on the disk image — what each file contains, where it
   loads in CPU memory, and how the code uses it.
2. **Reproduce the binaries.** A round-trippable BeebAsm source that
   re-assembles to byte-identical copies of `$.CODE` / `$.CODE2` /
   `$.CODE3` / `$.GRAPHIX`. The build script verifies this on every
   change.
3. **Make a modding-friendly base.** Once everything is named and the
   level data is structured, the same source serves as the starting point
   for a remake or a tile / sprite / map editor.

The disassembly is **assembled with [BeebAsm](https://github.com/stardot/beebasm)**
and verified byte-identical against the original `.SSD` extractions. All
sprite renderers are pure Python (standard library + Pillow).

## Status

| Component | State |
|-----------|-------|
| Boot / loader chain | Decoded |
| Sprite engine | Decoded + commented |
| Map / tile renderer | Decoded |
| Per-level data tables | Decoded byte-by-byte |
| Sound system | All effects identified, OSWORD &07 param blocks named |
| Per-level visualisations | One PNG per unique sprite, per scenario |
| Routine names | ~80 routines named across CODE / CODE2 / CODE3 |
| Cross-binary references | All addresses resolved to symbolic names |
| Byte-identical rebuild | ✓ for all four binaries |

See `JOURNAL.md` for the running narrative of how each piece was
discovered.

## Repository layout

```
4thDimension/Nevryon.ssd     Full 80-track DFS disk image (do not modify)
extracted/                   Files unpacked from the disk image
  _manifest.tsv              Per-file load/exec/length/start-sector
  $.<NAME> / N.<NAME>        Extracted file payloads (dir letter prefix)

disasm/                      BeebAsm-format reconstruction
  Nevryon.6502               Master file — INCLUDEs all four per-binary sources
  CODE.6502 + CODE.cfg.json  Annotated disassembly of $.CODE
  CODE2.6502  + .cfg.json    $.CODE2 — sound, score, intro, hazards
  CODE3.6502  + .cfg.json    $.CODE3 — inter-stage overlays + text engine
  GRAPHIX.6502 + .cfg.json   $.GRAPHIX — shared sprite atlas + IRQ palette split

tools/                       Python utilities
  dfs_extract.py             DFS catalog parser (Watford-DFS variant)
  bbcbasic_detoken.py        BBC BASIC II/IV detokeniser
  disasm6502.py              6502 → BeebAsm disassembler with tracing
  render_screen.py           MODE 1 / 2 / 5 bitmap → PNG
  render_sprite.py           Column-major sprite + grid viewer
  render_graphix_sprites.py  GRAPHIX atlas renderer
  render_map.py              LEVD1 tiles + LEVD2/3 column streams → strip
  render_level_summary.py    Composite map + enemies + spawn pins
  render_level.py            Per-level full output (sprites + maps + spawn tables)

levels/                      Per-scenario reverse-engineered data
  1/ 2/ 3/ 4/                One directory per scenario; each contains:
    explosion_00..05.png       6-frame player explosion (per-scenario palette)
    enemy_00..03.png           4-frame small-enemy animation
    enemy_hit_01..03.png       3-frame enemy hit/destruction
    player_sprite.png          The player ship
    tile_00..17.png            Map tile catalog
    hazard_00..13.png          14 stationary hazards (gun-towers, tanks, ...)
    map_strip.png              Full 240-col playfield strip (both stages share)
    map_with_spawns_{1,2}.png  Same with spawn-pin overlay (per stage)
    map_with_hazards_{1,2}.png Same with actual hazard sprites at spawn positions
    spawn_table_stage{1,2}.md  Decoded spawn schedule
    data/                      Raw 128/240-byte binary dumps
    README.md                  Byte-by-byte memory map + index→sprite tables

docs/
  file_layout.md             Per-file disk byte-map + named routine list
  memory_map.md              Single-page picture of CPU memory layout
                             (zero page, each binary, screen RAM, LEVD data,
                             spawn-attribute encoding)

graphix/                     Per-sprite atlas dumps from $.GRAPHIX
work/                        Scratch PNGs, level summaries

build.sh / build.bat         Regenerate disasm sources from cfg, then run
                             BeebAsm and verify byte-identity against
                             extracted/
build/                       Re-assembled binaries — `cmp -s` against
                             extracted/$.<NAME> should succeed

CLAUDE.md                    Project workflow + conventions
JOURNAL.md                   Running discovery log, newest entries on top
LICENSE                      MIT (project artefacts only — see notes there
                             about the original game's separate copyright)
```

## Getting started

If you just want to **look at things**:

- Per-level sprite & map dumps: `levels/1/`, `levels/2/`, `levels/3/`, `levels/4/`
- Full byte-by-byte memory map: `docs/memory_map.md`
- Annotated 6502 source: `disasm/CODE.6502` (with `disasm/Nevryon.6502` as the master)

If you want to **rebuild the binaries**:

```
./build.sh        # needs BeebAsm in PATH and Python 3
```

This regenerates the four `disasm/*.6502` files from the JSON cfgs, runs
BeebAsm against the master, then `cmp`s each output against
`extracted/$.<NAME>`. All four should report `BYTE-IDENTICAL`.

If you want to **regenerate the per-level visualisations**:

```
python3 tools/render_level.py
```

(Pillow optional — required only for PNG output.)

## Credits

- **Graeme Richardson** — author of *Nevryon* (1990).
- **The Fourth Dimension** — original publisher of the game.
- This reverse-engineering project is community work; see git history
  for individual contributions.

## License

The reverse-engineering output in this repository (disassembly, tools,
documentation, visualisations) is released under the [MIT license](LICENSE).
The original Nevryon binaries and disk image are not covered by that
license — they remain Copyright © 1990 Graeme Richardson / The Fourth
Dimension and are included only for research and preservation purposes.
If you are a rights holder and would prefer them removed, please open an
issue on the repository.
