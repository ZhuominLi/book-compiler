#!/usr/bin/env python3
"""BeanRead desktop launcher — local server + embedded webview."""

from __future__ import annotations

import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        from book_compiler.paths import frozen_bundle_root

        root = frozen_bundle_root()
        if root:
            return root
    return Path(__file__).resolve().parent


ROOT = _app_root()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ui"))

from book_compiler.runtime_update import activate_runtime_overlay  # noqa: E402

_RUNTIME = activate_runtime_overlay(ROOT)

from book_compiler.brand import APP_TITLE  # noqa: E402
from book_compiler.llm import load_env_file  # noqa: E402
from book_compiler.paths import app_data_dir, books_registry_path, library_dir  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}/"
WINDOW_W, WINDOW_H = 1400, 900


def _bootstrap_data_dir() -> None:
    """First-run: empty bookshelf, optional .env template, library folder."""
    data = app_data_dir()
    library_dir()
    reg = books_registry_path()
    if not reg.is_file():
        reg.write_text("{}\n", encoding="utf-8")
    env = data / ".env"
    if not env.is_file():
        example = ROOT / ".env.example"
        if example.is_file():
            shutil.copy(example, env)
    load_env_file(env)


def _wait_for_server(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    raise RuntimeError(f"server did not start on {URL}")


def main() -> None:
    try:
        import webview
    except ImportError as e:
        raise SystemExit(
            "pywebview is required for the desktop app.\n"
            "  pip install -r requirements-desktop.txt"
        ) from e

    _bootstrap_data_dir()

    from server import create_httpd  # noqa: E402

    httpd = create_httpd(host=HOST, port=PORT)
    thread = threading.Thread(target=httpd.serve_forever, name="beanread-server", daemon=True)
    thread.start()
    _wait_for_server()

    window = webview.create_window(APP_TITLE, URL, width=WINDOW_W, height=WINDOW_H, min_size=(960, 640))
    webview.start()
    httpd.shutdown()
    thread.join(timeout=3)


if __name__ == "__main__":
    main()
