# Golden Sample 说明

## 已有

| 类型 | 路径 | 模板 |
|------|------|------|
| M · synthesis | `../人人都是产品经理NOTE/insight/synthesis.md` | overview/synthesis |
| M · concepts | `../人人都是产品经理NOTE/insight/concepts/` | 单概念深页 |
| M · overview | `../人人都是产品经理NOTE/insight/overview.md` | preview |
| N · 单章 | `inspired-ch01.md` | `templates/chapter-N.md` |
| Skill 结构 | `~/.cursor/skills/pm-book-sujie/` | `templates/skill-SKILL.md` |

## 待人工加深

- 人人都是产品经理各章 `insight/chapters/ch*.md`（磁盘上原 概览/第N章.md 多为空，需 `python cli.py deep --all` + `OPENAI_API_KEY`）
- 启示录 ch02–ch39 同上

## 用法

```bash
# 离线占位 deep
python cli.py deep --book inspired-cagan --chapter ch02

# 有 API 后批量
export OPENAI_API_KEY=sk-...
python cli.py deep --book inspired-cagan --all
python cli.py synthesis --book inspired-cagan
python cli.py compile --book inspired-cagan --install
```

Pipeline 产出与 golden diff，以 golden 为准调 prompt。
