# Book Compiler · SPEC（Schema 定稿 v0.1）

> **产品名**：Book Compiler（暂定）  
> **一句话**：一本书进去 → **Insight 包**（个人知识库）+ **Skill 包**（AI 可调用）  
> **Golden Sample 来源**：人人都是产品经理 NOTE（M 型）；启示录 ch01（N 型，待做）

---

## 1. 目录结构

每本书一个 `{book-root}/`，与源文件并列：

```
Readings/{分类}/
├── {原书}.txt                          # 源文件（输入）
└── {书名}NOTE/                         # book-root
    ├── _extract/                       # [输入] 分章原文
    │   └── ch01.txt … chNN.txt
    ├── _state/                         # [运行时] pipeline 状态（可删可重建）
    │   └── pipeline.json
    ├── insight/                        # [交付物 1] 个人知识库
    │   ├── book-meta.json
    │   ├── overview.md
    │   ├── synthesis.md
    │   ├── qa.md
    │   ├── concept-index.json
    │   ├── chapters/
    │   │   └── ch01.md … chNN.md
    │   └── concepts/                   # [可选] 从 index 抽出的单概念深页
    │       └── Y模型.md
    └── skill/                          # [交付物 2] 本地 skill 草稿（compile 输出）
        ├── SKILL.md
        ├── reference.md
        ├── examples.md
        └── manifest.json
```

**安装位置**（compile 后复制）：

```
~/.cursor/skills/{book-slug}/     # Cursor
~/.claude/skills/{book-slug}/     # Claude Code（可选）
```

---

## 2. 旧目录迁移映射（人人都是产品经理）

| 现有路径 | 新路径 | 说明 |
|---------|--------|------|
| `_extract/ch*.txt` | `_extract/ch*.txt` | 不变 |
| `概览/全文深度总结.md` | `insight/overview.md`（早期版） | 可被 pipeline 覆盖 |
| `概览/全书融会贯通报告.md` | `insight/synthesis.md` | 深度完成后产出 |
| `概览/第N章.md` | `insight/chapters/chNN.md` | 深度模式单章 |
| `概览/Q&A.md` | `insight/qa.md` | 预览+深度 Q&A 合并 |
| `概览/方法论抽取/*.md` | `insight/concepts/*.md` | 可选，从 concept-index 生成 |
| `.claude/skills/pm-synthesis/` | compile → `skill/` → `~/.cursor/skills/pm-book/` | 现有 skill 是手工 v0，将被 compiler 替代 |

---

## 3. `book-meta.json`

**用途**：全书元数据 + 类型识别 + 章节索引。Preview 完成后写入/更新。

```json
{
  "schema_version": "0.1",
  "title": "人人都是产品经理",
  "title_en": null,
  "authors": ["苏杰"],
  "slug": "pm-book-sujie",
  "source_file": "../人人都是产品经理.txt",
  "language": "zh",

  "book_type": "M",
  "book_type_reason": "全书以 Y模型、KANO、MVP 等方法论框架为主",
  "book_type_overrides": {},

  "created_at": "2026-06-06T00:00:00Z",
  "updated_at": "2026-06-06T00:00:00Z",

  "pipeline": {
    "preview_done": false,
    "deep_done": false,
    "deep_current_chapter": null,
    "skill_compiled_at": null
  },

  "chapters": [
    {
      "id": "ch01",
      "index": 1,
      "title": "初识：大话产品经理",
      "template": "M",
      "source": "_extract/ch01.txt",
      "insight_file": "insight/chapters/ch01.md",
      "status": "pending",
      "char_count": 12000
    }
  ],

  "skill": {
    "slug": "pm-book-sujie",
    "triggers": ["人人都是产品经理", "苏杰", "Y模型", "KANO", "MVP"],
    "install_paths": ["~/.cursor/skills/pm-book-sujie"]
  }
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `book_type` | ✅ | `M` 方法论 / `N` 叙事 / `H` 混合（按章 `template` 区分） |
| `chapters[].template` | ✅ | 该章用 `M` 或 `N` 模板 |
| `chapters[].status` | ✅ | `pending` / `preview` / `deep_done` / `skipped` |
| `pipeline.deep_current_chapter` | — | 断点续传：上次停在哪一章 |

### 类型识别规则（C：自动 + 可 override）

**全书 `book_type` 打分**（Preview 阶段，LLM 或规则）：

| 信号 | M 分 | N 分 |
|------|------|------|
| 出现「模型/框架/步骤/清单/公式」密度高 | +2 | |
| 章节以案例论证为主 | | +2 |
| 目录含「方法/工具/模型」 | +1 | |
| 目录含「故事/实践/团队/文化」 | | +1 |

- M ≥ N + 2 → `M`
- N ≥ M + 2 → `N`
- 否则 → `H`（按章再判 `chapters[].template`）

**用户 override**：`book_type_overrides: { "book_type": "N" }` 优先。

---

## 4. `concept-index.json`

**用途**：概念 → 章节锚点，供 Q&A 跳转、Skill reference、UI 内链。

```json
{
  "schema_version": "0.1",
  "book_slug": "pm-book-sujie",
  "concepts": {
    "Y模型": {
      "id": "y-model",
      "aliases": ["Y模型", "需求转化模型", "Y模型四步法"],
      "type": "framework",
      "chapter": "ch05",
      "anchors": [
        {
          "source": "_extract/ch05.txt",
          "kind": "line",
          "start": 128,
          "end": 145,
          "quote": "用心听，但不要照着做"
        }
      ],
      "insight_refs": [
        "insight/chapters/ch05.md#概念1",
        "insight/concepts/Y模型.md"
      ],
      "related": ["伪需求", "KANO模型", "MVP"]
    }
  }
}
```

### Anchor 类型

| `kind` | 含义 | 示例 |
|--------|------|------|
| `line` | 源 txt 行号（1-based） | 启示录 OCR txt |
| `page` | PDF/OCR 页标记 | `--- 第 12 页 ---` |
| `heading` | 章节内标题文本 | `# 概念1：Y模型` |
| `md_block` | insight 文件内 heading id | `ch05.md#概念串联` |

**增量更新**：每完成一章深度模式，merge 该章 concepts 进 index，不覆盖已有（除非 `force: true`）。

---

## 5. `_state/pipeline.json`

**用途**：运行时 checkpoint，支持断点续传。

```json
{
  "schema_version": "0.1",
  "book_slug": "pm-book-sujie",
  "mode": "deep",
  "started_at": "2026-06-06T10:00:00Z",
  "updated_at": "2026-06-06T11:30:00Z",
  "current_step": "deep_chapter_qa",
  "current_chapter": "ch04",
  "completed_chapters": ["ch01", "ch02", "ch03"],
  "preview": { "done": true, "at": "2026-06-06T09:00:00Z" },
  "deep": { "done": false, "total": 11, "finished": 3 },
  "skill": { "compiled": false },
  "errors": []
}
```

---

## 6. Insight 文件 Schema

### 6.1 `insight/overview.md`（预览模式产出）

**时机**：书进入 → 分章完成后  
**作用**：全局 summary，决定要不要深度读

```markdown
---
schema_version: "0.1"
book_slug: pm-book-sujie
kind: overview
generated_at: 2026-06-06T09:00:00Z
---

# {书名} · 全书预览

> 基于全书分章原文的 global summary。深度阅读见 `chapters/`。

## 一句话
{一句话说清这本书讲什么}

## 全书主线
{3～7 条逻辑链或阶段表}

## 章节地图
| 章 | 标题 | 一句话 | 模板 |
|----|------|--------|------|
| ch01 | … | … | M |

## 核心概念速览（预览级，不含案例细节）
| 概念 | 在哪章 | 一句话 |
|------|--------|--------|

## 值得深度读吗？
{基于 preview 的判断：适合深读 / 选读哪些章}
```

### 6.2 `insight/chapters/chNN.md` — 模板 M（方法论型）

**Golden Sample**：`人人都是产品经理NOTE/概览/第4章.md`

见 [templates/chapter-M.md](templates/chapter-M.md)

**必填区块**：

1. YAML frontmatter（`chapter_id`, `template`, `book_slug`）
2. `## 概念清单`（表格：概念 | 定义 | 书中案例 | 锚点）
3. `## 概念串联`（本章逻辑链，ASCII 或 mermaid）
4. `## 与全书关系`
5. `## 本章 Q&A`（用户问答，答案含锚点）

### 6.3 `insight/chapters/chNN.md` — 模板 N（叙事型）

**Golden Sample**：`book-compiler/golden/inspired-ch01.md`（待创建）

见 [templates/chapter-N.md](templates/chapter-N.md)

**必填区块**：

1. YAML frontmatter
2. `## 核心论点`（1～3 条）
3. `## 关键论据与案例`（表格）
4. `## 实践含义`
5. `## 术语表`（若有）
6. `## 本章 Q&A`

### 6.4 `insight/qa.md`

**格式**：全书 Q&A 日志，预览 + 深度模式追加。

```markdown
---
schema_version: "0.1"
book_slug: pm-book-sujie
---

# Q&A · {书名}

## [preview] 2026-06-06

### Q：{用户问题}

**模式**：preview | deep:ch04  
**答案**：  
{ grounded 回答，必须基于本书 }

**溯源**：
- 概念：[[Y模型]] → ch05, line:128
- 原文：> {短引文}

---

## [deep:ch04] 2026-06-06

### Q：…
```

**规则**：

- 每条 Q&A 必须有 `溯源`（至少 1 个 anchor）
- 概念名用 `[[概念名]]`，对应 `concept-index.json`

### 6.5 `insight/synthesis.md`（深度全书完成后）

**Golden Sample**：`人人都是产品经理NOTE/概览/全书融会贯通报告.md`

```markdown
---
schema_version: "0.1"
book_slug: pm-book-sujie
kind: synthesis
generated_at: 2026-06-06T20:00:00Z
sources:
  - insight/overview.md
  - insight/chapters/*
  - insight/qa.md
---

# {书名} · 深度 Insight（融会贯通）

## 全书主线 + 金线
## 分章精华（每章 3～5 行，链接到 chapters/）
## 用户 Q&A 沉淀（从 qa.md 提炼高频问题）
## 跨章概念图谱
## 对个人知识库的使用建议
```

---

## 7. Skill 包 Schema

Skill 从 Insight **二次编译**，不手写。

### 7.1 `skill/manifest.json`

```json
{
  "schema_version": "0.1",
  "book_slug": "pm-book-sujie",
  "skill_name": "pm-book-sujie",
  "compiled_from": {
    "synthesis": "insight/synthesis.md",
    "concept_index": "insight/concept-index.json",
    "qa": "insight/qa.md",
    "compiled_at": "2026-06-06T21:00:00Z"
  },
  "insight_root": "../insight",
  "install_to": ["~/.cursor/skills/pm-book-sujie"]
}
```

### 7.2 `skill/SKILL.md`

**约束**：< 500 行；第三人称 description；含触发词。

**结构**（对齐 `product-thinking` skill）：

```markdown
---
name: pm-book-sujie
description: >-
  《人人都是产品经理》知识库。Y模型、KANO、MVP、需求采集与产品全流程。
  触发：人人都是产品经理、苏杰、Y模型、KANO、伪需求、MVP
---

# {书名}

## 何时调用
{3～5 条场景}

## 路由表
| 用户意图 | 查哪里 |
|---------|--------|

## 核心框架（极简）
{从 synthesis 压缩，不超过 100 行}

## 行为边界
- 答案必须 grounded 于本书 insight
- 不确定时指向 insight/chapters 或 qa.md

## 附加资源
- 完整 insight：{相对路径 insight/synthesis.md}
- 概念索引：{concept-index.json}
- 示例问答：examples.md
```

### 7.3 `skill/reference.md`

从 `concept-index` + `synthesis` 压缩的速查表，可较长（progressive disclosure）。

### 7.4 `skill/examples.md`

从 `qa.md` 选 3～5 条高质量 Q&A，格式与 qa.md 一致但精简。

---

## 8. Pipeline 流程

### 8.1 Preview 模式

```
输入: 原书 txt
  → split_chapters()     → _extract/ch*.txt
  → detect_book_type()   → book-meta.json
  → gen_overview()       → insight/overview.md
  → init_concept_index() → concept-index.json (preview 级概念)
  → qa_loop(optional)    → append insight/qa.md
输出: Insight 部分（无 synthesis、无 skill）
```

### 8.2 Deep 模式（Human-in-the-loop）

```
for chapter in chapters:
  → gen_chapter_insight(M|N)  → insight/chapters/chNN.md  [status: draft]
  → update_concept_index()
  → ⏸ HITL 闸门：人工审阅/编辑 chapters/chNN.md
  → qa_gate()                 → 用户 Q&A，append qa.md（可选）
  → approve                   → status: approved
  → checkpoint()              → _state/pipeline.json
  → 下一章

post (全部 approved 后):
  → gen_synthesis()
  → compile_skill()
```

**CLI**：

```bash
./run.sh deep --book inspired-cagan --chapter ch01    # 生成 draft，暂停
# 人工编辑 insight/chapters/ch01.md
./run.sh approve --book inspired-cagan --chapter ch01 # 通过后下一章
./run.sh status --book inspired-cagan                 # 查看 pending/draft/approved
./run.sh deep --book inspired-cagan --all --batch     # 跳过 HITL，批量 approved
```

章节状态：`pending` → `draft`（待审）→ `approved`（已通过）

### 8.3 Q&A Grounding 规则

1. 检索顺序：`concept-index` → 对应 `chapters/` → `_extract/` 原文
2. 答案必须含 ≥1 个 `溯源` anchor
3. 原文引用 ≤ 200 字；更长则摘要 + 跳转
4. 书中无依据 → 明确说「本书未涉及」，不编造

---

## 9. Insight → Skill 编译规则

| Insight 来源 | Skill 目标 | 规则 |
|-------------|-----------|------|
| `book-meta.skill.triggers` | `SKILL.md` frontmatter `description` | 逗号拼接触发词 |
| `synthesis.md` 全书主线 | `SKILL.md` 核心框架 | 压缩至 ≤100 行 |
| `synthesis.md` 路由场景 | `SKILL.md` 路由表 | 5～10 行 |
| `concept-index.json` | `reference.md` | 每个 concept 一行定义 + 章节 |
| `qa.md` 高频 Q | `examples.md` | 选有溯源、有深度的 3～5 条 |
| 全书 | `manifest.json` | 路径 + 编译时间 |

**Re-compile 触发**：`synthesis.md` 或 `qa.md` 更新后，运行 `compile_skill()`，不重新跑 deep。

---

## 10. Golden Sample 清单

| 类型 | 文件 | 状态 |
|------|------|------|
| M · 单章 | `人人都是产品经理NOTE/概览/第4章.md` | ✅ 已有 |
| M · synthesis | `人人都是产品经理NOTE/概览/全书融会贯通报告.md` | ✅ 已有 |
| M · Q&A | `人人都是产品经理NOTE/概览/Q&A.md` | ✅ 已有 |
| M · concept | `概览/方法论抽取/Y模型.md` | ✅ 已有 |
| N · 单章 | `book-compiler/golden/inspired-ch01.md` | ⏳ 待做 |
| Skill | `~/.cursor/skills/product-thinking/` | ✅ 结构参考 |
| Skill（本书） | `.claude/skills/pm-synthesis/SKILL.md` | ⚠️ 手工 v0，将被 compiler 替代 |

**质量对照**：pipeline 产出与 golden sample  diff 时，以 golden 为准调 prompt。

---

## 11. MVP 实现顺序

| 阶段 | 交付 | 验收 |
|------|------|------|
| **0** | 本 SPEC + templates | 你能看懂每个文件放什么 |
| **1** | 迁移人人产品经理 → 新目录结构 | insight/ 与现有概览等价 |
| **2** | Preview pipeline（overview + qa grounding） | 对 overview 提问能跳转 |
| **3** | Deep 单章（M 模板） | ch04 自动 ≈ golden sample |
| **4** | 启示录分章 + N 模板 golden | inspired-ch01.md 完成 |
| **5** | synthesis + compile_skill | skill 在新对话可触发 |

---

## 12. 附录：文件清单速查

| 路径 | 阶段 | 交付物 |
|------|------|--------|
| `_extract/ch*.txt` | 输入 | 原文 |
| `insight/book-meta.json` | Preview | 元数据 |
| `insight/overview.md` | Preview | Insight |
| `insight/chapters/ch*.md` | Deep | Insight |
| `insight/qa.md` | Preview+Deep | Insight |
| `insight/synthesis.md` | Deep 完成 | Insight |
| `insight/concept-index.json` | Preview+Deep | Insight |
| `skill/*` | Compile | Skill |
| `_state/pipeline.json` | 运行时 | 内部 |

**两个交付物边界**：

- **Insight** = `insight/` 整个目录（给人读、给 PKM、给 search）
- **Skill** = `skill/` → 安装到 `~/.cursor/skills/`（给 Agent 路由调用）
