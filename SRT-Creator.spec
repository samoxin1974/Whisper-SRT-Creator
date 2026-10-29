"""macOS PyInstaller recipe; invoke through scripts/build_macos.py."""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
ffmpeg = Path(os.environ["SRT_FFMPEG_BINARY"]).resolve()
icon = root / "build" / "assets" / "icon.icns"

a = Analysis(
    [str(root / "srt-creator.py")],
    pathex=[str(root)],
    binaries=[(str(ffmpeg), "bin")],
    datas=[(str(root / "icon.png"), ".")] + collect_data_files("whisper"),
    hiddenimports=["tiktoken_ext.openai_public"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SRT Creator",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SRT Creator")
app = BUNDLE(
    coll,
    name="SRT Creator.app",
    icon=str(icon),
    bundle_identifier="com.srtcreator.desktop",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "14.0",
    },
)
