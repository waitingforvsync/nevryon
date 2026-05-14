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
