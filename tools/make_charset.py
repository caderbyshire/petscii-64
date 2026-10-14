"""Build the redistributable PETSCII-inspired fallback; no Commodore ROM input."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'assets/font8x8_basic.h').read_text()
ascii_rows = [bytes(int(h, 16) for h in re.findall(r'0x([0-9A-Fa-f]{2})', row))
              for row in re.findall(r'\{([^{}]+)\}', source)]
assert len(ascii_rows) == 128 and all(len(row) == 8 for row in ascii_rows)


def reverse(value):
    return int(f'{value:08b}'[::-1], 2)


glyphs = [bytes(8) for _ in range(256)]
for code in range(64):
    ascii_code = code + 64 if code < 32 else code
    glyphs[code] = bytes(reverse(b) for b in ascii_rows[ascii_code])


def shape(code, predicate):
    glyphs[code] = bytes(sum(128 >> x for x in range(8) if predicate(x, y))
                         for y in range(8))


# Geometric primitives drawn specifically for this app in C64 screen-code slots.
shape(77, lambda x, y: abs(x-y) <= 1)
shape(78, lambda x, y: abs(x+y-7) <= 1)
shape(81, lambda x, y: (x-3.5)**2 + (y-3.5)**2 <= 10)
shape(86, lambda x, y: abs(x-y) <= 1 or abs(x+y-7) <= 1)
shape(90, lambda x, y: abs(x-3.5) + abs(y-3.5) <= 3.5)
shape(100, lambda x, y: y == 7)
shape(102, lambda x, y: (x//2 + y//2) % 2 == 0)
for code in range(128):
    glyphs[128+code] = bytes(b ^ 255 for b in glyphs[code])
output = ROOT / 'assets/petscii-inspired.bin'
output.write_bytes(b''.join(glyphs))
print(output)
