# BeanRead UI Element Kit

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
