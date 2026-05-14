#!/usr/bin/env python3
"""One-shot helper: prefix GRAPHIX sprite-atlas labels with `gfx_`,
then scan CODE/CODE2/CODE3 for `LDA #lo; STA &1194; LDA #hi; STA &1195`
self-modified-operand pairs and synthesise `immediate_overrides`
entries for each that resolve to `LO(gfx_<name> [+ &XX])` /
`HI(gfx_<name> [+ &XX])`. Writes the updated cfgs in place.

The GRAPHIX label prefix only affects entries in the sprite atlas
range (&3680..&48FF); IRQ-handler / palette labels at &4900+ keep
their existing names.

Also reports the sites whose target falls into the middle of a
named sprite (offset > 0) so they can be inspected manually.
"""

from __future__ import annotations

import json
import os
import sys
from collections import OrderedDict


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Address ranges relevant to the override:
GRAPHIX_ATLAS_END = 0x4900   # sprite atlas ends here; &4900+ is IRQ
GRAPHIX_BASE      = 0x3680

# Targets seen in CODE/CODE2/CODE3 self-mod sites that aren't in
# GRAPHIX — declare these in the master so overrides resolve.
NON_GFX_TARGETS = {
    0x4E80: "lev_player_sprite",   # LEVD1 player ship
    0x7D00: "lev_erase_brush",      # LEVD2 zero region start
    # Other LEVD targets are reached as offsets from lev_erase_brush
    # (&7D80 = +&80, &7DB0 = +&B0, &7E00 = +&100, &7E02 = +&102)
}

# Other one-off targets that aren't well-named yet — leave as raw hex.
RAW_TARGETS_OK: set[int] = {0x4C20, 0x4C68}


BINARIES = [
    ("CODE",   "extracted/$.CODE",   0x1100, "disasm/CODE.cfg.json"),
    ("CODE2",  "extracted/$.CODE2",  0x2800, "disasm/CODE2.cfg.json"),
    ("CODE3",  "extracted/$.CODE3",  0x3300, "disasm/CODE3.cfg.json"),
]


def load_json(path):
    with open(path) as f:
        text = f.read()
    return json.loads(text)


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def renamed(name: str) -> str:
    """Return the gfx_-prefixed form of a label name unless it already
    has the prefix."""
    return name if name.startswith("gfx_") else f"gfx_{name}"


def prefix_graphix_labels(cfg_path: str) -> dict:
    """Add `gfx_` prefix to all labels in the sprite-atlas range and
    return {old_name: new_name} mapping for reporting."""
    cfg = load_json(cfg_path)
    mapping: dict[str, str] = {}
    new_labels = OrderedDict()
    for k, v in cfg["labels"].items():
        addr = int(k, 0)
        if GRAPHIX_BASE <= addr < GRAPHIX_ATLAS_END:
            new = renamed(v)
            if new != v:
                mapping[v] = new
            new_labels[k] = new
        else:
            new_labels[k] = v
    cfg["labels"] = new_labels
    write_json(cfg_path, cfg)
    return mapping


def scan_self_mod(data: bytes, base: int):
    """Find LDA #lo / STA &1194 followed (within ~12 bytes) by LDA #hi / STA &1195.
    Returns (lo_pc, hi_pc, lo, hi, target, dist)."""
    sites = []
    i = 0
    while i + 9 < len(data):
        if (data[i] == 0xA9 and data[i+2] == 0x8D
                and data[i+3] == 0x94 and data[i+4] == 0x11):
            lo_byte = data[i+1]
            for j in range(i + 5, min(i + 20, len(data) - 4)):
                if (data[j] == 0xA9 and data[j+2] == 0x8D
                        and data[j+3] == 0x95 and data[j+4] == 0x11):
                    hi_byte = data[j+1]
                    target = (hi_byte << 8) | lo_byte
                    sites.append((base + i, base + j, lo_byte, hi_byte,
                                  target, j - i))
                    break
        i += 1
    return sites


def make_expr(target: int, gfx_labels: dict) -> str | None:
    """Build the LO/HI base expression for a target, e.g. `gfx_text_get_ready + &80`.
    Returns None if no suitable label exists (caller will leave the raw immediate)."""
    if target in gfx_labels:
        return gfx_labels[target]
    # offset into nearest preceding GRAPHIX label?
    candidates = [a for a in gfx_labels if a <= target and a < GRAPHIX_ATLAS_END]
    if candidates:
        base = max(candidates)
        offset = target - base
        if offset < 0x200:                     # don't span more than 512 B from a base
            return f"{gfx_labels[base]} + &{offset:X}"
    if target in NON_GFX_TARGETS:
        return NON_GFX_TARGETS[target]
    # near a non-GFX target?
    near = [(a, n) for a, n in NON_GFX_TARGETS.items() if a <= target < a + 0x200]
    if near:
        a, n = max(near)
        return f"{n} + &{target - a:X}"
    if target in RAW_TARGETS_OK:
        return None
    return None


def main():
    os.chdir(REPO)
    # Step 1: prefix labels in GRAPHIX.cfg.json
    print("=== prefixing GRAPHIX labels with `gfx_` ===")
    mapping = prefix_graphix_labels("disasm/GRAPHIX.cfg.json")
    for old, new in sorted(mapping.items()):
        print(f"  {old}  →  {new}")
    print(f"Renamed {len(mapping)} GRAPHIX labels.\n")

    # Step 2: load updated GRAPHIX labels for resolving overrides
    g_cfg = load_json("disasm/GRAPHIX.cfg.json")
    gfx_labels = {int(k, 0): v for k, v in g_cfg["labels"].items()
                  if GRAPHIX_BASE <= int(k, 0) < GRAPHIX_ATLAS_END}

    # Step 3: scan each binary; build immediate_overrides for each cfg
    print("=== generating immediate_overrides per binary ===")
    offset_cases: list[str] = []
    raw_cases:    list[str] = []
    for name, path, bin_base, cfg_path in BINARIES:
        if not os.path.exists(path) or not os.path.exists(cfg_path):
            continue
        data = open(path, "rb").read()
        sites = scan_self_mod(data, bin_base)
        cfg = load_json(cfg_path)
        overrides = OrderedDict(cfg.get("immediate_overrides", {}))
        added = 0
        for lo_pc, hi_pc, lo, hi, target, dist in sites:
            expr = make_expr(target, gfx_labels)
            if expr is None:
                raw_cases.append(f"  {name} @ &{lo_pc:04X}  →  &{target:04X}  (left as raw hex)")
                continue
            if " + " in expr:
                offset_cases.append(
                    f"  {name} @ &{lo_pc:04X}  →  &{target:04X}  ({expr})")
            overrides[f"0x{lo_pc:04X}"] = f"LO({expr})"
            overrides[f"0x{hi_pc:04X}"] = f"HI({expr})"
            added += 2
        # Sort by key for deterministic output
        cfg["immediate_overrides"] = OrderedDict(
            sorted(overrides.items(), key=lambda kv: int(kv[0], 0)))
        write_json(cfg_path, cfg)
        print(f"  {name}: {added} override entries added to {cfg_path}")

    print()
    if offset_cases:
        print("=== Offset-into-named cases (worth a closer look) ===")
        for s in offset_cases:
            print(s)
        print()
    if raw_cases:
        print("=== Sites left as raw hex (no label/expr matched) ===")
        for s in raw_cases:
            print(s)


if __name__ == "__main__":
    main()
