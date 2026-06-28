#!/usr/bin/env python3
"""UI kit helper — tokens + sprite coords + trimmed reference sections.

One composite sheet cannot yield production PNGs; use Figma exports for final assets.
Outputs what *is* usable: design tokens, CSS sprites, reference blocks.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ui" / "element"
DEFAULT_SRC = OUT / "_source" / "ui-kit-full.png"

TOKENS = {
    "colors": {
        "bean_green": "#ABC27A",
        "bean_yellow": "#F6D786",
        "bean_cream": "#FFE9C5",
        "bean_sand": "#EBD7B4",
        "bean_brown": "#8B6E4E",
    },
    "slogan_zh": "让阅读成为一件轻松的事",
    "name_zh": "懒豆阅读",
    "name_en": "beanread",
}

# Reference blocks — exclude section titles (「功能图标」「状态插画」等)
SECTIONS: dict[str, tuple[int, int, int, int]] = {
    "reference/brand-block.png": (20, 42, 402, 220),
    "reference/status-illustrations-row.png": (402, 65, 1018, 164),
    "reference/onboarding-row.png": (402, 175, 1018, 332),
    "reference/functional-icons-block.png": (20, 239, 402, 392),
    "reference/buttons-block.png": (20, 453, 402, 518),
    "reference/nav-and-deco-block.png": (20, 557, 402, 806),
    "reference/components-block.png": (402, 332, 1018, 609),
    "reference/progress-emojis-colors.png": (402, 617, 1018, 806),
}

ICON_NAMES = [
    "icon-home",
    "icon-bookshelf",
    "icon-discover",
    "icon-member",
    "icon-notes",
    "icon-search",
    "icon-bookmark",
    "icon-history",
    "icon-download",
    "icon-settings",
]
STATUS_NAMES = [
    "mascot-status-reading",
    "mascot-status-rest",
    "mascot-status-no-books",
    "mascot-status-empty",
]


def _bg_color(arr: np.ndarray) -> np.ndarray:
    return arr[8:28, 8:28].reshape(-1, 3).mean(axis=0)


def trim_content(im: Image.Image, tol: float = 14) -> Image.Image:
    arr = np.array(im.convert("RGB"))
    bg = _bg_color(arr)
    diff = np.linalg.norm(arr.astype(float) - bg, axis=2)
    ys, xs = np.where(diff > tol)
    if len(xs) == 0:
        return im
    pad = 3
    x0 = max(0, xs.min() - pad)
    x1 = min(arr.shape[1], xs.max() + 1 + pad)
    y0 = max(0, ys.min() - pad)
    y1 = min(arr.shape[0], ys.max() + 1 + pad)
    return im.crop((x0, y0, x1, y1))


def trim_in_box(
    diff: np.ndarray, box: tuple[int, int, int, int], tol: float = 12
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    patch = diff[y0:y1, x0:x1]
    ys, xs = np.where(patch > tol)
    if len(xs) == 0:
        return box
    return (x0 + xs.min(), y0 + ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)


def grid_sprites(
    diff: np.ndarray,
    region: tuple[int, int, int, int],
    cols: int,
    rows: int,
    names: list[str],
    display: int,
) -> dict[str, dict]:
    x0, y0, x1, y1 = region
    cw, rh = (x1 - x0) / cols, (y1 - y0) / rows
    out: dict[str, dict] = {}
    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        cell = (
            int(x0 + c * cw),
            int(y0 + r * rh),
            int(x0 + (c + 1) * cw),
            int(y0 + (r + 1) * rh),
        )
        box = trim_in_box(diff, cell)
        out[name] = {"box": [int(v) for v in box], "display": display}
    return out


def write_tokens_css(path: Path) -> None:
    c = TOKENS["colors"]
    path.write_text(
        f"""/* BeanRead design tokens — from UI kit */
:root {{
  --bean-green: {c['bean_green']};
  --bean-yellow: {c['bean_yellow']};
  --bean-cream: {c['bean_cream']};
  --bean-sand: {c['bean_sand']};
  --bean-brown: {c['bean_brown']};
  --bg: {c['bean_cream']};
  --surface: #fff;
  --accent: {c['bean_green']};
  --accent-soft: color-mix(in srgb, {c['bean_green']} 18%, {c['bean_cream']});
  --text: {c['bean_brown']};
  --muted: color-mix(in srgb, {c['bean_brown']} 55%, {c['bean_cream']});
  --border: color-mix(in srgb, {c['bean_sand']} 80%, #fff);
  --radius-card: 20px;
  --radius-btn: 999px;
  --shadow-clay: 0 8px 24px rgba(139, 110, 78, 0.12);
}}
""",
        encoding="utf-8",
    )


def write_sprite_css(path: Path, sheet_w: int, sheet_h: int, sprites: dict[str, dict]) -> None:
    lines = [
        "/* BeanRead UI kit sprites — one sheet, CSS background-position */",
        ".bean-sprite {",
        "  display: inline-block;",
        "  background-image: url('/element/_source/ui-kit-full.png');",
        "  background-repeat: no-repeat;",
        f"  background-size: {sheet_w}px {sheet_h}px;",
        "  vertical-align: middle;",
        "}",
    ]
    for name, spec in sprites.items():
        x, y, w, h = spec["box"]
        d = spec["display"]
        scale = d / max(w, 1)
        lines.append(f".bean-sprite-{name} {{")
        lines.append(f"  width: {d}px; height: {max(1, round(h * scale))}px;")
        lines.append(f"  background-position: {-x * scale:.1f}px {-y * scale:.1f}px;")
        lines.append(f"  background-size: {sheet_w * scale:.1f}px {sheet_h * scale:.1f}px;")
        lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src.is_file():
        raise SystemExit(f"Missing UI kit: {src}\nPlace sheet at ui/element/_source/ui-kit-full.png")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "_source").mkdir()
    shutil.copy2(src, OUT / "_source" / "ui-kit-full.png")

    img = Image.open(OUT / "_source" / "ui-kit-full.png").convert("RGBA")
    w, h = img.size
    arr = np.array(img.convert("RGB"))
    bg = _bg_color(arr)
    diff = np.linalg.norm(arr.astype(float) - bg, axis=2)

    sprites: dict[str, dict] = {}
    sprites.update(
        grid_sprites(diff, (35, 248, 395, 318), 5, 1, ICON_NAMES[:5], 40)
    )
    sprites.update(
        grid_sprites(diff, (35, 318, 395, 390), 5, 1, ICON_NAMES[5:], 40)
    )
    sprites.update(
        grid_sprites(diff, (408, 68, 1015, 162), 4, 1, STATUS_NAMES, 100)
    )

    manifest: dict = {
        "sheet": {"width": w, "height": h, "path": "_source/ui-kit-full.png"},
        "tokens": TOKENS,
        "sprites": sprites,
        "sections": {},
        "note": "Sprites are icon-only (labels excluded). ~40px source icons — OK for 24–32px UI. "
        "For retina toolbars export 512px assets from Figma into ui/element/export/.",
    }

    for rel, box in SECTIONS.items():
        fp = OUT / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        trimmed = trim_content(img.crop(box))
        trimmed.save(fp, format="PNG", optimize=True)
        manifest["sections"][rel] = {"box": box, "trimmed_size": list(trimmed.size)}

    write_tokens_css(OUT / "tokens.css")
    write_sprite_css(OUT / "sprite.css", w, h, sprites)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = OUT / "README.md"
    readme.write_text(
        """# BeanRead UI Element Kit

## 可直接用

| 文件 | 用途 |
|------|------|
| `tokens.css` | 色板、圆角、阴影 → 在 `style.css` 顶部 `@import url('/element/tokens.css');` |
| `sprite.css` | 雪碧图坐标 → `<span class="bean-sprite bean-sprite-icon-home"></span>` |
| `manifest.json` | 坐标与 token 真源 |

## 参考图

`reference/*.png` 是整块裁切（已去掉分区标题），用于设计对照，**不是**透明底生产素材。

## 生产级素材

从 Figma/PSD **分层导出**（512×512 图标、透明底）后放到：

```
ui/element/export/icons/
ui/element/export/mascot/
```

## 为何之前那批不能用？

从一张 1024px 总图硬切单张 PNG 会：裁进标题文字、网格对不齐、单 icon 只有 ~70px、米色底无法抠图。  
正确用法是 **tokens + CSS sprite**，或 **Figma 单独导出**。
""",
        encoding="utf-8",
    )
    print(f"OK → {OUT}  ({len(sprites)} sprites, {len(SECTIONS)} reference sections)")


if __name__ == "__main__":
    main()
