---
schema_version: "0.1"
book_slug: "{book-slug}"
chapter_id: "ch{NN}"
chapter_title: "{章标题}"
template: "M"
source: "_extract/ch{NN}.txt"
generated_at: "{ISO8601}"
status: "draft"
---

# 第{NN}章：{章标题} · 深度 Insight

> 方法论型模板 (M)。Golden sample：`人人都是产品经理NOTE/概览/第4章.md`

---

## 概念清单

| # | 概念 | 定义 | 书中案例 | 锚点 |
|---|------|------|---------|------|
| 1 | {概念名} | {一句话定义} | {案例摘要} | `_extract/ch{NN}.txt` L{start}-L{end} |

<!-- 要求：每个概念必须有案例 + 可跳转锚点 -->

---

## 概念串联

{本章概念之间的逻辑链——像 Z字采集法那张表，或 ASCII/mermaid}

```
{概念A} → {概念B} → {概念C}
    ↓
{与全书主线的关系}
```

---

## 与全书关系

| 维度 | 内容 |
|------|------|
| 在全书主线中的位置 | {如：想清楚阶段第二步} |
| 前置章节 | {ch0X} |
| 后续章节 | {ch0Y} |
| 全书金线 | {如：Y模型在本章如何体现} |

---

## 本章金句

- {可选，1～3 条}

---

## 本章 Q&A

### Q：{用户问题}

**答案**：{ grounded 回答 }

**溯源**：
- 概念：[[{概念名}]]
- 原文：`_extract/ch{NN}.txt` L{line} — 「{短引文}」

---

<!-- 深度模式：每章 Q&A 闸门关闭后，将本章 Q&A 追加到 insight/qa.md -->
