# -*- mode: python ; coding: utf-8 -*-
"""BeanRead Windows bundle — build with scripts/build-windows.ps1 or GitHub Actions."""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
hidden = collect_submodules("book_compiler")

EXCLUDES = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "keras",
    "scipy",
    "pandas",
    "sklearn",
    "matplotlib",
    "pyarrow",
    "transformers",
    "datasets",
    "accelerate",
    "sentencepiece",
    "tiktoken",
    "cv2",
    "PIL",
    "IPython",
    "notebook",
    "jupyter",
    "pytest",
    "setuptools",
]

a = Analysis(
    ["launcher.py"],
    pathex=["src", "ui"],
    binaries=[],
    datas=[
        ("ui/static", "ui/static"),
        ("ui/element", "ui/element"),
        (".env.example", "."),
        ("runtime-version.json", "."),
    ],
    hiddenimports=hidden + ["webview", "server"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BeanRead",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BeanRead",
)
