"""Generate the app icon (leetcode_cli/icon.png and icon.ico) with no deps.

A rounded blue square with a white checkmark. Re-run to regenerate:

    py tools/make_icon.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZE = 64
OUT_DIR = Path(__file__).resolve().parent.parent / "leetcode_cli"

# Colours (R, G, B)
BG = (47, 111, 235)       # accent blue
BG_EDGE = (31, 95, 208)   # slightly darker edge
CHECK = (255, 255, 255)


def _dist_point_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = x1 + t * dx, y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _in_rounded_rect(x, y, w, h, r, margin):
    x0, y0, x1, y1 = margin, margin, w - 1 - margin, h - 1 - margin
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def build_pixels():
    w = h = SIZE
    # checkmark polyline points (scaled to 64)
    seg = [(15, 34, 27, 46), (27, 46, 49, 19)]
    thick = 5.0
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            inside = _in_rounded_rect(x, y, w, h, r=14, margin=4)
            on_check = any(_dist_point_seg(x, y, *s) <= thick for s in seg)
            if inside and on_check:
                row.append((*CHECK, 255))
            elif inside:
                # subtle vertical shade for depth
                edge = _in_rounded_rect(x, y, w, h, r=14, margin=4) and not \
                    _in_rounded_rect(x, y, w, h, r=12, margin=6)
                row.append((*(BG_EDGE if edge else BG), 255))
            else:
                row.append((0, 0, 0, 0))
        rows.append(row)
    return rows


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def encode_png(rows) -> bytes:
    h = len(rows)
    w = len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter type 0
        for (r, g, b, a) in row:
            raw += bytes((r, g, b, a))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (sig + _png_chunk(b"IHDR", ihdr) +
            _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            _png_chunk(b"IEND", b""))


def wrap_ico(png: bytes) -> bytes:
    # ICONDIR + one ICONDIRENTRY pointing at a PNG-encoded image
    icondir = struct.pack("<HHH", 0, 1, 1)
    w = SIZE if SIZE < 256 else 0
    entry = struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png), 22)
    return icondir + entry + png


def main() -> int:
    rows = build_pixels()
    png = encode_png(rows)
    (OUT_DIR / "icon.png").write_bytes(png)
    (OUT_DIR / "icon.ico").write_bytes(wrap_ico(png))
    print(f"wrote {OUT_DIR / 'icon.png'} ({len(png)} bytes)")
    print(f"wrote {OUT_DIR / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
