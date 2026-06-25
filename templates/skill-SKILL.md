---
name: {book-slug}
description: >-
  {书名}知识库。{3～5 个核心主题词}。
  触发：{trigger1}、{trigger2}、{trigger3}
---

# {书名}

基于本书 Insight 包编译的 Agent Skill。答案必须 grounded 于本书。

---

## 何时调用

- {场景 1：如「用 Y模型分析这个需求」}
- {场景 2}
- {场景 3}

---

## 路由表

| 用户意图 | 查 Insight 哪里 |
|---------|----------------|
| {意图} | `insight/chapters/ch05.md` / `reference.md#{概念}` |

---

## 核心框架（压缩版）

{从 synthesis.md 提取，≤100 行。框架表 + 金句即可。}

---

## 行为边界

- 只基于本书 `insight/` 内容回答；不确定时说「书中未明确涉及」
- 需要案例细节时，指向 `insight/chapters/` 或 `insight/qa.md`
- 不替代读原书；鼓励用户跳转 `_extract/` 原文

---

## 附加资源

- 完整 Insight：[insight/synthesis.md](../insight/synthesis.md)
- 概念索引：[insight/concept-index.json](../insight/concept-index.json)
- 示例问答：[examples.md](examples.md)
