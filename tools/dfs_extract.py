#!/usr/bin/env python3
"""Parse and extract files from a BBC Micro DFS SSD disk image.

DFS Catalog format (single sided):
  Sector 0 (256 bytes):
    Bytes 0-7   : Disk title (chars 1-8), padded with spaces
    Bytes 8-247 : Up to 31 file entries, each 8 bytes
      0-6 : filename (7 chars, space padded)
      7   : directory letter; bit 7 = locked
  Sector 1 (256 bytes):
    Bytes 0-3   : Disk title (chars 9-12)
    Byte 4      : BCD cycle number
    Byte 5      : Number of files * 8 (i.e. used catalog bytes from offset 8)
    Byte 6      : bits 0-1: total sectors bits 9-8
                  bits 4-5: !BOOT option (0=none, 1=LOAD, 2=RUN, 3=EXEC)
                  bits 6-7: unused (hardware-specific)
    Byte 7      : total sectors bits 7-0
    Bytes 8-247 : File metadata, 8 bytes each (parallel to sector 0 entries)
      0-1 : load address LSB,MSB (lo word)
      2-3 : exec address LSB,MSB (lo word)
      4-5 : length LSB,MSB (lo word)
      6   : Watford / 1770 DFS encoding (the variant used by the Nevryon disk):
              bits 0-1: start sector bits 9-8
              bits 2-3: load address bits 17-16
              bits 4-5: length bits 17-16
              bits 6-7: exec address bits 17-16
            Note: Acorn DFS encoding is different (load_hi at bits 0-1,
            start_hi at bits 6-7). When in doubt, decide by inspecting
            actual sector contents — the Watford encoding fits this disk.
      7   : start sector LSB
"""

from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass


SECTOR_SIZE = 256


@dataclass
class DFSFile:
    name: str
    directory: str
    locked: bool
    load_addr: int
    exec_addr: int
    length: int
    start_sector: int
    data: bytes

    @property
    def full_name(self) -> str:
        return f"{self.directory}.{self.name}"

    @property
    def safe_filename(self) -> str:
        # filesystem-safe name preserving dir letter
        return f"{self.directory}.{self.name}".replace("/", "_")


def parse_dfs(image: bytes) -> tuple[str, int, list[DFSFile]]:
    s0 = image[0:SECTOR_SIZE]
    s1 = image[SECTOR_SIZE:2 * SECTOR_SIZE]

    title = (s0[0:8] + s1[0:4]).rstrip(b"\x00 ").decode("ascii", errors="replace")
    cycle = s1[4]
    num_files = s1[5] // 8
    boot_option = (s1[6] >> 4) & 0x3
    total_sectors = ((s1[6] & 0x3) << 8) | s1[7]

    files: list[DFSFile] = []
    for i in range(num_files):
        off = 8 + i * 8
        name_bytes = s0[off:off + 7]
        # Filenames are space-padded ASCII
        name = name_bytes.rstrip(b" ").decode("ascii", errors="replace")
        dir_byte = s0[off + 7]
        locked = bool(dir_byte & 0x80)
        directory = chr(dir_byte & 0x7F)

        m = s1[off:off + 8]
        load_lo = m[0] | (m[1] << 8)
        exec_lo = m[2] | (m[3] << 8)
        length_lo = m[4] | (m[5] << 8)
        hi = m[6]
        # Watford / 1770-DFS byte 6 packing (matches Nevryon disk)
        start_hi = hi & 0x03
        load_hi = (hi >> 2) & 0x03
        length_hi = (hi >> 4) & 0x03
        exec_hi = (hi >> 6) & 0x03
        start_sector = (start_hi << 8) | m[7]

        load_addr = (load_hi << 16) | load_lo
        exec_addr = (exec_hi << 16) | exec_lo
        length = (length_hi << 16) | length_lo

        # Sign-extend host-addressable load/exec: if top bit set in 18-bit field,
        # this is the BBC convention for "host RAM" (vs. tube/second processor).
        # Common pattern: 0x3xxxx means host. We'll leave the raw value alone.

        data_off = start_sector * SECTOR_SIZE
        data = image[data_off:data_off + length]

        files.append(DFSFile(
            name=name,
            directory=directory,
            locked=locked,
            load_addr=load_addr,
            exec_addr=exec_addr,
            length=length,
            start_sector=start_sector,
            data=data,
        ))

    return title, total_sectors, files, cycle, boot_option


def main():
    if len(sys.argv) < 2:
        print("Usage: dfs_extract.py <disk.ssd> [out_dir]", file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None

    with open(image_path, "rb") as f:
        image = f.read()

    title, total_sectors, files, cycle, boot_option = parse_dfs(image)
    boot_names = ["none", "LOAD", "RUN", "EXEC"]

    print(f"Disk title  : {title!r}")
    print(f"Cycle       : {cycle:02x}")
    print(f"Total sectors: {total_sectors}  ({total_sectors * SECTOR_SIZE} bytes)")
    print(f"Image size  : {len(image)} bytes")
    print(f"Boot option : {boot_option} ({boot_names[boot_option]})")
    print(f"Files       : {len(files)}")
    print()
    print(f"{'Filename':14} {'Load':>8} {'Exec':>8} {'Length':>8} {'Sector':>6}  L")
    print("-" * 60)

    for f in sorted(files, key=lambda x: x.start_sector):
        lock = "L" if f.locked else " "
        print(f"{f.full_name:14} {f.load_addr:08X} {f.exec_addr:08X} "
              f"{f.length:8d} {f.start_sector:6d}  {lock}")

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        # Also write a manifest
        manifest_lines = []
        for f in files:
            path = os.path.join(out_dir, f.safe_filename)
            with open(path, "wb") as out:
                out.write(f.data)
            manifest_lines.append(
                f"{f.full_name}\t{f.load_addr:06X}\t{f.exec_addr:06X}\t"
                f"{f.length}\t{f.start_sector}\t{'L' if f.locked else ''}"
            )
        with open(os.path.join(out_dir, "_manifest.tsv"), "w") as out:
            out.write("# name\tload\texec\tlength\tstart_sector\tlocked\n")
            out.write("\n".join(manifest_lines) + "\n")
        print(f"\nExtracted {len(files)} files to {out_dir}/")


if __name__ == "__main__":
    main()
