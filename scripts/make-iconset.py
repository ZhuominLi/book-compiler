#!/usr/bin/env python3
"""Build AppIcon.iconset from RGBA app-icon.png."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main() -> None:
    src = Path(sys.argv[1])
    iconset = Path(sys.argv[2])
    iconset.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGBA")
    for name, px in SIZES.items():
        img.resize((px, px), Image.Resampling.LANCZOS).save(iconset / name, format="PNG")
    print(f"iconset → {iconset}")


if __name__ == "__main__":
    main()
