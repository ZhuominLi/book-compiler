# -*- mode: python ; coding: utf-8 -*-
"""BeanRead slim bundle — build with .venv-pack (see scripts/build-macos.sh)."""
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
hidden = collect_submodules("book_compiler")

# Safety net if build ever runs from a fat conda env again
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
    hiddenimports=hidden + ["webview", "objc", "Foundation", "AppKit", "WebKit"],
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
    strip=True,
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
    strip=True,
    upx=False,
    upx_exclude=[],
    name="BeanRead",
)
app = BUNDLE(
    coll,
    name="懒豆阅读.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="com.zhuominli.beanread",
    info_plist={
        "CFBundleDisplayName": "懒豆阅读",
        "CFBundleName": "BeanRead",
        "CFBundleIconFile": "AppIcon",
    },
)
