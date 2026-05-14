#!/usr/bin/env python3
"""Detokenize a BBC BASIC program file into ASCII source.

BBC BASIC stored programs are line-oriented:
  Each line: 0x0D, line_hi, line_lo, len, tokens..., 0x0D
  Terminated by: 0x0D, 0xFF

Tokens are 0x80..0xFF; some are two-byte (0xC6, 0xC7, 0xC8 + offset for
"function tokens" added in BBC BASIC IV, and 0x8D..."line number"
indirection).

The 0x8D token introduces an encoded line number reference (e.g. GOTO 1000).
It's followed by 3 bytes that decode as follows:
    Let n1,n2,n3 = the three bytes after 0x8D.
    nLo = (n1 << 2) & 0xC0    # bits 7-6 of low byte from bits 5-4 of n1
    Actually the encoding (from BBC BASIC user guide):
       n1 = ((line >> 8) ^ 0x40) & 0xFF? — let's use a known-correct decoder.

We use the standard BBC BASIC encoding:
    Given encoded triple (a, b, c):
      lsb = b ^ ((a << 2) & 0xC0)
      msb = c ^ ((a << 4) & 0xC0)
      line = (msb << 8) | lsb
"""

from __future__ import annotations

import sys


# Token table from BBC BASIC II / IV (most popular BBC versions).
# Tokens &7F-&FF are statement/function tokens.
TOKENS = {
    0x7F: "OTHERWISE", 0x80: "AND", 0x81: "DIV", 0x82: "EOR", 0x83: "MOD",
    0x84: "OR", 0x85: "ERROR", 0x86: "LINE", 0x87: "OFF", 0x88: "STEP",
    0x89: "SPC", 0x8A: "TAB(", 0x8B: "ELSE", 0x8C: "THEN", 0x8D: "<lineref>",
    0x8E: "OPENIN", 0x8F: "PTR",
    0x90: "PAGE", 0x91: "TIME", 0x92: "LOMEM", 0x93: "HIMEM", 0x94: "ABS",
    0x95: "ACS", 0x96: "ADVAL", 0x97: "ASC", 0x98: "ASN", 0x99: "ATN",
    0x9A: "BGET", 0x9B: "COS", 0x9C: "COUNT", 0x9D: "DEG", 0x9E: "ERL",
    0x9F: "ERR",
    0xA0: "EVAL", 0xA1: "EXP", 0xA2: "EXT", 0xA3: "FALSE", 0xA4: "FN",
    0xA5: "GET", 0xA6: "INKEY", 0xA7: "INSTR(", 0xA8: "INT", 0xA9: "LEN",
    0xAA: "LN", 0xAB: "LOG", 0xAC: "NOT", 0xAD: "OPENUP", 0xAE: "OPENOUT",
    0xAF: "PI",
    0xB0: "POINT(", 0xB1: "POS", 0xB2: "RAD", 0xB3: "RND", 0xB4: "SGN",
    0xB5: "SIN", 0xB6: "SQR", 0xB7: "TAN", 0xB8: "TO", 0xB9: "TRUE",
    0xBA: "USR", 0xBB: "VAL", 0xBC: "VPOS", 0xBD: "CHR$", 0xBE: "GET$",
    0xBF: "INKEY$",
    0xC0: "LEFT$(", 0xC1: "MID$(", 0xC2: "RIGHT$(", 0xC3: "STR$", 0xC4: "STRING$(",
    0xC5: "EOF", 0xC6: "AUTO", 0xC7: "DELETE", 0xC8: "LOAD", 0xC9: "LIST",
    0xCA: "NEW", 0xCB: "OLD", 0xCC: "RENUMBER", 0xCD: "SAVE", 0xCE: "EDIT",
    0xCF: "PTR",
    0xD0: "PAGE", 0xD1: "TIME", 0xD2: "LOMEM", 0xD3: "HIMEM", 0xD4: "SOUND",
    0xD5: "BPUT", 0xD6: "CALL", 0xD7: "CHAIN", 0xD8: "CLEAR", 0xD9: "CLOSE",
    0xDA: "CLG", 0xDB: "CLS", 0xDC: "DATA", 0xDD: "DEF", 0xDE: "DIM",
    0xDF: "DRAW",
    0xE0: "END", 0xE1: "ENDPROC", 0xE2: "ENVELOPE", 0xE3: "FOR", 0xE4: "GOSUB",
    0xE5: "GOTO", 0xE6: "GCOL", 0xE7: "IF", 0xE8: "INPUT", 0xE9: "LET",
    0xEA: "LOCAL", 0xEB: "MODE", 0xEC: "MOVE", 0xED: "NEXT", 0xEE: "ON",
    0xEF: "VDU",
    0xF0: "PLOT", 0xF1: "PRINT", 0xF2: "PROC", 0xF3: "READ", 0xF4: "REM",
    0xF5: "REPEAT", 0xF6: "REPORT", 0xF7: "RESTORE", 0xF8: "RETURN",
    0xF9: "RUN", 0xFA: "STOP", 0xFB: "COLOUR", 0xFC: "TRACE", 0xFD: "UNTIL",
    0xFE: "WIDTH", 0xFF: "OSCLI",
}


def decode_lineref(a: int, b: int, c: int) -> int:
    lsb = b ^ ((a << 2) & 0xC0)
    msb = c ^ ((a << 4) & 0xC0)
    return (msb << 8) | lsb


def detoken_line(payload: bytes) -> str:
    out = []
    i = 0
    while i < len(payload):
        ch = payload[i]
        if ch == 0x8D:
            if i + 3 < len(payload):
                ln = decode_lineref(payload[i + 1], payload[i + 2], payload[i + 3])
                out.append(str(ln))
                i += 4
                continue
            else:
                out.append("<truncated lineref>")
                i = len(payload)
                continue
        if ch >= 0x7F:
            out.append(TOKENS.get(ch, f"<{ch:02X}>"))
        elif ch == 0x22:  # quote — copy literal string
            out.append('"')
            i += 1
            while i < len(payload) and payload[i] != 0x22:
                b = payload[i]
                if 32 <= b < 127:
                    out.append(chr(b))
                else:
                    out.append(f"<{b:02X}>")
                i += 1
            if i < len(payload):
                out.append('"')
        elif ch == 0x0D:
            break
        else:
            if 32 <= ch < 127:
                out.append(chr(ch))
            else:
                out.append(f"<{ch:02X}>")
        i += 1
    return "".join(out)


def find_first_line(data: bytes) -> int:
    """Skip any leading non-program bytes (some saved BASIC files have garbage
    prefix from prior memory contents). Find the first byte that looks like
    the start of a BASIC line: 0x0D <hi> <lo> <len> with reasonable values."""
    for i in range(len(data) - 4):
        if data[i] != 0x0D:
            continue
        line_no = (data[i + 1] << 8) | data[i + 2]
        line_len = data[i + 3]
        if line_len == 0 or line_len > 80:
            continue
        if line_no == 0 or line_no > 32767:
            continue
        # Sanity-check the line ends with another 0x0D or end-of-program
        end = i + line_len
        if end < len(data) and data[end] not in (0x0D, 0xFF):
            continue
        return i
    return 0


def detoken_program(data: bytes) -> str:
    out = []
    start = find_first_line(data)
    if start > 0:
        out.append(f"# (skipped {start:#x} bytes of leading garbage)")
    i = start
    while i < len(data):
        if data[i] != 0x0D:
            out.append(f"# unexpected byte at {i:#x}: {data[i]:#x}")
            break
        if i + 1 >= len(data):
            break
        if data[i + 1] == 0xFF:
            break  # end of program marker
        if i + 3 >= len(data):
            out.append(f"# truncated at {i:#x}")
            break
        line_no = (data[i + 1] << 8) | data[i + 2]
        line_len = data[i + 3]
        payload = data[i + 4:i + line_len]
        out.append(f"{line_no:5d} {detoken_line(payload)}")
        i += line_len
    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: bbcbasic_detoken.py <file>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        data = f.read()

    print(detoken_program(data))


if __name__ == "__main__":
    main()
