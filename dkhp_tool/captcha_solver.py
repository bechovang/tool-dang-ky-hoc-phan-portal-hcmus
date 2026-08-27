"""OCR solver for the HCMUS portal 6-digit captcha (Handlers/Captcha.ashx).

The captcha mixes normal-size and tiny "superscript" digits on patterned
backgrounds; whole-image OCR skips the small glyphs. We segment each glyph
with connected components (clustering broken strokes by x-overlap), rescale
every glyph to a uniform 64px height, and classify glyphs individually with
ddddocr. Returns a 6-digit string, or None when no confident candidate exists.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import cv2
import ddddocr
import numpy as np

_ENGINES: list = []

# common OCR misreads -> digits (the captcha is digits-only)
DIGIT_MAP = {
    "O": "0", "o": "0", "D": "0", "U": "0", "u": "0",
    "I": "1", "l": "1", "i": "1", "L": "1", "|": "1",
    "Z": "2", "z": "2",
    "A": "4", "a": "4",
    "S": "5", "s": "5",
    "G": "6", "b": "6",
    "T": "7", "?": "7",
    "B": "8",
    "g": "9", "q": "9",
}


def _engines() -> list:
    global _ENGINES
    if not _ENGINES:
        _ENGINES = [
            ddddocr.DdddOcr(show_ad=False),
            ddddocr.DdddOcr(show_ad=False, beta=True),
        ]
    return _ENGINES


def _glyphs(bw: np.ndarray, h: int, w: int):
    """Cluster ink components into glyph boxes, left-to-right."""
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    comps = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= max(8, h * w * 0.0008)]
    if not 4 <= len(comps) <= 30:
        return None
    boxes = sorted(
        (stats[i, 0], stats[i, 1], stats[i, 0] + stats[i, 2], stats[i, 1] + stats[i, 3])
        for i in comps
    )
    clusters = []
    for b in boxes:
        if clusters and b[0] < clusters[-1][2] - 2:  # x-overlap -> same glyph
            c = clusters[-1]
            c[0], c[1] = min(c[0], b[0]), min(c[1], b[1])
            c[2], c[3] = max(c[2], b[2]), max(c[3], b[3])
        else:
            clusters.append(list(b))
    return [c for c in clusters
            if (c[2] - c[0]) >= 3 and (c[3] - c[1]) >= 5 and (c[2] - c[0]) < w * 0.6]


def _classify(bw: np.ndarray, c, pad: int = 2) -> str:
    crop = bw[max(0, c[1] - pad):c[3] + pad, max(0, c[0] - pad):c[2] + pad]
    if crop.size == 0:
        return ""
    ch, cw = crop.shape
    crop = cv2.resize(crop, (max(1, int(cw * 64 / max(1, ch))), 64),
                      interpolation=cv2.INTER_NEAREST)
    ch, cw = crop.shape
    canvas = np.zeros((80, 80), np.uint8)
    y0, x0 = (80 - ch) // 2, max(0, (80 - cw) // 2)
    x1 = min(80, x0 + cw)
    canvas[y0:y0 + ch, x0:x1] = crop[:, :x1 - x0]
    _ok, png = cv2.imencode(".png", canvas * 255)
    for eng in _engines():
        r = eng.classification(png.tobytes())
        r = "".join(DIGIT_MAP.get(x, x) for x in r if x.strip())
        if len(r) == 1 and r.isdigit():
            return r
    return r or "?"


def solve(png_bytes: bytes) -> str | None:
    """Return the 6-digit captcha text, or None if no confident candidate."""
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, w = img.shape
    fallback = []
    for th in (90, 110, 130, 150, 170):
        for invert in (False, True):
            bw = (img < th if not invert else img >= th).astype(np.uint8)
            if not 0.02 <= bw.mean() <= 0.25:
                continue
            clusters = _glyphs(bw, h, w)
            if not clusters:
                continue
            chars = [_classify(bw, c) for c in clusters]
            digits = [c for c in chars if c.isdigit()]
            junk = [c for c in chars if not c.isdigit()]
            if len(digits) == 6 and not junk:
                return "".join(digits)
            if len(digits) == 6 and len(junk) == 1:
                fallback.append("".join(digits))
    return fallback[0] if fallback else None
