#!/usr/bin/env python3
"""Prepare app icon: defringe + rounded corners with transparent outside."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

# macOS / iOS squircle-like corner radius
CORNER_RADIUS_RATIO = 0.2237


def _cream_sample(img: Image.Image) -> tuple[int, int, int]:
    w, h = img.size
    return img.convert("RGB").getpixel((w // 2, h - 90))


def defringe_rgb(img: Image.Image) -> None:
    w, h = img.size
    cream = _cream_sample(img)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(img, seed, cream, thresh=35)


def apply_round_alpha(img: Image.Image) -> Image.Image:
    w, h = img.size
    radius = int(min(w, h) * CORNER_RADIUS_RATIO)
    rgba = img.convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    rgba.putalpha(mask)
    return rgba


def process(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    defringe_rgb(img)
    return apply_round_alpha(img)


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "assets/app-icon.png")
    out = process(target.resolve())
    out.save(target, format="PNG")
    print(f"icon ready {target} (rounded alpha, radius≈{CORNER_RADIUS_RATIO:.0%})")
