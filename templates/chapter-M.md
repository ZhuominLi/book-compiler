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

## 一、本章概念清单

| 概念 | 原文表述 | 锚点 |
|------|----------|------|
| {概念名} | {书中原话或忠实复述，含案例细节} | `_extract/ch{NN}.txt` L{start}-L{end} |

<!-- 要求：原文每一个独立概念一行；「原文表述」尽量引用书中原话 -->

---

## 二、本章概念串联

{用所有概念串联起来，总结本章完整内容——2～5 段叙述，可辅以 ASCII/mermaid}

### 一句话概括

{本章一句话}

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
