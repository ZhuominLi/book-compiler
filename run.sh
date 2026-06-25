#!/usr/bin/env bash
# 使用 llm conda 环境运行 Book Compiler（已配置 DeepSeek .env）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec conda run -n llm --no-capture-output python "$ROOT/cli.py" "$@"
