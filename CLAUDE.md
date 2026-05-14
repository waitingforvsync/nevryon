# Nevryon Reverse-Engineering Project

Reverse-engineering the BBC Micro game **Nevryon** (4th Dimension, 1991) — a
MODE 5 sideways-scrolling R-Type clone — with the aim of recovering sprites
and level maps, and (stretch) producing a full BeebAsm disassembly toward a
remake.

The source disk image was downloaded from
<https://stairwaytohell.com/bbc/archive/diskimages/4thDimension/Nevryon.zip>.

## Repository layout

```
4thDimension/Nevryon.ssd     # full 80-track DFS disk image (do not modify)
extracted/                   # files unpacked from the disk image
  _manifest.tsv              # per-file load/exec/length/start-sector
  $.<NAME> / N.<NAME>        # extracted file payloads (dir letter prefix)
tools/                       # Python utilities (DFS, sprite, map decode)
  dfs_extract.py             # parses SSD catalog, extracts files (Watford-DFS variant)
  bbcbasic_detoken.py        # BBC BASIC II/IV detokeniser (handles junk preamble)
  render_screen.py           # MODE 1 / MODE 5 raw bitmap → PNG
  render_strip.py            # linear strip view of arbitrary bytes
  render_sprite.py           # column-major sprite + grid viewer
  disasm6502.py              # 6502 → BeebAsm disassembler with annotations
work/                        # PNG previews, scratch
disasm/                      # BeebAsm-format reconstruction in progress
  CODE.beebasm               # annotated disassembly of $.CODE
  CODE.cfg.json              # region/label/comment annotations for $.CODE
  CODE2.beebasm, CODE3.beebasm  # unannotated (annotate as we learn)
CLAUDE.md                    # this file — workflow & conventions
JOURNAL.md                   # running log of discoveries & decisions
```

## Hard-won lessons (read before editing)

### Catalog uses Watford / 1770-DFS byte-6 encoding, not Acorn DFS
Byte 6 of each file's metadata in catalog sector 1 packs the high bits
of load/exec/length/start_sector. The Nevryon disk uses:
  - bits 0-1: start-sector bits 9-8
  - bits 2-3: load-address bits 17-16
  - bits 4-5: file-length bits 17-16
  - bits 6-7: exec-address bits 17-16
*Not* the Acorn convention (which puts load at bits 0-1 and start at
6-7). If a freshly-extracted file looks like text where you expect
binary (or vice-versa), this is the first thing to check.

### Disassembly target is BeebAsm, not da65
`tools/disasm6502.py` emits BeebAsm syntax (`&hex`, `.label`, `EQUB`,
`ORG`, `\ comment`). Goal: a roundtrip-able source that BeebAsm can
re-assemble into the original binary. Drive it via the annotation JSON
(`disasm/<file>.cfg.json`) — add a region/label/comment any time we
identify one, then re-run. Do not hand-edit `.beebasm` output.

### Self-modifying code
The sprite engine self-modifies its `LDA &XXXX,X` source operand at
`L1194/L1195`. When disassembling, treat the two operand bytes as
data (declare them in `.cfg.json`) rather than letting them be decoded
as part of the LDA instruction.



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

### Game palette
**In-game (verified from emulator screenshot):** BBC default 4-colour —
logical 0=black, 1=red, 2=yellow, 3=white. Use `NEVRYON_GAME_PALETTE`.

**Loader screens (title/options/scoreboard):** Loader2 line 990 sets
`VDU 19,3,7;0; 19,2,6;0; 19,1,1;0;` → 2=cyan instead of yellow. Use
`NEVRYON_LOADER_PALETTE` for any pre-gameplay rendering.

The game CODE overrides the loader palette before gameplay starts
(several `LDA #&13` candidates in `$.CODE2` are likely VDU 19 calls).

### Map tile layout
- Upper tile id table at `&7F10` (LEVD2 file offset `&B90`), 240 entries.
- Lower tile id table at `&7E10` (file offset `&A90`), 240 entries.
- Tile catalog at `&4F00` in LEVD1, 128 bytes per tile (4 col × 32 lines).
- **Upper tile is rendered vertically mirrored** (`zp_sprite_dir_flag=0`
  in `L127B` draw routine — read column-major bytes in reverse).
- Upper tile at screen char rows 0-3 (top of playfield), lower tile at
  rows 16-19 (bottom). 12-row (96 px) gap between is shared with
  player ship, enemies, force-fields, and starfield.

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

## How to update these docs

- **CLAUDE.md** changes when the workflow/conventions change — keep stable.
- **JOURNAL.md** gets an entry every working session, newest at the top, with
  a date heading (YYYY-MM-DD) and a short narrative of what was attempted,
  what worked, what didn't, and the next planned step.
