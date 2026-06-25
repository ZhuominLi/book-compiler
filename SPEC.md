# Book Compiler · SPEC（Schema 定稿 v0.2）

> **产品名**：Book Compiler（暂定）  
> **一句话**：一本书进去 → **深度 Summary**（读前材料）→ 阅读 Q&A → **Insight 包** + **Skill 包**  
> **Golden Sample 来源**：人人都是产品经理 NOTE（M 型）；启示录 ch01（N 型，待做）  
> **最后更新**：2026-06-06

---

## 1. 目录结构

每本书一个 `{book-root}/`，与源文件并列：

```
Readings/{分类}/
├── {原书}.{txt|md|docx|epub|pdf}       # 源文件（任意支持格式）
└── {书名}NOTE/                         # book-root
    ├── {stem}.txt                      # ingest 标准化全文（canonical）
    ├── _extract/                       # [输入] 分章原文（行锚点 L）
    │   └── ch01.txt … chNN.txt
    ├── _state/                         # [运行时] pipeline 状态（可删可重建）
    │   └── pipeline.json
    ├── summary/                        # [Pipeline] 深度 Summary（Q&A 之前）
    │   ├── overview.md
    │   ├── chapters/ch01.md … chNN.md
    │   └── page-index.json
    ├── insight/                        # [交付物 1] 个人 Insight（Q&A 之后）
    │   ├── book-meta.json
    │   ├── qa.md                       # UI chatbot 自动追加，不预生成
    │   ├── synthesis.md
    │   ├── concept-index.json
    │   └── concepts/                   # [可选]
    └── skill/                          # [交付物 2] compile 输出
        ├── SKILL.md
        ├── reference.md
        ├── examples.md
        └── manifest.json
```

**向后兼容**：旧书 `insight/chapters/`、`insight/overview.md` 仍可读；新书统一写 `summary/`。

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

## 3. Input Pipeline（ingest）

**用途**：任意源格式 → **BookDraft**（canonical 纯文本）→ 现有 split / preview / deep 不变。

### 3.1 流程

```
POST /api/books (multipart)
  → detect_format(filename)
  → adapter(bytes) → BookDraft
  → init_book(source_text=draft.text) → {stem}.txt
  → optional split_book() → _extract/ch*.txt
```

### 3.2 `BookDraft`（内存，不落盘 schema）

| 字段 | 说明 |
|------|------|
| `text` | 标准化全文，`\n` 换行，供分章与 L 锚点 |
| `source_format` | `txt` / `md` / `docx` / `epub` / `pdf_text` / `pdf_scan` |
| `original_filename` | 用户上传名 |
| `warnings` | 如「Word 表格未保留」 |
| `needs_ocr` | 扫描 PDF 为 true，导入拒绝并提示 P3 |

### 3.3 Adapter 注册表

| 扩展名 | adapter | 依赖 |
|--------|---------|------|
| `.txt` | `adapters/txt.py` | stdlib |
| `.md` | `adapters/md.py` | stdlib |
| `.docx` | `adapters/docx.py` | stdlib (zip+xml) |
| `.epub` | `adapters/epub.py` | stdlib (zip+spine) |
| `.pdf` | `adapters/pdf.py` | `pypdf`（文字层）；扫描版 `needs_ocr` |

代码路径：`src/book_compiler/ingest/`

### 3.4 `book-meta.json` → `ingest` 字段

```json
"ingest": {
  "source_format": "epub",
  "original_filename": "启示录.epub",
  "ingested_at": "2026-06-06T12:00:00Z",
  "warnings": ["EPUB 已按 spine 顺序转为纯文本"]
}
```

### 3.5 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/books` | multipart: `title`, `file`, `auto_split`, … |
| POST | `/api/split/detect` | JSON `source_text` 或 multipart `file` |
| POST | `/api/ingest/detect` | 仅预览 ingest + split，不建书 |
| GET | `/api/health` | `ingest_formats` 列表 |

---

## 4. 阅读呈现

**原则**：存储用 Markdown，呈现用 HTML + CSS；原文侧栏用纯文本 + 行号。

| 区域 | 存储 | UI 渲染 |
|------|------|---------|
| Summary / Insight 正文 | `summary/*.md`, `insight/*.md` | `renderMd()` → `.article.md-body.reader` |
| OCR 原文 | `_extract/ch*.txt` | 等宽 + 行号，highlight 锚点范围 |
| Chatbot | localStorage + `qa.md` | assistant 气泡 MD→HTML |

**阅读器偏好**（`localStorage: book-compiler-reader`）：

- `--reader-size`：14–22px
- `data-reader-theme`：`paper` | `night`

---

## 5. `book-meta.json`

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

## 6. `concept-index.json`

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

## 7. `_state/pipeline.json`

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

## 8. 文件 Schema

### 8.1 `summary/overview.md`（Preview 产出）

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

### 8.2 `summary/chapters/chNN.md` — 模板 M（方法论型）

**Golden Sample**：`人人都是产品经理NOTE/概览/第4章.md`

见 [templates/chapter-M.md](templates/chapter-M.md)

**必填区块**：

1. YAML frontmatter（`chapter_id`, `template`, `book_slug`）
2. `## 概念清单`（表格：概念 | 定义 | 书中案例 | 锚点）
3. `## 概念串联`（本章逻辑链，ASCII 或 mermaid）
4. `## 与全书关系`
5. `## 本章 Q&A`（用户问答，答案含锚点）

### 8.3 `summary/chapters/chNN.md` — 模板 N（叙事型）

**Golden Sample**：`book-compiler/golden/inspired-ch01.md`（待创建）

见 [templates/chapter-N.md](templates/chapter-N.md)

**必填区块**：

1. YAML frontmatter
2. `## 核心论点`（1～3 条）
3. `## 关键论据与案例`（表格）
4. `## 实践含义`
5. `## 术语表`（若有）
6. `## 本章 Q&A`

### 8.4 `insight/qa.md`

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

### 8.5 `insight/synthesis.md`（需 qa.md 非空）

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

## 9. Skill 包 Schema

Skill 从 Insight **二次编译**，不手写。

### 9.1 `skill/manifest.json`

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

### 9.2 `skill/SKILL.md`

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

### 9.3 `skill/reference.md`

从 `concept-index` + `synthesis` 压缩的速查表，可较长（progressive disclosure）。

### 9.4 `skill/examples.md`

从 `qa.md` 选 3～5 条高质量 Q&A，格式与 qa.md 一致但精简。

---

## 10. Pipeline 流程

### 10.1 Ingest（导入）

```
源文件 → ingest_bytes() → BookDraft
  → init_book() 写入 canonical txt + book-meta.ingest
  → split_book() → _extract/ch*.txt（可选）
```

### 10.2 Preview 模式

```
输入: canonical txt + _extract/
  → detect_book_type()   → book-meta.json
  → gen_overview()       → summary/overview.md
  → init_concept_index() → concept-index.json (preview 级概念)
输出: Summary（无 qa、synthesis、skill）
```

> **Q&A 不预生成** — 仅 UI chatbot 阅读时追加 `insight/qa.md`。

### 10.3 Deep 模式（Human-in-the-loop）

```
for chapter in chapters:
  → gen_chapter_insight(M|N)  → summary/chapters/chNN.md  [status: draft]
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

### 10.4 Q&A Grounding 规则

1. 检索顺序：`concept-index` → 对应 `chapters/` → `_extract/` 原文
2. 答案必须含 ≥1 个 `溯源` anchor
3. 原文引用 ≤ 200 字；更长则摘要 + 跳转
4. 书中无依据 → 明确说「本书未涉及」，不编造

---

## 11. Insight → Skill 编译规则

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

## 12. Golden Sample 清单

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

## 13. MVP 实现顺序

| 阶段 | 交付 | 验收 | 状态 |
|------|------|------|------|
| **0** | 本 SPEC + templates | 你能看懂每个文件放什么 | ✅ |
| **1** | 迁移人人产品经理 → 新目录结构 | insight/ 与现有概览等价 | ✅ |
| **2** | Preview pipeline | overview 可生成 | ✅ |
| **3** | Deep 单章（M 模板） | ch04 自动 ≈ golden sample | ⚠️ |
| **4** | 启示录分章 + N 模板 | inspired 39 章 | ✅ |
| **5** | synthesis + compile_skill | skill 可触发 | ✅ |
| **6** | Input ingest 多格式 | txt/md/docx/epub/pdf 导入 | ✅ |
| **7** | 阅读呈现 MD+CSS | 主题/字号/锚点 | ✅ |
| **8** | PDF OCR 异步 | 扫描古籍可导入 | ⏳ P3 |

---

## 14. 附录：文件清单速查

| 路径 | 阶段 | 交付物 |
|------|------|--------|
| `{stem}.txt` | Ingest | canonical 全文 |
| `_extract/ch*.txt` | Split | 分章原文（L 锚点） |
| `insight/book-meta.json` | Init | 元数据 + ingest |
| `summary/overview.md` | Preview | 深度 Summary |
| `summary/chapters/ch*.md` | Deep | 深度 Summary |
| `insight/qa.md` | 阅读 UI | Insight（对话） |
| `insight/synthesis.md` | Post-Q&A | Insight（融会贯通） |
| `summary/page-index.json` | Preview+Deep | 检索索引 |
| `skill/*` | Compile | Skill |
| `_state/pipeline.json` | 运行时 | 内部 |

**三层边界**：

- **Summary** = `summary/`（Pipeline 读厚，Q&A 之前）
- **Insight** = `insight/qa.md` + `synthesis.md`（你的理解，Q&A 之后）
- **Skill** = `skill/` → `~/.cursor/skills/`（给 Agent）
