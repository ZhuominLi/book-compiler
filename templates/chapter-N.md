---
schema_version: "0.1"
book_slug: "{book-slug}"
chapter_id: "ch{NN}"
chapter_title: "{章标题}"
template: "N"
source: "_extract/ch{NN}.txt"
generated_at: "{ISO8601}"
status: "draft"
---

# 第{NN}章：{章标题} · 深度 Insight

> 叙事型模板 (N)。与 M 模板统一：**概念清单 + 概念串联**。

---

## 一、本章概念清单

| 概念 | 原文表述 | 锚点 |
|------|----------|------|
| {论点/主题名} | {书中原话或忠实复述} | `_extract/ch{NN}.txt` L{start}-L{end} |

<!-- 要求：原文每一个独立论点/主题一行；「原文表述」尽量引用书中原话 -->

---

## 二、本章概念串联

{用所有概念按论证顺序串联，总结本章完整内容——2～5 段叙述}

### 一句话概括

{本章一句话}

---

## 本章 Q&A

### Q：{用户问题}

**答案**：{ grounded 回答 }

**溯源**：
- 概念：[[{概念名}]]
- 原文：`_extract/ch{NN}.txt` L{line} — 「{短引文}」

---
