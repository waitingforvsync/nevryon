#!/usr/bin/env python3
"""6502 disassembler emitting BeebAsm-compatible source.

BeebAsm syntax conventions used here:
  - Hex literals use & (e.g. LDA #&FF, LDA &1234)
  - Labels are introduced with '.' (e.g. .my_routine)
  - Data: EQUB / EQUW / EQUD / EQUS
  - ORG <addr> sets origin
  - Branch targets emit as labels when known

Features:
  - Reads a control "info" file (TOML or JSON) describing:
      base address, code/data regions, named labels, comments
  - Walks the input bytes, decoding instructions from the start of every
    declared code region, jumping conservatively (we don't trace branches
    yet — full reachability tracing would require knowing all entry points)
  - For data regions, emits EQUB / EQUW with optional comment
  - Auto-generates labels for branch and JSR/JMP targets that fall inside
    declared code regions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field


# 6502 opcode table. (mnemonic, mode, length).
# Modes:
#   imp  - implied / accumulator
#   imm  - immediate
#   zp   - zero page
#   zpx  - zero page,X
#   zpy  - zero page,Y
#   abs  - absolute
#   absx - absolute,X
#   absy - absolute,Y
#   ind  - indirect ((abs))
#   inx  - (zp,X)
#   iny  - (zp),Y
#   rel  - relative (branch)
#   acc  - accumulator (e.g. ASL A)
#
# Unknown opcodes emit as EQUB with a comment.
OPCODES: dict[int, tuple[str, str, int]] = {
    # ADC
    0x69: ("ADC", "imm", 2),  0x65: ("ADC", "zp", 2),  0x75: ("ADC", "zpx", 2),
    0x6D: ("ADC", "abs", 3),  0x7D: ("ADC", "absx", 3), 0x79: ("ADC", "absy", 3),
    0x61: ("ADC", "inx", 2),  0x71: ("ADC", "iny", 2),
    # AND
    0x29: ("AND", "imm", 2),  0x25: ("AND", "zp", 2),  0x35: ("AND", "zpx", 2),
    0x2D: ("AND", "abs", 3),  0x3D: ("AND", "absx", 3), 0x39: ("AND", "absy", 3),
    0x21: ("AND", "inx", 2),  0x31: ("AND", "iny", 2),
    # ASL
    0x0A: ("ASL", "acc", 1),  0x06: ("ASL", "zp", 2),  0x16: ("ASL", "zpx", 2),
    0x0E: ("ASL", "abs", 3),  0x1E: ("ASL", "absx", 3),
    # Branches
    0x10: ("BPL", "rel", 2),  0x30: ("BMI", "rel", 2),  0x50: ("BVC", "rel", 2),
    0x70: ("BVS", "rel", 2),  0x90: ("BCC", "rel", 2),  0xB0: ("BCS", "rel", 2),
    0xD0: ("BNE", "rel", 2),  0xF0: ("BEQ", "rel", 2),
    # BIT
    0x24: ("BIT", "zp", 2),  0x2C: ("BIT", "abs", 3),
    # BRK
    0x00: ("BRK", "imp", 1),
    # Flags
    0x18: ("CLC", "imp", 1),  0xD8: ("CLD", "imp", 1),  0x58: ("CLI", "imp", 1),
    0xB8: ("CLV", "imp", 1),  0x38: ("SEC", "imp", 1),  0xF8: ("SED", "imp", 1),
    0x78: ("SEI", "imp", 1),
    # CMP
    0xC9: ("CMP", "imm", 2),  0xC5: ("CMP", "zp", 2),  0xD5: ("CMP", "zpx", 2),
    0xCD: ("CMP", "abs", 3),  0xDD: ("CMP", "absx", 3), 0xD9: ("CMP", "absy", 3),
    0xC1: ("CMP", "inx", 2),  0xD1: ("CMP", "iny", 2),
    # CPX, CPY
    0xE0: ("CPX", "imm", 2),  0xE4: ("CPX", "zp", 2),  0xEC: ("CPX", "abs", 3),
    0xC0: ("CPY", "imm", 2),  0xC4: ("CPY", "zp", 2),  0xCC: ("CPY", "abs", 3),
    # DEC, DEX, DEY
    0xC6: ("DEC", "zp", 2),  0xD6: ("DEC", "zpx", 2),  0xCE: ("DEC", "abs", 3),
    0xDE: ("DEC", "absx", 3),
    0xCA: ("DEX", "imp", 1),  0x88: ("DEY", "imp", 1),
    # EOR
    0x49: ("EOR", "imm", 2),  0x45: ("EOR", "zp", 2),  0x55: ("EOR", "zpx", 2),
    0x4D: ("EOR", "abs", 3),  0x5D: ("EOR", "absx", 3), 0x59: ("EOR", "absy", 3),
    0x41: ("EOR", "inx", 2),  0x51: ("EOR", "iny", 2),
    # INC, INX, INY
    0xE6: ("INC", "zp", 2),  0xF6: ("INC", "zpx", 2),  0xEE: ("INC", "abs", 3),
    0xFE: ("INC", "absx", 3),
    0xE8: ("INX", "imp", 1),  0xC8: ("INY", "imp", 1),
    # JMP, JSR, RTS, RTI
    0x4C: ("JMP", "abs", 3),  0x6C: ("JMP", "ind", 3),  0x20: ("JSR", "abs", 3),
    0x60: ("RTS", "imp", 1),  0x40: ("RTI", "imp", 1),
    # LDA
    0xA9: ("LDA", "imm", 2),  0xA5: ("LDA", "zp", 2),  0xB5: ("LDA", "zpx", 2),
    0xAD: ("LDA", "abs", 3),  0xBD: ("LDA", "absx", 3), 0xB9: ("LDA", "absy", 3),
    0xA1: ("LDA", "inx", 2),  0xB1: ("LDA", "iny", 2),
    # LDX
    0xA2: ("LDX", "imm", 2),  0xA6: ("LDX", "zp", 2),  0xB6: ("LDX", "zpy", 2),
    0xAE: ("LDX", "abs", 3),  0xBE: ("LDX", "absy", 3),
    # LDY
    0xA0: ("LDY", "imm", 2),  0xA4: ("LDY", "zp", 2),  0xB4: ("LDY", "zpx", 2),
    0xAC: ("LDY", "abs", 3),  0xBC: ("LDY", "absx", 3),
    # LSR
    0x4A: ("LSR", "acc", 1),  0x46: ("LSR", "zp", 2),  0x56: ("LSR", "zpx", 2),
    0x4E: ("LSR", "abs", 3),  0x5E: ("LSR", "absx", 3),
    # NOP
    0xEA: ("NOP", "imp", 1),
    # ORA
    0x09: ("ORA", "imm", 2),  0x05: ("ORA", "zp", 2),  0x15: ("ORA", "zpx", 2),
    0x0D: ("ORA", "abs", 3),  0x1D: ("ORA", "absx", 3), 0x19: ("ORA", "absy", 3),
    0x01: ("ORA", "inx", 2),  0x11: ("ORA", "iny", 2),
    # Stack
    0x48: ("PHA", "imp", 1),  0x68: ("PLA", "imp", 1),  0x08: ("PHP", "imp", 1),
    0x28: ("PLP", "imp", 1),
    # ROL, ROR
    0x2A: ("ROL", "acc", 1),  0x26: ("ROL", "zp", 2),  0x36: ("ROL", "zpx", 2),
    0x2E: ("ROL", "abs", 3),  0x3E: ("ROL", "absx", 3),
    0x6A: ("ROR", "acc", 1),  0x66: ("ROR", "zp", 2),  0x76: ("ROR", "zpx", 2),
    0x6E: ("ROR", "abs", 3),  0x7E: ("ROR", "absx", 3),
    # SBC
    0xE9: ("SBC", "imm", 2),  0xE5: ("SBC", "zp", 2),  0xF5: ("SBC", "zpx", 2),
    0xED: ("SBC", "abs", 3),  0xFD: ("SBC", "absx", 3), 0xF9: ("SBC", "absy", 3),
    0xE1: ("SBC", "inx", 2),  0xF1: ("SBC", "iny", 2),
    # STA
    0x85: ("STA", "zp", 2),  0x95: ("STA", "zpx", 2),  0x8D: ("STA", "abs", 3),
    0x9D: ("STA", "absx", 3), 0x99: ("STA", "absy", 3),
    0x81: ("STA", "inx", 2),  0x91: ("STA", "iny", 2),
    # STX, STY
    0x86: ("STX", "zp", 2),  0x96: ("STX", "zpy", 2),  0x8E: ("STX", "abs", 3),
    0x84: ("STY", "zp", 2),  0x94: ("STY", "zpx", 2),  0x8C: ("STY", "abs", 3),
    # Transfers
    0xAA: ("TAX", "imp", 1),  0xA8: ("TAY", "imp", 1),  0xBA: ("TSX", "imp", 1),
    0x8A: ("TXA", "imp", 1),  0x9A: ("TXS", "imp", 1),  0x98: ("TYA", "imp", 1),
}


@dataclass
class Region:
    start: int          # absolute CPU address
    end: int            # exclusive
    kind: str           # "code" or "data"
    width: int = 1       # for data: bytes per EQU (1=EQUB, 2=EQUW)
    comment: str = ""


@dataclass
class DisasmConfig:
    base: int                                 # ORG address
    regions: list[Region] = field(default_factory=list)
    labels: dict[int, str] = field(default_factory=dict)
    comments: dict[int, str] = field(default_factory=dict)
    # OS / external addresses to give friendly names. Items from the
    # cfg JSON go here; they're assumed to be defined elsewhere
    # (master `Nevryon.6502`) when `emit_externs=false`.
    extern_labels: dict[int, str] = field(default_factory=dict)
    # Auto-promoted externs (out-of-range data / zp slots discovered
    # while disassembling). The master doesn't know about these, so
    # they're always emitted inline in the per-binary .6502 to keep
    # the build self-contained.
    auto_extern_labels: dict[int, str] = field(default_factory=dict)
    # Master-file equates: addr → name parsed from the master
    # `Nevryon.6502` (or whichever file the user points to). Loading
    # these makes the disasm prefer the master's preferred names over
    # auto-generated `zp_XX` / `data_XXXX` fallbacks.
    master_externs: dict[int, str] = field(default_factory=dict)
    # Immediate-operand overrides keyed by the PC of the # instruction.
    # Value is a literal BeebAsm expression that replaces the raw value
    # (e.g. "LO(some_label)" / "HI(some_label)").
    immediate_overrides: dict[int, str] = field(default_factory=dict)
    # Reachability tracing entry points. When non-empty, the tool traces
    # code reachability from these addresses (following JMP/JSR/branches
    # until RTS/RTI/BRK) and synthesises code/data regions from the
    # result, replacing any unrecognised gaps with EQUB data. User-
    # declared `data` regions are still honoured (they're treated as
    # forced data even if reached by the tracer).
    entries: list[int] = field(default_factory=list)
    # If false, the per-file extern_labels equates are not emitted at
    # the top of the .6502 output (the master .6502 wrapper declares
    # them once instead). Defaults to true for standalone-style output.
    emit_externs: bool = True

    @classmethod
    def from_json(cls, path: str) -> "DisasmConfig":
        with open(path) as f:
            j = json.load(f)
        c = cls(base=int(j["base"], 0) if isinstance(j["base"], str) else j["base"])
        for r in j.get("regions", []):
            c.regions.append(Region(
                start=int(r["start"], 0) if isinstance(r["start"], str) else r["start"],
                end=int(r["end"], 0) if isinstance(r["end"], str) else r["end"],
                kind=r.get("kind", "code"),
                width=r.get("width", 1),
                comment=r.get("comment", ""),
            ))
        for k, v in j.get("labels", {}).items():
            c.labels[int(k, 0)] = v
        for k, v in j.get("comments", {}).items():
            c.comments[int(k, 0)] = v
        for k, v in j.get("extern_labels", {}).items():
            c.extern_labels[int(k, 0)] = v
        for k, v in j.get("immediate_overrides", {}).items():
            c.immediate_overrides[int(k, 0)] = v
        for e in j.get("entries", []):
            c.entries.append(int(e, 0) if isinstance(e, str) else e)
        c.emit_externs = j.get("emit_externs", True)
        return c


def fmt_hex(value: int, width: int) -> str:
    return f"&{value:0{width}X}"


def fmt_operand(mode: str, value: int, target_label: str | None) -> str:
    if mode == "imm":
        return f"#{fmt_hex(value, 2)}"
    if mode == "zp":
        return target_label or fmt_hex(value, 2)
    if mode == "zpx":
        return f"{target_label or fmt_hex(value, 2)},X"
    if mode == "zpy":
        return f"{target_label or fmt_hex(value, 2)},Y"
    if mode == "abs":
        return target_label or fmt_hex(value, 4)
    if mode == "absx":
        return f"{target_label or fmt_hex(value, 4)},X"
    if mode == "absy":
        return f"{target_label or fmt_hex(value, 4)},Y"
    if mode == "ind":
        return f"({target_label or fmt_hex(value, 4)})"
    if mode == "inx":
        return f"({target_label or fmt_hex(value, 2)},X)"
    if mode == "iny":
        return f"({target_label or fmt_hex(value, 2)}),Y"
    if mode == "rel":
        return target_label or fmt_hex(value, 4)
    if mode == "acc":
        return "A"
    return ""


def collect_branch_targets(data: bytes, base: int, region: Region,
                           targets: set[int],
                           jsr_targets: set[int] | None = None):
    """First pass: scan code in this region and add all branch / JMP / JSR
    targets to the `targets` set (for label generation). If `jsr_targets`
    is also given, populate it with JSR-only destinations — used by the
    code emitter to insert a blank line before every routine entry
    point so the output reads as discrete subroutines instead of one
    wall of text."""
    pc = region.start
    while pc < region.end:
        off = pc - base
        if off < 0 or off >= len(data):
            break
        opcode = data[off]
        info = OPCODES.get(opcode)
        if info is None:
            pc += 1
            continue
        mnem, mode, length = info
        if pc + length > region.end:
            break
        operand_lo = data[off + 1] if length >= 2 and off + 1 < len(data) else 0
        operand_hi = data[off + 2] if length >= 3 and off + 2 < len(data) else 0

        if mode == "rel":
            target = pc + 2 + ((operand_lo - 256) if operand_lo & 0x80 else operand_lo)
            targets.add(target & 0xFFFF)
        elif mnem in ("JMP", "JSR") and mode in ("abs", "ind"):
            target = (operand_hi << 8) | operand_lo
            targets.add(target)
            if jsr_targets is not None and mnem == "JSR":
                jsr_targets.add(target)
        pc += length


def disasm_code_region(data: bytes, base: int, region: Region,
                       labels: dict[int, str], extern_labels: dict[int, str],
                       comments: dict[int, str], lines: list[str],
                       immediate_overrides: dict[int, str] | None = None,
                       auto_extern_labels: dict[int, str] | None = None,
                       jsr_targets: set[int] | None = None,
                       sm_operand_labels: dict[int, str] | None = None):
    """Emit one code region. `sm_operand_labels` is a dict of
    (addr → name) for symbols whose address falls *inside* an
    instruction's operand bytes (i.e. self-modified-operand bytes).
    The matching `name = &addr` equate is emitted on the line
    immediately above the instruction whose operand it patches —
    not in a global block at the file head — so each self-mod
    callsite carries its own annotation."""
    immediate_overrides = immediate_overrides or {}
    auto_extern_labels = auto_extern_labels or {}
    jsr_targets = jsr_targets or set()
    sm_operand_labels = sm_operand_labels or {}
    def lookup(addr: int):
        return (labels.get(addr) or extern_labels.get(addr)
                or auto_extern_labels.get(addr))
    pc = region.start
    while pc < region.end:
        # Emit pending label if this PC has one. Routine entries
        # (JSR destinations) get a leading blank line so each
        # subroutine is visually separated.
        if pc in labels:
            if pc in jsr_targets and pc != region.start and lines and lines[-1] != "":
                lines.append("")
            lines.append(f".{labels[pc]}")
        off = pc - base
        if off < 0 or off >= len(data):
            break
        # Look ahead at this instruction's length so we can check for
        # any self-mod-operand labels falling inside its operand bytes.
        # If found, emit the equate(s) right above the instruction —
        # defined relative to BeebAsm's current PC (`*`) so the equate
        # tracks the instruction even if the surrounding code shifts.
        _info = OPCODES.get(data[off])
        _instr_len = _info[2] if _info else 1
        if _instr_len + off > len(data):
            _instr_len = 1
        for byte_pc in range(pc + 1, pc + _instr_len):
            if byte_pc in sm_operand_labels:
                name = sm_operand_labels[byte_pc]
                offset = byte_pc - pc
                lines.append(f"{name:16} = * + {offset}")
        opcode = data[off]
        info = OPCODES.get(opcode)
        if info is None:
            # Unknown opcode → emit as EQUB
            cmt = comments.get(pc, "")
            cmt_str = f"  \\ {cmt}" if cmt else ""
            lines.append(f"    EQUB {fmt_hex(opcode, 2)}{cmt_str}  \\ ?? opcode &{opcode:02X}")
            pc += 1
            continue
        mnem, mode, length = info
        if pc + length > region.end:
            lines.append(f"    EQUB {fmt_hex(opcode, 2)}  \\ {mnem} truncated")
            pc += 1
            continue

        operand_lo = data[off + 1] if length >= 2 else 0
        operand_hi = data[off + 2] if length >= 3 else 0

        if mode == "imm":
            value = operand_lo
            override = immediate_overrides.get(pc)
            if override is not None:
                operand_str = f"#{override}"
            else:
                operand_str = fmt_operand(mode, value, None)
        elif mode in ("zp", "zpx", "zpy", "inx", "iny"):
            value = operand_lo
            tgt_lbl = lookup(value)
            operand_str = fmt_operand(mode, value, tgt_lbl)
        elif mode == "rel":
            offset = (operand_lo - 256) if operand_lo & 0x80 else operand_lo
            value = (pc + 2 + offset) & 0xFFFF
            tgt_lbl = lookup(value)
            operand_str = fmt_operand(mode, value, tgt_lbl)
        elif mode in ("abs", "absx", "absy", "ind"):
            value = (operand_hi << 8) | operand_lo
            tgt_lbl = lookup(value)
            operand_str = fmt_operand(mode, value, tgt_lbl)
        elif mode == "acc":
            value = 0
            operand_str = fmt_operand(mode, 0, None)
        else:  # imp
            value = 0
            operand_str = ""

        cmt = comments.get(pc, "")
        cmt_str = f"  \\ {cmt}" if cmt else ""
        if operand_str:
            lines.append(f"    {mnem} {operand_str}{cmt_str}")
        else:
            lines.append(f"    {mnem}{cmt_str}")
        pc += length


def disasm_data_region(data: bytes, base: int, region: Region,
                       labels: dict[int, str], comments: dict[int, str],
                       lines: list[str]):
    pc = region.start
    while pc < region.end:
        if pc in labels:
            lines.append(f".{labels[pc]}")
        off = pc - base
        if off < 0 or off >= len(data):
            break
        if pc in comments:
            lines.append(f"    \\ {comments[pc]}")

        if region.kind == "string":
            # Emit ASCII as EQUS "...", &XX terminators; break each line
            # at a CR (&0D) or at the next label.
            parts: list[str] = []
            buf: list[int] = []
            run_start = pc
            def flush_buf():
                if buf:
                    s = ''.join(chr(b) for b in buf).replace('\\', '\\\\').replace('"', '\\"')
                    parts.append(f'"{s}"')
                    buf.clear()
            while pc < region.end and off < len(data):
                if pc != run_start and pc in labels:
                    break
                b = data[off]
                if 0x20 <= b < 0x7F and b != 0x22:  # printable, not '"'
                    buf.append(b)
                else:
                    flush_buf()
                    parts.append(fmt_hex(b, 2))
                pc += 1
                off = pc - base
                if b == 0x0D:  # CR — end of string
                    break
            flush_buf()
            if parts:
                lines.append(f"    EQUS {', '.join(parts)}")
            continue

        if region.width == 2:
            if pc + 2 > region.end or off + 2 > len(data):
                lines.append(f"    EQUB {fmt_hex(data[off], 2)}  \\ trailing")
                pc += 1
                continue
            val = data[off] | (data[off + 1] << 8)
            lines.append(f"    EQUW {fmt_hex(val, 4)}")
            pc += 2
        else:
            # Group up to 8 bytes per line for compactness
            row = []
            row_start = pc
            row_end = min(pc + 8, region.end)
            while pc < row_end and off < len(data):
                # Check if next byte has a label; if so, break the line
                if pc != row_start and pc in labels:
                    break
                row.append(fmt_hex(data[off], 2))
                pc += 1
                off = pc - base
                if pc in comments and pc != row_start:
                    break
            lines.append(f"    EQUB {', '.join(row)}")


def find_dead_jumps(data: bytes, base: int, code_bytes: set[int]) -> list[int]:
    """Recover untraced instruction sequences sitting in unreached gaps.

    For each contiguous gap of unreached bytes, decode forward from the
    very start of the gap. If the decode reaches an unconditional flow
    break (JMP / RTS / RTI / BRK) — and any branch / JMP target inside
    that decode lands either inside the same gap or in already-reached
    code — treat the gap-start as a recovered entry point.

    This catches:
      - Bare `JMP main_loop` / `JMP some_routine` left after a `JMP
        external_call`.
      - Trampoline routine stubs (`LDA #x; STA src_lo; LDA #y; STA
        src_hi; JMP plotter`) called only from other binaries.
    """
    end_addr = base + len(data)
    extras: list[int] = []
    pc = base
    while pc < end_addr:
        if pc in code_bytes:
            pc += 1
            continue
        gap_start = pc
        # Find the end of this gap (next reached byte or EOF)
        gap_end = gap_start
        while gap_end < end_addr and gap_end not in code_bytes:
            gap_end += 1
        # Walk through the gap, trying to recover one stub at a time.
        # Each recovered stub starts at the current position and must
        # end with an unconditional flow break (JMP / RTS / RTI / BRK)
        # whose target (for JMP) is in already-reached code or back into
        # this gap. Stubs run end-to-end without padding.
        stub_start = gap_start
        while stub_start < gap_end:
            cur = stub_start
            terminated_cleanly = False
            while cur < gap_end:
                off = cur - base
                info = OPCODES.get(data[off])
                if info is None:
                    break
                mnem, mode, length = info
                if cur + length > gap_end:
                    break
                if mnem in ("RTS", "RTI", "BRK"):
                    terminated_cleanly = True
                    cur += length
                    break
                if mnem == "JMP":
                    if mode == "abs":
                        target = (data[off + 2] << 8) | data[off + 1]
                        if target in code_bytes or gap_start <= target < gap_end:
                            terminated_cleanly = True
                    cur += length
                    break
                cur += length
            if not terminated_cleanly:
                break
            extras.append(stub_start)
            stub_start = cur
        pc = gap_end
    return extras


def trace_reachable(data: bytes, base: int, entries: list[int]) -> tuple[set[int], set[int]]:
    """Trace code reachability from entry points.

    Returns (instruction_starts, code_bytes):
      - instruction_starts: addresses that begin a decoded instruction
      - code_bytes: addresses covered by any decoded instruction
    Flow stops at RTS / RTI / BRK / JMP. JSR follows the target AND
    falls through after the call. Branches follow both arms.
    """
    instr_starts: set[int] = set()
    code_bytes: set[int] = set()
    end_addr = base + len(data)
    work: list[int] = list(entries)
    while work:
        pc = work.pop()
        while True:
            if pc in instr_starts:
                break
            if pc < base or pc >= end_addr:
                break
            off = pc - base
            opcode = data[off]
            info = OPCODES.get(opcode)
            if info is None:
                break
            mnem, mode, length = info
            if pc + length > end_addr:
                break
            instr_starts.add(pc)
            for i in range(length):
                code_bytes.add(pc + i)

            if mnem in ("RTS", "RTI", "BRK"):
                break
            if mnem == "JMP":
                if mode == "abs":
                    target = (data[off + 2] << 8) | data[off + 1]
                    work.append(target)
                break
            if mnem == "JSR":
                target = (data[off + 2] << 8) | data[off + 1]
                work.append(target)
                pc += length
                continue
            if mode == "rel":
                rel = data[off + 1]
                if rel & 0x80:
                    rel -= 256
                target = (pc + length + rel) & 0xFFFF
                work.append(target)
                pc += length
                continue
            pc += length
    return instr_starts, code_bytes


def synthesise_regions(code_bytes: set[int], base: int, length: int,
                       forced_regions: list[Region]) -> list[Region]:
    """Build a list of code/data regions covering [base, base+length).

    Forced regions from cfg override the tracer:
      - A forced `data` region masks any code reached by the tracer.
      - A forced `code` region masks data — these contiguous bytes are
        all decoded even if the tracer didn't reach them. (We add their
        starts as entry points before calling this, so usually they ARE
        in code_bytes; this just makes the kind explicit.)
    """
    end = base + length
    # Build a per-address kind table
    forced_data: set[int] = set()
    forced_code: set[int] = set()
    for r in forced_regions:
        target = forced_code if r.kind == "code" else forced_data
        for addr in range(r.start, r.end):
            target.add(addr)

    def kind_at(addr: int) -> str:
        if addr in forced_data:
            return "data"
        if addr in forced_code or addr in code_bytes:
            return "code"
        return "data"

    if length == 0:
        return []

    regions: list[Region] = []
    cur_start = base
    cur_kind = kind_at(base)
    for addr in range(base + 1, end):
        k = kind_at(addr)
        if k != cur_kind:
            regions.append(Region(start=cur_start, end=addr, kind=cur_kind))
            cur_start = addr
            cur_kind = k
    regions.append(Region(start=cur_start, end=end, kind=cur_kind))
    # Annotate forced regions with their kind/comment so they survive synthesis
    forced_by_start = {r.start: r for r in forced_regions}
    for i, r in enumerate(regions):
        f = forced_by_start.get(r.start)
        if f is not None and f.end == r.end:
            regions[i] = Region(start=r.start, end=r.end, kind=f.kind,
                                 width=f.width, comment=f.comment)
    return regions


def collect_table_targets(data: bytes, base: int, instr_starts: set[int],
                          code_bytes: set[int]) -> tuple[set[int], set[int], set[int]]:
    """Catalog every data operand reached. Returns
    (indexed_abs, plain_abs, zp_addrs):

      - indexed_abs:  `LDA tbl,X` / `STA tbl,Y` etc. — multi-byte
        table accessed by index. Name as `tbl_XXXX`. Skipped when the
        target is inside reached code (an indexed read of code bytes
        is exotic and probably intentional, but the existing label
        machinery has nowhere clean to put the name).
      - plain_abs:   `LDA abs` / `STA abs` / `INC abs` etc. — single
        named variable / state byte. Name as `data_XXXX`. INCLUDES
        targets that fall inside an instruction (BBC code routinely
        reuses an instruction operand byte as scratchpad RAM); the
        emit pass promotes those to mid-instruction equates.
      - zp_addrs:    `LDA zp` / `STA zp,X` etc. — zero-page slot.
        Name as `zp_XX`.

    JMP/JSR are handled separately by collect_branch_targets, so they
    aren't included here even though their mode is `abs`."""
    indexed_abs: set[int] = set()
    plain_abs: set[int] = set()
    zp_addrs: set[int] = set()
    indexed_modes = {"absx", "absy"}
    zp_modes = {"zp", "zpx", "zpy", "inx", "iny"}
    for pc in instr_starts:
        off = pc - base
        info = OPCODES.get(data[off])
        if info is None:
            continue
        mnem, mode, length = info
        if mnem in ("JMP", "JSR"):
            continue
        if mode in zp_modes and length >= 2:
            zp_addrs.add(data[off + 1])
            continue
        if length < 3:
            continue
        target = (data[off + 2] << 8) | data[off + 1]
        if mode in indexed_modes:
            indexed_abs.add(target)
        elif mode == "abs":
            plain_abs.add(target)
    return indexed_abs, plain_abs, zp_addrs


def disassemble(data: bytes, cfg: DisasmConfig) -> str:
    use_tracer = bool(cfg.entries)
    if use_tracer:
        # Treat the start of every user-declared code region as an
        # additional entry point.
        entries = list(cfg.entries)
        for r in cfg.regions:
            if r.kind == "code":
                entries.append(r.start)
        instr_starts, code_bytes = trace_reachable(data, cfg.base, entries)

        # Recover dead JMPs / JSRs sitting in gaps whose targets are
        # already classified as code. Re-trace once with those added.
        dead = find_dead_jumps(data, cfg.base, code_bytes)
        if dead:
            instr_starts, code_bytes = trace_reachable(
                data, cfg.base, entries + dead)

        # Synthesise regions covering the whole file from the tracer
        # output, with user-declared regions as forced overrides.
        regions = synthesise_regions(code_bytes, cfg.base, len(data),
                                      cfg.regions)
        cfg = DisasmConfig(
            base=cfg.base,
            regions=regions,
            labels=dict(cfg.labels),
            comments=dict(cfg.comments),
            extern_labels=dict(cfg.extern_labels),
            auto_extern_labels=dict(cfg.auto_extern_labels),
            master_externs=dict(cfg.master_externs),
            immediate_overrides=dict(cfg.immediate_overrides),
            entries=cfg.entries,
            emit_externs=cfg.emit_externs,
        )

        # Auto-label JMP/JSR/branch targets that fell inside reached code.
        # Track which labels are "routine entries" so the code emitter
        # can insert a blank line before each. Three sources count:
        #   1. JSR destinations.
        #   2. cfg.entries (the user's declared entry points).
        #   3. Any address with a user-supplied name in cfg.labels
        #      (auto-generated `L<addr>` labels added later don't count
        #      — they're typically branch / jmp targets *inside* a
        #      routine).
        targets: set[int] = set()
        jsr_targets: set[int] = set(cfg.entries) | set(cfg.labels)
        for r in cfg.regions:
            if r.kind == "code":
                collect_branch_targets(data, cfg.base, r, targets, jsr_targets)
        for t in sorted(targets):
            if t in code_bytes and t not in cfg.labels:
                cfg.labels[t] = f"L{t:04X}"

        # Auto-label data referenced from code with absolute or zp
        # addressing. Don't override user-supplied names. Out-of-range
        # refs that the master pre-declares get the master's preferred
        # name (added to cfg.extern_labels — assumed defined upstream);
        # everything else falls back to a `zp_XX` / `data_XXXX` /
        # `tbl_XXXX` auto-promotion emitted inline in this file.
        indexed_addrs, plain_addrs, zp_addrs = collect_table_targets(
            data, cfg.base, instr_starts, code_bytes)
        end_addr_now = cfg.base + len(data)
        def known(a: int) -> bool:
            return (a in cfg.labels or a in cfg.extern_labels
                    or a in cfg.auto_extern_labels)
        def adopt_extern(addr: int, fallback: str):
            """Pick the master's name if it has one; else use the
            fallback and emit inline."""
            if addr in cfg.master_externs:
                cfg.extern_labels.setdefault(addr, cfg.master_externs[addr])
            else:
                cfg.auto_extern_labels[addr] = fallback
        # &FFFF is the canonical "unused, will be self-modified at
        # runtime" placeholder — leave the disassembly showing the
        # raw literal `&FFFF` rather than autopromoting it to a
        # symbol that pretends to reference real memory.
        SM_PLACEHOLDER = 0xFFFF
        for addr in sorted(indexed_addrs):
            if known(addr) or addr == SM_PLACEHOLDER:
                continue
            if cfg.base <= addr < end_addr_now:
                cfg.labels[addr] = f"tbl_{addr:04X}"
            else:
                adopt_extern(addr, f"tbl_{addr:04X}")
        for addr in sorted(plain_addrs):
            if known(addr) or addr == SM_PLACEHOLDER:
                continue
            if cfg.base <= addr < end_addr_now:
                cfg.labels[addr] = f"data_{addr:04X}"
            else:
                adopt_extern(addr, f"data_{addr:04X}")
        for addr in sorted(zp_addrs):
            if known(addr):
                continue
            adopt_extern(addr, f"zp_{addr:02X}")

        # Label each declared entry too
        for e in cfg.entries:
            if e not in cfg.labels:
                cfg.labels[e] = f"sub_{e:04X}"

        # Auto-label each synthesised data region with its start address so
        # references can use a symbol instead of a raw hex.
        for r in cfg.regions:
            if r.kind == "data" and r.start not in cfg.labels:
                cfg.labels[r.start] = f"data_{r.start:04X}"
    else:
        # Legacy region-based mode (no tracing).
        targets = set()
        jsr_targets: set[int] = set()
        for r in cfg.regions:
            if r.kind == "code":
                collect_branch_targets(data, cfg.base, r, targets, jsr_targets)
        code_ranges = [(r.start, r.end) for r in cfg.regions if r.kind == "code"]
        for t in sorted(targets):
            if any(s <= t < e for s, e in code_ranges):
                if t not in cfg.labels:
                    cfg.labels[t] = f"L{t:04X}"

    # Promote any label whose address falls outside the ORG'd binary
    # range to an extern (emitted as `name = &XXXX` constant up top).
    # Also promote labels that point INSIDE a code instruction (between
    # instr_start and the next instr_start) — those bytes never get a
    # `.label` line of their own.
    end_addr = cfg.base + len(data)

    code_emit_points: set[int] = set()
    data_byte_addrs: set[int] = set()
    for r in cfg.regions:
        if r.kind == "code":
            pc = r.start
            while pc < r.end:
                off = pc - cfg.base
                if off < 0 or off >= len(data):
                    break
                info = OPCODES.get(data[off])
                length = info[2] if info else 1
                if pc + length > r.end:
                    length = 1
                code_emit_points.add(pc)
                pc += length
        else:
            for addr in range(r.start, r.end):
                data_byte_addrs.add(addr)

    for addr in list(cfg.labels):
        if addr < cfg.base or addr >= end_addr:
            cfg.extern_labels.setdefault(addr, cfg.labels.pop(addr))
        elif addr in data_byte_addrs:
            continue  # data byte — label will be emitted inline
        elif addr in code_emit_points:
            continue  # at an instruction start — label will be emitted
        else:
            # Address is mid-instruction (or in a forced-data gap that
            # somehow isn't covered) — emit as extern constant.
            cfg.extern_labels.setdefault(addr, cfg.labels.pop(addr))

    # Symmetric cleanup: in-range extern_labels that happen to point
    # at an instruction-start or data byte are NOT self-mod operand
    # bytes (they're just normal labels the user happened to put in
    # the cfg's `extern_labels` block). Demote them back to cfg.labels
    # so they're emitted as `.label` lines at the byte position rather
    # than as `name = * + N` inline equates.
    for addr in list(cfg.extern_labels):
        if not (cfg.base <= addr < end_addr):
            continue
        if addr in code_emit_points or addr in data_byte_addrs:
            cfg.labels.setdefault(addr, cfg.extern_labels.pop(addr))

    # Build output
    lines: list[str] = []
    lines.append("\\ ============================================================")
    lines.append(f"\\ Auto-disassembly — base {fmt_hex(cfg.base, 4)}")
    lines.append("\\ ============================================================")
    lines.append("")
    # Split extern_labels into in-range (mid-instruction equates for
    # labels that fall inside this binary's own operand bytes — i.e.
    # self-modified operand bytes) and out-of-range (OS, HW, cross-
    # file refs). The in-range "SM operand" labels are emitted by
    # disasm_code_region directly above the instruction whose operand
    # they patch, as `name = * + N` (PC-relative) so they track the
    # instruction regardless of where it ends up at assembly time.
    # Out-of-range externs go in the file header, gated by emit_externs.
    end_addr_for_split = cfg.base + len(data)
    sm_operand_labels = {a: n for a, n in cfg.extern_labels.items()
                         if cfg.base <= a < end_addr_for_split}
    out_range_ext = {a: n for a, n in cfg.extern_labels.items()
                     if not (cfg.base <= a < end_addr_for_split)}

    if out_range_ext and cfg.emit_externs:
        lines.append("\\ External / OS addresses:")
        for addr, name in sorted(out_range_ext.items()):
            lines.append(f"{name:16} = {fmt_hex(addr, 4)}")
        lines.append("")
    elif out_range_ext:
        lines.append("\\ Extern labels defined in master Nevryon.6502 wrapper:")
        for addr, name in sorted(out_range_ext.items()):
            lines.append(f"\\   {name} = {fmt_hex(addr, 4)}")
        lines.append("")
    # Auto-promoted externs (zp slots, data state outside this binary).
    # These aren't in the master, so always emit them inline. Avoid
    # re-declaring anything already covered by a cfg extern.
    cfg_extern_addrs = set(cfg.extern_labels)
    auto_ext_to_emit = {a: n for a, n in cfg.auto_extern_labels.items()
                        if a not in cfg_extern_addrs}
    if auto_ext_to_emit:
        lines.append("\\ Auto-promoted externs (zp/data outside this binary):")
        for addr, name in sorted(auto_ext_to_emit.items()):
            width = 2 if addr <= 0xFF else 4
            lines.append(f"{name:16} = {fmt_hex(addr, width)}")
        lines.append("")
    lines.append(f"ORG {fmt_hex(cfg.base, 4)}")
    lines.append("")

    # Sort regions and emit
    sorted_regions = sorted(cfg.regions, key=lambda r: r.start)
    cursor = cfg.base
    for r in sorted_regions:
        # Skip gap before region (or emit as default-data EQUB)
        if r.start > cursor:
            gap_region = Region(start=cursor, end=r.start, kind="data", width=1,
                                comment="(unannotated gap, treated as data)")
            lines.append("")
            lines.append(f"\\ --- gap {fmt_hex(cursor, 4)}..{fmt_hex(r.start, 4)} ---")
            disasm_data_region(data, cfg.base, gap_region, cfg.labels, cfg.comments, lines)
        lines.append("")
        lines.append(f"\\ ----- {r.kind} {fmt_hex(r.start, 4)}..{fmt_hex(r.end, 4)} -----")
        if r.comment:
            lines.append(f"\\ {r.comment}")
        if r.kind == "code":
            disasm_code_region(data, cfg.base, r, cfg.labels, cfg.extern_labels,
                               cfg.comments, lines, cfg.immediate_overrides,
                               cfg.auto_extern_labels, jsr_targets,
                               sm_operand_labels)
        else:
            disasm_data_region(data, cfg.base, r, cfg.labels, cfg.comments, lines)
        cursor = r.end

    # Trailing data
    end_of_file = cfg.base + len(data)
    if cursor < end_of_file:
        lines.append("")
        lines.append(f"\\ --- trailing data {fmt_hex(cursor, 4)}..{fmt_hex(end_of_file, 4)} ---")
        trailing = Region(start=cursor, end=end_of_file, kind="data", width=1)
        disasm_data_region(data, cfg.base, trailing, cfg.labels, cfg.comments, lines)

    return "\n".join(lines) + "\n"


def parse_master_externs(path: str) -> dict[int, str]:
    """Parse a BeebAsm source file for `name = &VAL` equates so we can
    use the master's preferred names for shared zp / hardware / extern
    addresses (instead of auto-promoting to `zp_XX` / `data_XXXX`)."""
    import re
    pat = re.compile(
        r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*&([0-9A-Fa-f]+)\s*(?:\\|$)')
    out: dict[int, str] = {}
    with open(path) as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            name = m.group(1)
            value = int(m.group(2), 16)
            out.setdefault(value, name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="binary file to disassemble")
    ap.add_argument("--base", type=lambda s: int(s, 0), required=True,
                    help="load address (CPU base)")
    ap.add_argument("--config", help="JSON config file (regions, labels, comments)")
    ap.add_argument("--end", type=lambda s: int(s, 0),
                    help="if no config, treat from base..end as one big code region")
    ap.add_argument("--master",
                    help="master .6502 file to scan for shared equates "
                         "(`name = &VAL`); preferred names override auto-promoted "
                         "`zp_XX` / `data_XXXX` fallback labels.")
    ap.add_argument("--output", "-o", required=True)
    args = ap.parse_args()

    with open(args.input, "rb") as f:
        data = f.read()

    if args.config:
        cfg = DisasmConfig.from_json(args.config)
        if cfg.base != args.base:
            print(f"warning: --base {args.base:#x} != config base {cfg.base:#x}",
                  file=sys.stderr)
    else:
        end = args.end or args.base + len(data)
        cfg = DisasmConfig(base=args.base,
                           regions=[Region(start=args.base, end=end, kind="code")])

    if args.master:
        cfg.master_externs = parse_master_externs(args.master)

    out = disassemble(data, cfg)
    with open(args.output, "w") as f:
        f.write(out)
    print(f"wrote {args.output} ({out.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
