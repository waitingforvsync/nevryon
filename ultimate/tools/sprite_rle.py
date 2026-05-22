"""Sprite RLE -- scheme C (per-sprite 5+3 with XOR encoding).

The canonical scheme-C library for the Nevryon Ultimate remake, used
by the per-asset encoders in this directory. Mirrors the parent
repo's `../../tools/sprite_rle.py` (the version the survey numbers in
`../../docs/sprite_rle_notes.md` were produced from), trimmed to the
pieces we actually depend on: spec-exact encoder + decoder + flag
picker. The remake's smarter encoders (e.g. encode_tiles.py) call
into the decoder here for round-trip verification.

Scheme summary, from `../../docs/sprite_rle_notes.md`:

* Each sprite picks its own 5-bit FLAG so that no source byte has
  top-5-bits == FLAG. `FLAG_BYTE = FLAG << 3`.
* Encoded stream byte b:
    b <  8  ->  run code. count = b + 3 (= 3..10). The NEXT byte is
                the run's source value, shipped RAW (NOT eor'd).
    b >= 8  ->  literal. Emit (b EOR FLAG_BYTE) once.
* Runs never cross a sprite-column (32-byte) boundary, so each
  column's encoded sub-stream is independently decodable.

The decoder + flag picker here are spec-conformant and used for
round-trip verification of every emitted sprite.
"""

from __future__ import annotations


# 4x32 column-major sprites are the bulk of Nevryon's catalog
# (tiles + hazards + explosion frames). Smaller categories (player,
# enemy, flame, pickup) use trim + raw blit and don't go through this
# library; see ../docs/sprite_rle_notes.md "Variable-shape sprites
# with border trim" for the rationale.
SPRITE_W_COLS    = 4
SPRITE_COL_BYTES = 32                              # = MODE 5 sprite height
SPRITE_SIZE      = SPRITE_W_COLS * SPRITE_COL_BYTES   # = 128


def pick_flag(sprite: bytes) -> int:
    """Pick a 5-bit FLAG such that no source byte has top-5-bits == FLAG.

    Returns the first such FLAG in 0..31. Raises ValueError if all 32
    prefixes are in use -- which empirically never happens for the
    4x32 sprite corpus (every sprite has at least 3 free prefixes).
    """
    used = {b >> 3 for b in sprite}
    for f in range(32):
        if f not in used:
            return f
    raise ValueError("sprite uses all 32 possible 5-bit prefixes -- no FLAG available")


def encode_column(col: bytes, flag_byte: int) -> bytes:
    """Spec-exact column encoder. Runs are 3..10 bytes, bounded to the
    column. Residue after the last full-10 run spills as literals if
    < 3, otherwise emits as one final short run.

    The remake's encoders override this with an all-RLE long-run split
    (see e.g. encode_tiles.encode_column) -- keeping this here as the
    documented spec-baseline + reference implementation."""
    out = bytearray()
    i = 0
    n = len(col)
    while i < n:
        j = i
        while j < n and j - i < 10 and col[j] == col[i]:
            j += 1
        run_len = j - i
        if run_len >= 3:
            out.append(run_len - 3)
            out.append(col[i])
            i = j
        else:
            out.append(col[i] ^ flag_byte)
            i += 1
    return bytes(out)


def encode_sprite(sprite: bytes, w_cols: int = SPRITE_W_COLS,
                  h_lines: int = SPRITE_COL_BYTES,
                  flag: int | None = None
                  ) -> tuple[int, bytes, list[int]]:
    """Spec-exact per-sprite encoder. Returns (flag, encoded_stream,
    col_offsets) -- stream does NOT include the leading flag header
    byte (the remake passes the flag via a separate equate, not in-band).
    col_offsets[c] = offset of column c's data within encoded_stream."""
    assert len(sprite) == w_cols * h_lines, (len(sprite), w_cols, h_lines)
    if flag is None:
        flag = pick_flag(sprite)
    flag_byte = flag << 3
    out = bytearray()
    col_offsets: list[int] = []
    for c in range(w_cols):
        col_offsets.append(len(out))
        col = sprite[c * h_lines:(c + 1) * h_lines]
        out.extend(encode_column(col, flag_byte))
    return flag, bytes(out), col_offsets


def decode_column(stream: bytes, flag_byte: int,
                  target_len: int = SPRITE_COL_BYTES
                  ) -> tuple[bytes, int]:
    """Decode one column from `stream`. Returns (decoded, bytes_consumed)."""
    out = bytearray()
    i = 0
    while len(out) < target_len:
        b = stream[i]
        i += 1
        if b < 8:
            count = b + 3
            value = stream[i]      # raw -- encoder ships raw
            i += 1
            out.extend([value] * count)
        else:
            out.append(b ^ flag_byte)
    if len(out) != target_len:
        raise ValueError(f"column decode overshot: got {len(out)} of {target_len}")
    return bytes(out), i


def decode_sprite(flag: int, stream: bytes,
                  n_cols: int = SPRITE_W_COLS,
                  col_bytes: int = SPRITE_COL_BYTES) -> bytes:
    """Decode a full sprite from the concatenated per-column streams.
    `stream` is what the spec encoder returns (no leading flag byte).
    Used by round-trip checks: encode_xxx then assert decode == input."""
    flag_byte = flag << 3
    out = bytearray()
    i = 0
    for _ in range(n_cols):
        col, consumed = decode_column(stream[i:], flag_byte, col_bytes)
        out.extend(col)
        i += consumed
    return bytes(out)
