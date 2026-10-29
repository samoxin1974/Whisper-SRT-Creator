#!/usr/bin/env python3
"""Build a macOS app and drag-to-Applications DMG from the current source."""
import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ffmpeg", default=os.environ.get("SRT_FFMPEG_BINARY"),
        help="Path to a macOS FFmpeg executable (defaults to imageio-ffmpeg's bundled binary).",
    )
    parser.add_argument("--app-only", action="store_true", help="Skip DMG creation.")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Build on macOS, using Python for the target architecture.")
    missing = [name for name in ("whisper", "PyQt5", "PyInstaller", "imageio_ffmpeg")
               if importlib.util.find_spec(name) is None]
    if missing:
        parser.error("Missing packages: " + ", ".join(missing)
                     + ". Run: python -m pip install -r requirements-build.txt")
    if not args.ffmpeg:
        import imageio_ffmpeg
        args.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg = Path(args.ffmpeg).expanduser().resolve()
    if ffmpeg is None or not ffmpeg.is_file() or not os.access(ffmpeg, os.X_OK):
        parser.error("Install FFmpeg or supply --ffmpeg /path/to/ffmpeg.")
    architectures = subprocess.check_output(["lipo", "-archs", str(ffmpeg)], text=True).split()
    if platform.machine() not in architectures:
        parser.error(f"FFmpeg has architecture(s) {architectures}, but Python uses "
                     f"{platform.machine()}. Supply a matching binary with --ffmpeg.")
    run(ffmpeg, "-version", stdout=subprocess.DEVNULL)

    assets = ROOT / "build" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    # Whisper launches the command by this exact name.
    staged_ffmpeg = assets / "ffmpeg"
    shutil.copy2(ffmpeg, staged_ffmpeg)
    iconset = assets / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            pixels = size * scale
            run("sips", "-z", pixels, pixels, ROOT / "icon.png", "--out",
                iconset / f"icon_{size}x{size}{suffix}.png", stdout=subprocess.DEVNULL)
    run("iconutil", "-c", "icns", iconset, "-o", assets / "icon.icns")

    env = os.environ.copy()
    env["SRT_FFMPEG_BINARY"] = str(staged_ffmpeg)
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / ".pyinstaller")
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        ROOT / "SRT-Creator.spec", cwd=ROOT, env=env)
    app = ROOT / "dist" / "SRT Creator.app"
    bundled_ffmpeg = app / "Contents" / "Resources" / "bin" / "ffmpeg"
    if not bundled_ffmpeg.is_file():
        raise RuntimeError(f"FFmpeg missing from app: {bundled_ffmpeg}")
    run(bundled_ffmpeg, "-version", stdout=subprocess.DEVNULL)
    run(app / "Contents" / "MacOS" / "SRT Creator", "--self-test")
    print(f"Built: {app}", flush=True)
    if args.app_only:
        return

    dmg = ROOT / "dist" / f"SRT-Creator-macOS-{platform.machine()}.dmg"
    if dmg.exists():
        parser.error(f"Installer already exists: {dmg}. Move it aside before rebuilding.")
    with tempfile.TemporaryDirectory(prefix="srt-creator-dmg-") as staging:
        stage = Path(staging)
        run("ditto", app, stage / app.name)
        (stage / "Applications").symlink_to("/Applications")
        run("hdiutil", "create", "-volname", "SRT Creator", "-srcfolder", stage,
            "-format", "UDZO", dmg)
    run("hdiutil", "verify", dmg)
    print(f"Built: {dmg}")


if __name__ == "__main__":
    main()
