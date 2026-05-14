#!/usr/bin/env python3
"""Scan CODE/CODE2/CODE3 binaries for the LDA #lo/STA &1194 + LDA #hi/STA &1195
self-modified-operand pattern that points the sprite blitter at a source
address. Report each site as (binary, addr, target, label).

Also scans for LDA #lo/STA <zp>; LDA #hi/STA <zp+1> ZP-pointer setups
that target known GRAPHIX or LEVD addresses.
"""

from __future__ import annotations

import json
import os
import sys


BINARIES = [
    ("CODE",    "extracted/$.CODE",    0x1100),
    ("CODE2",   "extracted/$.CODE2",   0x2800),
    ("CODE3",   "extracted/$.CODE3",   0x3300),
]


def load_graphix_labels():
    """Build {address: name} from disasm/GRAPHIX.cfg.json."""
    with open("disasm/GRAPHIX.cfg.json") as f:
        cfg = json.load(f)
    labels = {}
    for k, v in cfg.get("labels", {}).items():
        labels[int(k, 0)] = v
    return labels


def scan_self_mod(data: bytes, base: int):
    """Find LDA #imm / STA &1194 followed (within ~12 bytes) by LDA #imm / STA &1195.
    Returns list of (call_site_addr, lo, hi, target, distance)."""
    sites = []
    i = 0
    while i + 9 < len(data):
        # LDA #lo at i?: A9 <lo>
        if data[i] == 0xA9 and data[i+2] == 0x8D and data[i+3] == 0x94 and data[i+4] == 0x11:
            lo = data[i+1]
            # Now scan forward for LDA #hi; STA &1195 within ~12 bytes
            for j in range(i + 5, min(i + 20, len(data) - 4)):
                if data[j] == 0xA9 and data[j+2] == 0x8D and data[j+3] == 0x95 and data[j+4] == 0x11:
                    hi = data[j+1]
                    target = (hi << 8) | lo
                    sites.append((base + i, lo, hi, target, j - i))
                    break
        i += 1
    return sites


def lookup_label(addr: int, graphix_labels: dict) -> str:
    """Categorize what `addr` likely refers to."""
    if addr in graphix_labels:
        return f"GRAPHIX:{graphix_labels[addr]}"
    if 0x3680 <= addr < 0x4A00:
        # In GRAPHIX range but no named label
        prev = max((a for a in graphix_labels if a <= addr), default=None)
        if prev is not None:
            return f"GRAPHIX:{graphix_labels[prev]}+&{addr-prev:X}"
        return f"GRAPHIX:?&{addr:04X}"
    if 0x4A00 <= addr < 0x5800:
        return f"LEVD1:&{addr:04X}"
    if 0x7380 <= addr < 0x8000:
        return f"LEVD2/3:&{addr:04X}"
    if 0x5800 <= addr < 0x7100:
        return f"MODE5_SCREEN:&{addr:04X}"
    if addr == 0x7D80:
        return "ERASE_BRUSH"
    return f"?&{addr:04X}"


def scan_zp_ptr(data: bytes, base: int):
    """Find LDA #lo / STA &zpL paired with LDA #hi / STA &zpL+1 within 12 bytes.
    Restricts to zp addresses (00..FF) and adjacent pairs.
    Returns list of (site, lo, hi, target, zpL)."""
    sites = []
    i = 0
    while i + 7 < len(data):
        if data[i] == 0xA9 and data[i+2] == 0x85:  # LDA # / STA zp
            lo = data[i+1]
            zpL = data[i+3]
            for j in range(i + 4, min(i + 14, len(data) - 3)):
                if data[j] == 0xA9 and data[j+2] == 0x85 and data[j+3] == (zpL + 1) & 0xFF:
                    hi = data[j+1]
                    target = (hi << 8) | lo
                    sites.append((base + i, lo, hi, target, zpL))
                    break
        i += 1
    return sites


def scan_abs_refs(data: bytes, base: int, lo_byte: int, hi_byte: int):
    """Find any 3-byte instruction whose operand bytes are <lo_byte, hi_byte>."""
    # Opcodes with absolute / abs,X / abs,Y / ind,X-ish addressing modes
    # are mostly 3-byte. Just look for any 16-bit operand pattern.
    sites = []
    for i in range(len(data) - 2):
        if data[i+1] == lo_byte and data[i+2] == hi_byte:
            op = data[i]
            sites.append((base + i, op))
    return sites


def main():
    graphix_labels = load_graphix_labels()
    print(f"Loaded {len(graphix_labels)} GRAPHIX labels.\n")

    print("=== Self-modified sprite-source loads (LDA #/STA &1194; LDA #/STA &1195) ===\n")
    print(f"{'Site':>10}  {'binary':<7}  {'lo':>3} {'hi':>3}  {'target':>6}  label")
    print("-" * 80)
    total = 0
    for name, path, base in BINARIES:
        if not os.path.exists(path):
            continue
        data = open(path, "rb").read()
        sites = scan_self_mod(data, base)
        for site_addr, lo, hi, target, dist in sites:
            lbl = lookup_label(target, graphix_labels)
            print(f"  &{site_addr:04X}  {name:<7}  "
                  f"&{lo:02X} &{hi:02X}  &{target:04X}  {lbl}  (dist {dist})")
            total += 1
    print(f"\nTotal self-mod sites: {total}\n")

    # ZP pointer loads — widen to anything that could land in the
    # &4500..&474F unknown_table when offset by Y/X.
    print("=== ZP pointer setups → targets in &4400..&47FF "
          "(could reach unknown_table via (zp),Y) ===\n")
    zp_total = 0
    for name, path, base in BINARIES:
        if not os.path.exists(path):
            continue
        data = open(path, "rb").read()
        sites = scan_zp_ptr(data, base)
        for site_addr, lo, hi, target, zpL in sites:
            if 0x4400 <= target < 0x4800:
                lbl = lookup_label(target, graphix_labels)
                print(f"  &{site_addr:04X}  {name:<7}  "
                      f"&{lo:02X} &{hi:02X}  &{target:04X}  zp=&{zpL:02X}  {lbl}")
                zp_total += 1
    print(f"\nTotal zp-ptr setups in &4400..&47FF: {zp_total}\n")

    # ZP pointer setups → GRAPHIX (excluding &4400..&47FF)
    print("=== ZP pointer setups → other GRAPHIX targets ===\n")
    for name, path, base in BINARIES:
        if not os.path.exists(path):
            continue
        data = open(path, "rb").read()
        sites = scan_zp_ptr(data, base)
        for site_addr, lo, hi, target, zpL in sites:
            if (0x3680 <= target < 0x4400 or 0x4800 <= target < 0x4A00):
                lbl = lookup_label(target, graphix_labels)
                print(f"  &{site_addr:04X}  {name:<7}  "
                      f"&{lo:02X} &{hi:02X}  &{target:04X}  zp=&{zpL:02X}  {lbl}")
    print()

    # Any 16-bit operand reading from &4500..&474F (unknown_table)
    print("=== Any 16-bit operand referencing &4500..&474F ===\n")
    abs_total = 0
    for name, path, base in BINARIES:
        if not os.path.exists(path):
            continue
        data = open(path, "rb").read()
        for target in range(0x4500, 0x4750):
            hits = scan_abs_refs(data, base, target & 0xFF, (target >> 8) & 0xFF)
            for site_addr, op in hits:
                # Filter to actual abs-addressing opcodes (loads, stores, JMP, JSR, etc.)
                # 3-byte opcodes with abs/abs,X/abs,Y addressing — common ones:
                # AD = LDA abs, BD = LDA abs,X, B9 = LDA abs,Y
                # 8D = STA abs, 9D = STA abs,X
                # 2D, 0D, 4D, 6D, CD, ED, etc.
                if op in (0xAD, 0xBD, 0xB9, 0x8D, 0x9D, 0x99,
                          0x2D, 0x0D, 0x4D, 0x6D, 0xCD, 0xED,
                          0x4C, 0x20, 0x6C, 0x2C, 0xEE, 0xCE):
                    print(f"  &{site_addr:04X}  {name:<7}  "
                          f"op=&{op:02X} → &{target:04X}")
                    abs_total += 1
    print(f"\nTotal abs refs into &4500..&474F: {abs_total}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
