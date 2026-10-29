# Whisper SRT Creator

A desktop subtitle generator using OpenAI Whisper and PyQt5. Select an audio or
video file, choose a model and language, and export SRT, WebVTT, or transcript JSON.
Transcription runs locally on your computer after the selected model is downloaded.

## Download and install

**[Download the macOS Apple Silicon installer](https://github.com/samoxin1974/Whisper-SRT-Creator/releases/latest)**

Requires an Apple Silicon Mac (M1 or newer) running macOS 14 or later. The installer
includes Python, application dependencies, and FFmpeg; no separate installation
of those tools is needed.

1. Download `SRT-Creator-macOS-arm64.dmg` from the release page.
2. Open the DMG and drag **SRT Creator** into **Applications**.
3. Launch the app from Applications. The window is titled **Whisper Subtitle Generator**.

The app is ad hoc signed and has not been notarized by Apple. Whisper downloads
the selected model on first use, so an internet connection and free disk space
are required. No OpenAI API key or subscription is required.

## Features

- Generate `.srt`, `.vtt`, and structured `.json` transcripts.
- Choose `tiny`, `base`, `small`, `medium`, or `large` Whisper models.
- Detect the spoken language automatically or select a language manually.
- Open common audio and video formats, including MP3, WAV, M4A, MP4, and MOV.
- Save one or more output formats to a directory of your choice.

## Usage

1. Click **Browse...** and select an audio or video file.
2. Choose a model and a language, or leave **Auto Detect** selected.
3. Select one or more output formats.
4. Optionally change the output directory, then click **Generate**.

Start with `base` or `tiny`. Larger models require more memory and take longer
to run. Files are saved alongside the input by default, using the same base name.
Existing output files with those names are overwritten.

JSON contains `phrases` with timestamps, text, token ranges, and generated element
IDs (`schemaVersion` `1.1.3`); it is not Whisper's raw JSON output.

## Run from source

Use Python 3.12 and FFmpeg. On macOS with Homebrew:

```sh
git clone https://github.com/samoxin1974/Whisper-SRT-Creator.git
cd Whisper-SRT-Creator
brew install python@3.12 ffmpeg
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python srt-creator.py
```

On Linux or Windows, install Python and FFmpeg using your system's tools, then
create a virtual environment and install the same requirements. On Windows,
activate it with `.venv\Scripts\activate`. Source operation on those platforms
has not been verified for this reconstruction.

## Build a macOS app and DMG

With the virtual environment above activated:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_macos.py
```

The build script generates the macOS icon from `icon.png`, bundles the Python
runtime, dependencies, Whisper assets, and FFmpeg with PyInstaller, and creates:

- `dist/SRT Creator.app`
- `dist/SRT-Creator-macOS-arm64.dmg` or `dist/SRT-Creator-macOS-x86_64.dmg`

The ARM64 build uses Python 3.12 and requires macOS 14 or later. Its exact package
versions are recorded in `requirements-lock-macos-arm64.txt`. On an Apple Silicon
Mac with Python 3.12, install that file instead of `requirements-build.txt` to
recreate the dependency environment.

Build separately on each target architecture with a matching Python environment.
The default FFmpeg comes from `imageio-ffmpeg` and does not require Homebrew on the
destination Mac. This is not a universal binary build. Use
`python scripts/build_macos.py --ffmpeg /path/to/ffmpeg` to select FFmpeg explicitly,
or `--app-only` to skip the disk image. The app output is replaced during a rebuild;
an existing DMG must be moved aside first. Models are downloaded on first use and
are not included in the installer.

These packaging files were reconstructed from the surviving source and icon.
They do not reproduce an earlier installer byte for byte. The build script runs
the packaged app's `--self-test`, checking audio decoding through bundled FFmpeg,
Whisper's audio assets, tokenization, all three exporters, and creation of the Qt
window. It also verifies the disk image checksum. These checks do not download a
model or run speech recognition. Before distributing, test a real transcription
from Finder on a separate Mac without your development environment.

To repeat the packaged app check:

```sh
"dist/SRT Creator.app/Contents/MacOS/SRT Creator" --self-test
```

The build uses PyInstaller's default ad hoc signing. Developer ID signing and
Apple notarization are not configured. Review dependency licenses, including
PyQt5 and the selected FFmpeg build, before distributing binaries.

## Project files

| File | Purpose |
| --- | --- |
| `srt-creator.py` | Application, transcription worker, and exporters |
| `icon.png` | Original 1024 × 1024 application icon |
| `requirements.txt` | Direct runtime dependencies |
| `requirements-build.txt` | Runtime and packaging dependencies |
| `requirements-lock-macos-arm64.txt` | Exact dependency versions for the ARM64 build |
| `SRT-Creator.spec` | PyInstaller macOS bundle definition |
| `scripts/build_macos.py` | Icon, app, and DMG build automation |
| `.gitignore` | Keeps installers, caches, and environments out of Git |
| `.gitattributes` | Text line endings and binary file handling |

Whisper is pinned; other dependencies use version ranges. These are reconstructed
requirements, not a recovered lockfile for the original installer. After a
successful build, save `python -m pip freeze` with your release notes to record
the exact environment used.

## Release validation

The initial ARM64 build passed the packaged app self-test, disk-image integrity
check, and ad hoc code-signature verification. The app was also tested directly
from the mounted DMG. Real speech recognition and operation on a separate Mac
have not yet been verified.

Installers and SHA-256 checksums are published under
[Releases](https://github.com/samoxin1974/Whisper-SRT-Creator/releases).
Generated applications, virtual environments, models, and caches are excluded
from the source repository.

## References

- [Whisper installation and FFmpeg requirements](https://github.com/openai/whisper#setup)
- [PyInstaller spec files and macOS bundles](https://pyinstaller.org/en/stable/spec-files.html)
