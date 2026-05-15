#!/usr/bin/env bash
# Build all four Nevryon runtime binaries from disasm/Nevryon.6502
# and verify they match the originals byte-for-byte.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p build

if ! command -v beebasm >/dev/null 2>&1; then
    echo "beebasm not found in PATH — install BeebAsm (https://github.com/stardot/beebasm)" >&2
    exit 1
fi

echo "Regenerating per-binary .6502 sources from extracted/ + cfg ..."
# Cumulative master: each binary inherits auto-promoted externs from
# the binaries that get INCLUDE'd before it, so the same `zp_XX` /
# `data_XXXX` slot is declared exactly once across the whole build.
master_tmp="$(mktemp)"
cumulative_tmp="$(mktemp)"
cp disasm/Nevryon.6502 "$master_tmp"
for spec in 'CODE:0x1100' 'CODE2:0x2800' 'CODE3:0x3300' 'GRAPHIX:0x3680'; do
    name="${spec%:*}"; base="${spec#*:}"
    python3 tools/disasm6502.py "extracted/\$.$name" --base "$base" \
        --master "$master_tmp" \
        --config "disasm/$name.cfg.json" -o "disasm/$name.6502" >/dev/null
    cat "$master_tmp" "disasm/$name.6502" > "$cumulative_tmp"
    mv "$cumulative_tmp" "$master_tmp"
done
rm -f "$master_tmp"

echo "Building from disasm/Nevryon.6502 ..."
( cd disasm && beebasm -i Nevryon.6502 ) >/dev/null

echo "Verifying byte-identity against extracted/ ..."
status=0
for name in CODE CODE2 CODE3 GRAPHIX; do
    if cmp -s "build/$name" "extracted/\$.$name"; then
        printf "  %-8s BYTE-IDENTICAL\n" "$name"
    else
        printf "  %-8s MISMATCH\n" "$name"
        status=1
    fi
done

if [ "$status" -eq 0 ]; then
    echo "All four binaries match the originals."
fi
exit "$status"
