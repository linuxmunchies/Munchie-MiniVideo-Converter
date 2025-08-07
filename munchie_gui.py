#!/usr/bin/env python3

import os
import sys
import shutil
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Optional, Set, Tuple
"""
GUI app to convert videos to mini animations (WebP, GIF, APNG) with optional
frame interpolation. Includes cross-distro codec checks and guidance.
"""

from PySide6.QtCore import Qt, QProcess, QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ConversionOptions:
    input_path: str
    output_path: str
    output_format: str  # "webp", "gif", or "apng"
    target_width_px: int
    frames_per_second: int
    speed_multiplier: float  # e.g. 8.0 → 8x faster
    webp_quality: int  # 0-100, only for webp
    loop_forever: bool
    interpolate: bool


class MiniVideoConverterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Munchie MiniVideo Converter")
        self.setMinimumSize(QSize(700, 520))

        self.ffmpeg_path: Optional[str] = shutil.which("ffmpeg")
        self.ffprobe_path: Optional[str] = shutil.which("ffprobe")

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # File selection
        file_box = QGroupBox("Files")
        file_layout = QGridLayout(file_box)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Select input video (.mp4, .mkv, .webm)")
        browse_in_btn = QPushButton("Browse…")
        browse_in_btn.clicked.connect(self._choose_input)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Select output file (.webp or .gif)")
        browse_out_btn = QPushButton("Browse…")
        browse_out_btn.clicked.connect(self._choose_output)

        file_layout.addWidget(QLabel("Input video"), 0, 0)
        file_layout.addWidget(self.input_edit, 0, 1)
        file_layout.addWidget(browse_in_btn, 0, 2)
        file_layout.addWidget(QLabel("Output file"), 1, 0)
        file_layout.addWidget(self.output_edit, 1, 1)
        file_layout.addWidget(browse_out_btn, 1, 2)

        # Options
        options_box = QGroupBox("Options")
        form = QFormLayout(options_box)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["webp", "gif", "apng"])
        self.format_combo.currentTextChanged.connect(self._on_format_change)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(64, 2048)
        self.width_spin.setValue(480)
        self.width_spin.setSingleStep(16)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(10)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 32)
        self.speed_spin.setValue(8)

        self.webp_quality_slider = QSlider(Qt.Horizontal)
        self.webp_quality_slider.setRange(0, 100)
        self.webp_quality_slider.setValue(60)
        self.webp_quality_label = QLabel("60")
        self.webp_quality_slider.valueChanged.connect(
            lambda v: self.webp_quality_label.setText(str(v))
        )

        self.loop_checkbox = QCheckBox("Loop forever")
        self.loop_checkbox.setChecked(True)

        self.interpolate_checkbox = QCheckBox("Frame interpolation (motion)")
        self.interpolate_checkbox.setChecked(False)

        form.addRow("Format", self.format_combo)
        form.addRow("Width (px)", self.width_spin)
        form.addRow("FPS", self.fps_spin)
        form.addRow("Speed (×)", self.speed_spin)

        quality_row = QHBoxLayout()
        quality_row.addWidget(self.webp_quality_slider)
        quality_row.addWidget(self.webp_quality_label)
        quality_row_container = QWidget()
        quality_row_container.setLayout(quality_row)
        form.addRow("WebP quality", quality_row_container)

        form.addRow("", self.loop_checkbox)
        form.addRow("", self.interpolate_checkbox)

        # Actions
        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self._start_conversion)
        actions_row.addWidget(self.convert_btn)

        # Log
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log_edit)

        layout.addWidget(file_box)
        layout.addWidget(options_box)
        layout.addLayout(actions_row)
        layout.addWidget(log_box, 1)

        # Menu (about/help)
        help_action = QAction("About", self)
        help_action.triggered.connect(self._show_about)
        self.menuBar().addAction(help_action)

        self.process: Optional[QProcess] = None
        self._on_format_change(self.format_combo.currentText())

        if not self.ffmpeg_path:
            QMessageBox.critical(
                self,
                "ffmpeg not found",
                "ffmpeg is required but was not found in PATH. Please install it and try again.",
            )
        else:
            # Warm up decoder list cache so first conversion feels snappy
            try:
                _ = self._get_ffmpeg_decoders()
            except Exception:
                pass

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select input video",
            os.path.expanduser("~"),
            "Video files (*.mp4 *.mkv *.webm);;All files (*)",
        )
        if path:
            self.input_edit.setText(path)
            # Auto-suggest output filename
            base, _ext = os.path.splitext(path)
            fmt = self.format_combo.currentText()
            self.output_edit.setText(base + f".{fmt}")

    def _choose_output(self) -> None:
        fmt = self.format_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select output file",
            os.path.expanduser("~"),
            f"{fmt.upper()} files (*.{fmt});;All files (*)",
        )
        if path:
            # Ensure correct extension
            if not path.lower().endswith(f".{fmt}"):
                path = path + f".{fmt}"
            self.output_edit.setText(path)

    def _on_format_change(self, fmt: str) -> None:
        is_webp = fmt == "webp"
        self.webp_quality_slider.setEnabled(is_webp)
        self.webp_quality_label.setEnabled(is_webp)

        # Update output file suggestion if input already chosen
        in_path = self.input_edit.text().strip()
        if in_path:
            base, _ = os.path.splitext(in_path)
            self.output_edit.setText(base + f".{fmt}")

    def _collect_options(self) -> Optional[ConversionOptions]:
        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()
        fmt = self.format_combo.currentText().strip()

        if not input_path:
            QMessageBox.warning(self, "Missing input", "Please choose an input video file.")
            return None
        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "Invalid input", "The selected input file does not exist.")
            return None
        if not output_path:
            QMessageBox.warning(self, "Missing output", "Please choose an output file path.")
            return None
        out_dir = os.path.dirname(output_path) or "."
        if not os.path.isdir(out_dir):
            QMessageBox.warning(self, "Invalid output", "The output directory does not exist.")
            return None

        options = ConversionOptions(
            input_path=input_path,
            output_path=output_path,
            output_format=fmt,
            target_width_px=int(self.width_spin.value()),
            frames_per_second=int(self.fps_spin.value()),
            speed_multiplier=float(self.speed_spin.value()),
            webp_quality=int(self.webp_quality_slider.value()),
            loop_forever=bool(self.loop_checkbox.isChecked()),
            interpolate=bool(self.interpolate_checkbox.isChecked()),
        )
        return options

    def _append_log(self, text: str) -> None:
        self.log_edit.append(text)
        self.log_edit.ensureCursorVisible()

    def _toggle_ui(self, enabled: bool) -> None:
        for widget in [
            self.input_edit,
            self.output_edit,
            self.format_combo,
            self.width_spin,
            self.fps_spin,
            self.speed_spin,
            self.webp_quality_slider,
            self.loop_checkbox,
            self.convert_btn,
        ]:
            widget.setEnabled(enabled)

    def _start_conversion(self) -> None:
        if not self.ffmpeg_path:
            QMessageBox.critical(self, "ffmpeg not found", "ffmpeg is not available in PATH.")
            return

        options = self._collect_options()
        if not options:
            return

        self.log_edit.clear()
        self._append_log("Starting conversion…")
        self._toggle_ui(False)

        # Preflight: verify decoder availability for the input
        detected_codec = self._probe_video_codec(options.input_path)
        self._append_log(f"Detected video codec: {detected_codec or 'unknown'}")
        ok, msg = self._preflight_decoding(options.input_path)
        if not ok:
            self._append_log(msg)
            QMessageBox.critical(self, "Missing codec support", msg)
            self._toggle_ui(True)
            return

        # Build command(s)
        if options.output_format == "webp":
            cmd = self._build_webp_command(options)
            self._run_single_process(cmd)
        elif options.output_format == "apng":
            cmd = self._build_apng_command(options)
            self._run_single_process(cmd)
        else:
            # GIF palette two-pass
            cmds = self._build_gif_commands(options)
            self._run_multi_process(cmds)

    def _build_webp_command(self, o: ConversionOptions) -> list[str]:
        vf = self._build_vf_chain(o)
        decoder_args = self._decoder_args_for_input(o.input_path)
        # Single-step encode to WebP
        args = [
            self.ffmpeg_path or "ffmpeg",
            "-hide_banner",
            "-y",
            *decoder_args,
            "-i",
            o.input_path,
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libwebp",
            "-lossless",
            "0",
            "-q:v",
            str(o.webp_quality),
        ]
        if o.loop_forever:
            args += ["-loop", "0"]  # infinite
        # If not looping, omit -loop for single play
        args += [o.output_path]
        return args

    def _build_gif_commands(self, o: ConversionOptions) -> list[list[str]]:
        vf_core = self._build_vf_chain(o)

        temp_dir = tempfile.mkdtemp(prefix="munchie_")
        palette_path = os.path.join(temp_dir, "palette.png")
        decoder_args = self._decoder_args_for_input(o.input_path)

        gen_palette = [
            self.ffmpeg_path or "ffmpeg",
            "-hide_banner",
            "-y",
            *decoder_args,
            "-i",
            o.input_path,
            "-vf",
            f"{vf_core},palettegen",
            palette_path,
        ]
        use_palette = [
            self.ffmpeg_path or "ffmpeg",
            "-hide_banner",
            "-y",
            *decoder_args,
            "-i",
            o.input_path,
            "-i",
            palette_path,
            "-lavfi",
            f"{vf_core}[x];[x][1:v]paletteuse=dither=sierra2_4a",
            "-an",
        ]
        if o.loop_forever:
            use_palette += ["-loop", "0"]  # infinite
        # If not looping, omit -loop for single play
        use_palette += [o.output_path]
        # Store the palette path on the instance to clean it later
        self._temp_palette_dir = temp_dir
        return [gen_palette, use_palette]

    def _build_apng_command(self, o: ConversionOptions) -> list[str]:
        vf = self._build_vf_chain(o)
        decoder_args = self._decoder_args_for_input(o.input_path)
        args = [
            self.ffmpeg_path or "ffmpeg",
            "-hide_banner",
            "-y",
            *decoder_args,
            "-i",
            o.input_path,
            "-vf",
            vf,
            "-an",
            "-c:v",
            "apng",
        ]
        if o.loop_forever:
            # APNG uses -plays (0 for infinite)
            args += ["-plays", "0"]
        args += [o.output_path]
        return args

    def _build_vf_chain(self, o: ConversionOptions) -> str:
        setpts_factor = 1.0 / max(o.speed_multiplier, 0.001)
        fps_part = (
            f"minterpolate=fps={o.frames_per_second}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
            if o.interpolate
            else f"fps={o.frames_per_second}"
        )
        vf = (
            f"setpts={setpts_factor}*PTS,"
            f"{fps_part},"
            f"setsar=1,"
            f"scale={o.target_width_px}:-2:flags=lanczos"
        )
        return vf

    def _decoder_args_for_input(self, input_path: str) -> list[str]:
        """Return decoder selection args (placed BEFORE "-i <input>") based on input codec.

        This can steer ffmpeg away from problematic external decoders like libopenh264
        by explicitly selecting the built-in software decoders when available.
        """
        try:
            codec = (self._probe_video_codec(input_path) or "").lower()
        except Exception:
            codec = None

        if codec in {"h264", "avc1"}:
            available_decoders = self._get_ffmpeg_decoders()
            if "h264" in available_decoders:
                return ["-c:v", "h264"]
            # If only hardware decoders exist, let ffmpeg auto-pick
            return []

        if codec in {"hevc", "h265"}:
            available_decoders = self._get_ffmpeg_decoders()
            if "hevc" in available_decoders:
                return ["-c:v", "hevc"]
            return []

        return []

    def _probe_video_codec(self, input_path: str) -> Optional[str]:
        """Probe codec via ffprobe; if unavailable, fall back to parsing ffmpeg -i output."""
        if self.ffprobe_path:
            try:
                result = subprocess.run(
                    [
                        self.ffprobe_path,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=codec_name",
                        "-of",
                        "default=nw=1:nk=1",
                        input_path,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                codec = result.stdout.strip().splitlines()[0] if result.stdout else None
                if codec:
                    return codec
            except Exception:
                pass

        # Fallback: parse ffmpeg -i output
        return self._probe_codec_via_ffmpeg_i(input_path)

    def _probe_codec_via_ffmpeg_i(self, input_path: str) -> Optional[str]:
        if not self.ffmpeg_path:
            return None
        try:
            res = subprocess.run(
                [self.ffmpeg_path, "-hide_banner", "-i", input_path],
                capture_output=True,
                text=True,
            )
            text = (res.stderr or "") + "\n" + (res.stdout or "")
            # Look for a line with "Video: <codec>"
            for line in text.splitlines():
                if "Video:" in line:
                    try:
                        after = line.split("Video:", 1)[1].strip()
                        first = after.split(",", 1)[0].strip()
                        token = first.split()[0].strip().lower()
                        # Common normalizations
                        if token == "avc1":
                            token = "h264"
                        if token == "h265":
                            token = "hevc"
                        return token
                    except Exception:
                        continue
        except Exception:
            return None
        return None

    def _get_ffmpeg_decoders(self) -> Set[str]:
        """Return a set of available video decoder names from ffmpeg -decoders.

        The names are normalized to lowercase and include primary video decoders
        like 'h264', 'hevc', 'vp9', 'av1', etc.
        """
        cache_key = "_cached_decoders"
        cached = getattr(self, cache_key, None)
        if isinstance(cached, set):
            return cached
        if not self.ffmpeg_path:
            return set()
        try:
            proc = subprocess.run(
                [self.ffmpeg_path, "-hide_banner", "-decoders"],
                capture_output=True,
                text=True,
                check=True,
            )
            decoders: Set[str] = set()
            for line in proc.stdout.splitlines():
                line = line.strip()
                # Lines look like: " V.... h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10"
                if not line or not (line.startswith("V") or line.startswith(".V")):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1].strip().lower()
                    decoders.add(name)
            setattr(self, cache_key, decoders)
            return decoders
        except Exception:
            return set()

    def _decode_probe_details(self, input_path: str, prefer_decoder: Optional[str]) -> Tuple[bool, str]:
        """Try decoding a tiny portion to NULL; return (ok, stderr_text)."""
        if not self.ffmpeg_path:
            return False, "ffmpeg not found"
        cmd = [self.ffmpeg_path, "-hide_banner", "-v", "error"]
        if prefer_decoder:
            cmd += ["-c:v", prefer_decoder]
        cmd += ["-t", "0.2", "-i", input_path, "-f", "null", "-"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            return res.returncode == 0, (res.stderr or "")
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def _preflight_decoding(self, input_path: str) -> Tuple[bool, str]:
        """Ensure we can decode the input video. If not, return False and a helpful message."""
        codec = (self._probe_video_codec(input_path) or "").lower()
        if not codec:
            return True, ""  # Unknown codec; let ffmpeg try

        # Normalize common aliases
        if codec == "avc1":
            codec = "h264"
        if codec == "h265":
            codec = "hevc"

        # If it's a common codec, check that a robust decoder exists
        decoders = self._get_ffmpeg_decoders()

        def ok_with(dec: str) -> bool:
            # Prefer native software decoders 'h264'/'hevc' when present
            if dec in decoders:
                return True
            # Accept hardware decoders as a fallback
            if f"{dec}_cuvid" in decoders or f"{dec}_qsv" in decoders or f"{dec}_vaapi" in decoders:
                return True
            return False

        requested_decoder: Optional[str] = None
        if codec in {"h264", "hevc"}:
            requested_decoder = codec if codec in decoders else None
            if not ok_with(codec):
                help_text = self._codec_help_message(codec)
                return False, help_text

        # Try a tiny decode run to catch failing decoders
        prefer = requested_decoder
        ok, stderr_text = self._decode_probe_details(input_path, prefer_decoder=prefer)
        if not ok:
            inferred = codec
            txt = (stderr_text or "").lower()
            if "openh264" in txt:
                inferred = "h264"
            elif "no decoder" in txt and "hevc" in txt:
                inferred = "hevc"
            elif "no decoder" in txt and "h264" in txt:
                inferred = "h264"
            help_text = self._codec_help_message(inferred or codec or "h264")
            return False, help_text

        return True, ""

    def _detect_distro(self) -> Tuple[str, str]:
        """Return (id_like, id) from /etc/os-release (lowercased), best-effort."""
        os_release = "/etc/os-release"
        like = ""; os_id = ""
        try:
            with open(os_release, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("ID_LIKE="):
                        like = line.split("=", 1)[1].strip().strip('"').lower()
                    elif line.startswith("ID="):
                        os_id = line.split("=", 1)[1].strip().strip('"').lower()
        except Exception:
            pass
        return like, os_id

    def _codec_help_message(self, codec: str) -> str:
        """Return actionable guidance to install proper ffmpeg decoders per distro."""
        like, os_id = self._detect_distro()
        lines = [
            f"It looks like your ffmpeg cannot decode {codec.upper()} on this system.",
            "\nRecommended fix:",
        ]

        def add(cmds: list[str]) -> None:
            for c in cmds:
                lines.append(f"  - {c}")

        if os_id in {"fedora"} or "fedora" in like:
            add([
                "Enable RPM Fusion (free + nonfree):",
                "sudo dnf install https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm",
                "Replace ffmpeg-free with full ffmpeg:",
                "sudo dnf swap ffmpeg-free ffmpeg --allowerasing",
                "Then install libraries:",
                "sudo dnf install ffmpeg ffmpeg-libs",
                "Optional multimedia refresh (avoid weak deps):",
                "sudo dnf update @multimedia --setopt=install_weak_deps=False --exclude=PackageKit-gstreamer-plugin",
            ])
        elif os_id in {"ubuntu", "debian"} or any(x in like for x in ["debian", "ubuntu"]):
            add([
                "sudo apt update",
                "sudo apt install ffmpeg",
                "On Ubuntu, if needed: sudo apt install libavcodec-extra",
            ])
        elif os_id in {"arch", "manjaro"} or any(x in like for x in ["arch"]):
            add([
                "sudo pacman -Syu ffmpeg",
            ])
        elif os_id in {"opensuse-tumbleweed", "opensuse-leap", "opensuse"} or "suse" in like:
            add([
                "Enable Packman repo and install full ffmpeg (commands vary by version):",
                "sudo zypper ar -cfp 90 https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Tumbleweed/ packman",
                "sudo zypper dup --from packman --allow-vendor-change",
                "sudo zypper in ffmpeg",
            ])
        else:
            add([
                "Install a full-featured ffmpeg from your distribution or a trusted multimedia repo.",
                "Ensure software decoders for H.264 (h264) and HEVC (hevc) are present in `ffmpeg -decoders`.",
            ])

        lines.append("\nAfter installing, restart this app and try again.")
        return "\n".join(lines)

    def _run_single_process(self, cmd: list[str]) -> None:
        self.process = QProcess(self)
        # Important: merge stderr to stdout so all logs appear in one stream
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_proc_output)
        self.process.finished.connect(self._on_proc_finished)
        self._append_log("Running: " + " ".join(self._quote_parts(cmd)))
        self.process.start(cmd[0], cmd[1:])

    def _run_multi_process(self, cmds: list[list[str]]) -> None:
        # Run a small chain: when one finishes successfully, start the next
        self._gif_cmds = cmds
        self._gif_step_index = -1
        self._start_next_gif_step()

    def _start_next_gif_step(self) -> None:
        self._gif_step_index += 1
        if self._gif_step_index >= len(getattr(self, "_gif_cmds", [])):
            self._on_proc_finished(0, QProcess.ExitStatus.NormalExit)
            return

        cmd = self._gif_cmds[self._gif_step_index]
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_proc_output)
        self.process.finished.connect(self._on_gif_step_finished)
        step_label = "palettegen" if self._gif_step_index == 0 else "encode"
        self._append_log(f"Running ({step_label}): " + " ".join(self._quote_parts(cmd)))
        self.process.start(cmd[0], cmd[1:])

    def _on_gif_step_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self._start_next_gif_step()
        else:
            self._on_proc_finished(exit_code, exit_status)

    def _on_proc_output(self) -> None:
        if not self.process:
            return
        data = self.process.readAllStandardOutput()
        try:
            text = bytes(data).decode("utf-8", errors="ignore").strip()
        except Exception:
            text = str(data)
        if text:
            self._append_log(text)

    def _on_proc_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        # Cleanup temp dir for GIF palette if present
        temp_dir = getattr(self, "_temp_palette_dir", None)
        if temp_dir and os.path.isdir(temp_dir):
            try:
                for name in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, name))
                    except Exception:
                        pass
                os.rmdir(temp_dir)
            except Exception:
                pass
        if hasattr(self, "_temp_palette_dir"):
            delattr(self, "_temp_palette_dir")

        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self._append_log("\nDone! ✅")
            QMessageBox.information(self, "Success", "Conversion completed successfully.")
        else:
            self._append_log("\nFailed. ❌")
            QMessageBox.critical(
                self,
                "Conversion failed",
                "ffmpeg reported an error. See the log for details.",
            )
        self._toggle_ui(True)
        self.process = None

    def _quote_parts(self, parts: list[str]) -> list[str]:
        def q(p: str) -> str:
            if " " in p or "\t" in p:
                return f'"{p}"'
            return p
        return [q(p) for p in parts]

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About",
            (
                "Munchie MiniVideo Converter\n\n"
                "Generate mini WebP or GIF animations from video files using ffmpeg.\n"
                "- Formats: mp4, mkv, webm input → webp/gif output\n"
                "- Options: width, fps, speed, loop, quality (WebP)\n"
            ),
        )


def main() -> int:
    app = QApplication(sys.argv)
    win = MiniVideoConverterWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


