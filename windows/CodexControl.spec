# -*- mode: python ; coding: utf-8 -*-
"""One-file Windows build; collect application code, never local account data."""
import os
from pathlib import Path

root = Path(SPECPATH)
version_resource = os.environ.get("CODEXCONTROL_VERSION_RESOURCE")
if not version_resource:
    raise RuntimeError("Build with windows/build.ps1 to supply generic version metadata")

a = Analysis(
    [str(root / "CodexControlWindows.pyw")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=["pystray._win32", "PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest", "IPython", "matplotlib", "numpy", "pandas", "scipy"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="CodexControl",
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
    icon=str(root / "build-assets" / "CodexControl.ico"),
    version=version_resource,
)
