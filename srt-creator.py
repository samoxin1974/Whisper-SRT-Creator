import sys
import os
import ctypes
import time
import json
import multiprocessing
import threading
import whisper

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QCheckBox, QFileDialog,
    QProgressBar, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon


LANGUAGES = {
    "Auto Detect": None,
    "English": "en",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Russian": "ru",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese": "zh",
    "Arabic": "ar",
    "Polish": "pl",
    "Turkish": "tr",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Norwegian": "no",
    "Ukrainian": "uk",
}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]


def configure_bundled_ffmpeg():
    """Make the bundled ffmpeg visible to Whisper inside the frozen macOS app."""
    if not getattr(sys, "frozen", False):
        return None

    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())

    contents_dir = os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))
    bundled_bin = os.path.join(contents_dir, "Resources", "bin")
    bundled_ffmpeg = os.path.join(bundled_bin, "ffmpeg")
    if not os.path.exists(bundled_ffmpeg):
        return None

    current_path = os.environ.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    if bundled_bin not in path_parts:
        os.environ["PATH"] = os.pathsep.join([bundled_bin, *path_parts])
    return bundled_ffmpeg


# ── Crockford Base32 ULID generator (no extra dependencies) ──────────

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid():
    """Return a 26-char Crockford-Base32 ULID (timestamp + random)."""
    ts_ms = int(time.time() * 1000)
    # 10-char timestamp (48-bit ms)
    t_chars = []
    for _ in range(10):
        t_chars.append(_CROCKFORD[ts_ms & 0x1F])
        ts_ms >>= 5
    t_chars.reverse()
    # 16-char randomness (80-bit)
    rand_bytes = os.urandom(10)
    rand_val = int.from_bytes(rand_bytes, "big")
    r_chars = []
    for _ in range(16):
        r_chars.append(_CROCKFORD[rand_val & 0x1F])
        rand_val >>= 5
    r_chars.reverse()
    return "".join(t_chars) + "".join(r_chars)


# ── Tokenizer — splits phrase text into text / punct ranges ──────────

def tokenize_text(value, monologue, element_counter):
    """
    Walk *value* character-by-character and produce a list of range dicts
    matching the JSON schema.  Returns (ranges_list, next_element_counter).

    Rules (derived from the reference JSON):
      • A "text" token is a run of letters, digits, mid-word apostrophes
        (e.g. I'm, don't) and mid-word hyphens (e.g. right-click, read-only).
      • Every other single character becomes its own "punct" token
        (spaces, commas, periods, colons, semicolons, …).
    """
    ranges = []
    i = 0
    n = len(value)

    while i < n:
        ch = value[i]

        if ch.isalnum():
            # Start of a word
            start = i
            i += 1
            while i < n:
                c = value[i]
                if c.isalnum():
                    i += 1
                elif c in ("'", "\u2019") and i + 1 < n and value[i + 1].isalnum():
                    # mid-word apostrophe  (I'm, don't)
                    i += 2
                elif c == "-" and i + 1 < n and value[i + 1].isalnum():
                    # mid-word hyphen  (right-click, read-only)
                    i += 2
                else:
                    break
            ranges.append({
                "type": "text",
                "start": start,
                "length": i - start,
                "source": {
                    "monologue": monologue,
                    "element": element_counter,
                    "elementId": generate_ulid(),
                },
            })
            element_counter += 1
        else:
            # Single punct / whitespace character
            ranges.append({
                "type": "punct",
                "start": i,
                "length": 1,
                "source": {
                    "monologue": monologue,
                    "element": element_counter,
                    "elementId": generate_ulid(),
                },
            })
            element_counter += 1
            i += 1

    return ranges, element_counter


# ── JSON export (matches reference schema) ───────────────────────────

def segments_to_json(segments, schema_version="1.1.3"):
    """
    Convert Whisper segments into the JSON transcription format:
      { "phrases": [ { ts, value, ranges }, … ], "schemaVersion": "…" }
    """
    phrases = []
    monologue = 0
    element_counter = 0

    for seg in segments:
        text = seg["text"].strip()
        ts = round(seg["start"], 3)

        ranges, element_counter = tokenize_text(text, monologue, element_counter)
        # skip one element between phrases (matches reference file behaviour)
        element_counter += 1

        phrases.append({
            "ts": ts,
            "value": text,
            "ranges": ranges,
        })

    return json.dumps(
        {"phrases": phrases, "schemaVersion": schema_version},
        ensure_ascii=False,
    )


# ── SRT / VTT helpers (unchanged) ───────────────────────────────────

def format_timestamp_srt(seconds):
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def format_timestamp_vtt(seconds):
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{format_timestamp_srt(seg['start'])} --> {format_timestamp_srt(seg['end'])}")
        lines.append(seg['text'].strip())
        lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments):
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{format_timestamp_vtt(seg['start'])} --> {format_timestamp_vtt(seg['end'])}")
        lines.append(seg['text'].strip())
        lines.append("")
    return "\n".join(lines)


# ── Worker thread (unchanged) ────────────────────────────────────────

class TranscribeWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path, language, model_name):
        super().__init__()
        self.file_path = file_path
        self.language = language
        self.model_name = model_name

    def run(self):
        try:
            self.progress.emit("Loading Whisper model...")
            model = whisper.load_model(self.model_name)

            self.progress.emit("Transcribing... (this may take a while)")
            options = {}
            if self.language:
                options["language"] = self.language

            result = model.transcribe(self.file_path, **options)
            self.finished.emit(result["segments"])
        except Exception as e:
            self.error.emit(str(e))


# ── Main window ──────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Whisper Subtitle Generator")
        self.setMinimumWidth(600)
        self.file_path = None
        self.worker = None

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # File selector
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Model selector
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Whisper model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        self.model_combo.setCurrentText("base")
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        # Language selector
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        # Output format checkboxes  ← .json added here
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Output format:"))
        self.srt_check = QCheckBox(".srt")
        self.srt_check.setChecked(True)
        self.vtt_check = QCheckBox(".vtt")
        self.json_check = QCheckBox(".json")
        fmt_row.addWidget(self.srt_check)
        fmt_row.addWidget(self.vtt_check)
        fmt_row.addWidget(self.json_check)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Output folder
        out_row = QHBoxLayout()
        self.out_label = QLabel("Output: same folder as input file")
        out_btn = QPushButton("Change...")
        out_btn.clicked.connect(self.browse_output)
        out_row.addWidget(self.out_label, 1)
        out_row.addWidget(out_btn)
        layout.addLayout(out_row)
        self.output_dir = None

        # Generate button
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setFixedHeight(40)
        self.generate_btn.clicked.connect(self.generate)
        layout.addWidget(self.generate_btn)

        # Status log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        layout.addWidget(self.log)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio or video file", "",
            "Media files (*.mp3 *.wav *.m4a *.ogg *.flac *.mp4 *.mkv *.mov *.avi *.webm *.ts);;All files (*)"
        )
        if path:
            self.file_path = path
            self.file_label.setText(path)
            self.log.clear()

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_dir = folder
            self.out_label.setText(f"Output: {folder}")

    def log_msg(self, msg):
        self.log.append(msg)

    def generate(self):
        if not self.file_path:
            QMessageBox.warning(self, "No file", "Please select an audio or video file first.")
            return
        if (
            not self.srt_check.isChecked()
            and not self.vtt_check.isChecked()
            and not self.json_check.isChecked()
        ):
            QMessageBox.warning(self, "No format", "Please select at least one output format.")
            return

        lang_name = self.lang_combo.currentText()
        language = LANGUAGES[lang_name]
        model_name = self.model_combo.currentText()

        self.generate_btn.setEnabled(False)
        self.log.clear()
        self.log_msg(f"File: {self.file_path}")
        self.log_msg(f"Model: {model_name} | Language: {lang_name}")

        self.worker = TranscribeWorker(self.file_path, language, model_name)
        self.worker.progress.connect(self.log_msg)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_finished(self, segments):
        out_dir = self.output_dir or os.path.dirname(self.file_path)
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        out_base = os.path.join(out_dir, base_name)

        if self.srt_check.isChecked():
            path = out_base + ".srt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_srt(segments))
            self.log_msg(f"Saved: {path}")

        if self.vtt_check.isChecked():
            path = out_base + ".vtt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_vtt(segments))
            self.log_msg(f"Saved: {path}")

        if self.json_check.isChecked():
            path = out_base + ".json"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_json(segments))
            self.log_msg(f"Saved: {path}")

        self.log_msg("Done!")
        self.generate_btn.setEnabled(True)

    def on_error(self, msg):
        self.log_msg(f"ERROR: {msg}")
        self.generate_btn.setEnabled(True)


def main():
    multiprocessing.freeze_support()

    if "--self-test" in sys.argv:
        # Exercise packaged native libraries and assets without downloading a model.
        import tempfile
        import wave
        configure_bundled_ffmpeg()
        with tempfile.TemporaryDirectory(prefix="srt-self-test-") as directory:
            audio_path = os.path.join(directory, "silence.wav")
            with wave.open(audio_path, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(b"\x00\x00" * 16000)
            samples = whisper.load_audio(audio_path)
            mel = whisper.log_mel_spectrogram(samples)
            assert mel.shape[0] == 80
            from whisper.tokenizer import get_tokenizer
            tokenizer = get_tokenizer(multilingual=True, language="en")
            assert tokenizer.decode(tokenizer.encode("Test subtitles")) == "Test subtitles"
            segments = [{"start": 0.0, "end": 1.0, "text": "Test subtitles"}]
            assert "Test subtitles" in segments_to_srt(segments)
            assert segments_to_vtt(segments).startswith("WEBVTT")
            assert json.loads(segments_to_json(segments))["phrases"][0]["value"] == "Test subtitles"
        app = QApplication([sys.argv[0], "-platform", "offscreen"])
        window = MainWindow()
        assert window.windowTitle() == "Whisper Subtitle Generator"
        window.close()
        print("Self-test passed: FFmpeg, Whisper audio/assets, tokenizer, exports, Qt window.", flush=True)
        return

    # Windows: set AppUserModelID so the taskbar uses our icon instead of Python's
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "whisper.subtitle.generator"
        )

    configure_bundled_ffmpeg()

    app = QApplication(sys.argv)

    # Set the icon on the application (affects taskbar + all windows)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
