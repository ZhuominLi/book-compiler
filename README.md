# Book Compiler

一本书 → **Insight**（个人知识库）+ **Skill**（AI 可调用）

规范见 [SPEC.md](SPEC.md)。

## 快速开始

```bash
cd Readings/产品经理/book-compiler
./run.sh all-pm                    # 推荐：自动用 llm conda + .env
./run.sh deep --book inspired-cagan --chapter ch02
./run.sh deep --book inspired-cagan --all
```

或手动：`conda run -n llm python cli.py ...`

## LLM（DeepSeek / OpenAI 兼容）

在 `book-compiler/.env` 配置（已 gitignore）：

```bash
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

也支持 `OPENAI_API_KEY` + `OPENAI_BASE_URL` 作为别名。未配置时使用离线 heuristic。

## 目录

| 书 | book-root |
|----|-----------|
| 人人都是产品经理 | `../人人都是产品经理NOTE/` |
| 启示录 | `../启示录NOTE/` |

## 产出

- `insight/` — overview, chapters, synthesis, qa, concept-index.json
- `skill/` — SKILL.md, reference.md, examples.md, manifest.json
- 安装：`~/.cursor/skills/{slug}/`

## 阅读 UI

```bash
./run-ui.sh
# → http://127.0.0.1:8765
```

- 左侧导航：概览 / 各章 / synthesis / Q&A
- 正文 Markdown 阅读
- 点击锚点 `L20–L40` → 右侧原文面板
