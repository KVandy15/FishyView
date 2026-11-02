"""Draw the FishyView icon and write assets/FishyView.ico."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "FishyView.ico"


def png(rgba: np.ndarray) -> bytes:
    height, width, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"".join([
        b"\x89PNG\r\n\x1a\n",
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        chunk(b"IDAT", zlib.compress(raw, 9)),
        chunk(b"IEND", b""),
    ])


def draw(size: int) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    cx = (size - 1) / 2
    radius = np.sqrt((xx - cx) ** 2 + (yy - cx) ** 2)
    img = np.zeros((size, size, 4), np.uint8)
    margin = size * 0.08
    inside = (xx >= margin) & (xx < size - margin) & (yy >= margin) & (yy < size - margin)
    img[inside] = (28, 34, 44, 255)
    img[radius < size * 0.34] = (232, 236, 240, 255)
    img[radius < size * 0.27] = (18, 28, 38, 255)
    img[radius < size * 0.08] = (120, 190, 220, 255)
    return img


def ico(images: list[tuple[int, bytes]]) -> bytes:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = b""
    blobs = b""
    for size, data in images:
        shown = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", shown, shown, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    return header + entries + blobs


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [(size, png(draw(size))) for size in (16, 32, 48, 256)]
    OUT.write_bytes(ico(images))
    print(OUT)


if __name__ == "__main__":
    main()
