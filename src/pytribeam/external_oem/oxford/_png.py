"""Minimal PNG encoder (grayscale, 8-bit) so pattern previews need no imaging library."""

import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_gray8(image) -> bytes:
    """Encode a 2-D array as an 8-bit grayscale PNG.

    uint8 data is written as-is; anything else is min-max scaled to 0..255
    (constant images become black).
    """
    import numpy as np

    a = np.asarray(image)
    if a.ndim != 2:
        raise ValueError("expected a 2-D image, got shape %s" % (a.shape,))
    if a.dtype != np.uint8:
        a = a.astype(np.float64)
        lo, hi = np.nanmin(a), np.nanmax(a)
        a = np.zeros(a.shape) if hi <= lo else (a - lo) * (255.0 / (hi - lo))
        a = np.nan_to_num(a).round().clip(0, 255).astype(np.uint8)
    h, w = a.shape
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def save_gray8(image, path: str) -> str:
    with open(path, "wb") as f:
        f.write(encode_gray8(image))
    return path
