#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/src"
echo "Book Compiler UI → http://127.0.0.1:8765 (局域网见启动日志)"
exec conda run -n llm --no-capture-output python "$ROOT/ui/server.py"
