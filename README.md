# Munchie MiniVideo Converter

Create tiny looping animations from videos with a clean Qt GUI. Supports animated WebP, GIF, and APNG, with optional motion interpolation to boost frame rate.

### Highlights
- **Outputs**: WebP, GIF, APNG
- **Inputs**: `.mp4`, `.mkv`, `.webm` (anything your `ffmpeg` can read)
- **Controls**: width, FPS, time-lapse speed, loop, WebP quality
- **Motion interpolation**: synthesize in-between frames for smoother motion
- **Live logs**: full `ffmpeg` command and output
- **Codec preflight**: detects missing H.264/HEVC decoders and displays fix instructions per distro

---

## Install

### Prerequisites
- `ffmpeg` (a full build with H.264/HEVC decoders; see below for distro notes)
- Python 3.10+
- `pip`

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run
```bash
python munchie_gui.py
```

---

## Usage
1) Open the app and select an input video.
2) Choose your output format (`webp`, `gif`, or `apng`).
3) Set options:
   - **Width (px)**: output width (height preserves aspect ratio)
   - **FPS**: target frames per second
   - **Speed (×)**: time-lapse factor (8× makes it 8 times faster)
   - **Loop forever**: keep repeating animation
   - **WebP quality**: 0–100 (lossy; 0 is lowest, 100 is highest)
   - **Frame interpolation**: creates in-between frames for smoother motion (uses ffmpeg `minterpolate`)
4) Click Convert and watch the log panel.

Tips:
- For **WebP/APNG**, higher FPS works well. For **GIF**, high FPS can bloat size and cause banding/dither artifacts.
- Interpolation increases compute time. If encodes feel slow, try lower FPS or disable interpolation.

---

## How it works (high level)
- The app builds a filter chain: `setpts` (speed) → `minterpolate` (optional) → `fps` → `setsar` → `scale`.
- WebP and APNG are encoded directly in one pass.
- GIF uses a palette two-pass for better color quality.
- Before converting, the app preflights your system:
  - Probes input codec via `ffprobe` or a fallback using `ffmpeg -i` parsing.
  - Enumerates available decoders from `ffmpeg -decoders`.
  - Runs a tiny decode to NULL to catch failing setups (e.g., `libopenh264` on Fedora).
  - If missing/unsupported, shows tailored install guidance based on your distro.

---

## ffmpeg on Linux (common setups)

Some distros ship a restricted `ffmpeg` that can’t decode H.264/HEVC. Use these commands to install a full-featured build:

- Fedora (RPM Fusion, replace ffmpeg-free):
  - `sudo dnf install https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm`
  - `sudo dnf swap ffmpeg-free ffmpeg --allowerasing`
  - `sudo dnf install ffmpeg ffmpeg-libs`
  - Optional multimedia refresh (avoid weak deps): `sudo dnf update @multimedia --setopt="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin`

- Ubuntu/Debian:
  - `sudo apt update`
  - `sudo apt install ffmpeg`
  - Ubuntu (optional): `sudo apt install libavcodec-extra`

- Arch/Manjaro:
  - `sudo pacman -Syu ffmpeg`

- openSUSE (Packman repo):
  - `sudo zypper ar -cfp 90 https://ftp.gwdg.de/pub/linux/misc/packman/suse/openSUSE_Tumbleweed/ packman`
  - `sudo zypper dup --from packman --allow-vendor-change`
  - `sudo zypper in ffmpeg`

Verify decoders:
```bash
ffmpeg -hide_banner -decoders | grep -E '(^|\s)(h264|hevc|vp9|av1)\b'
```

---

## Troubleshooting
- “Unable to create decoder”, “no decoder found”: install full `ffmpeg` as above. Restart the app after installing.
- Wayland/HiDPI scaling issues: set `QT_SCALE_FACTOR=1.25` (or similar) before launching.
- Very large GIFs: try lowering width or FPS, or switch to WebP/APNG.

---

## Development

### Tech stack
- Python + PySide6 (Qt 6) GUI
- `ffmpeg` for all media processing

### Project layout
- `munchie_gui.py`: main GUI and conversion logic
- `requirements.txt`: Python dependencies (PySide6)
- `munchiescript.sh`: helper shell script (optional)

### Run from source
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python munchie_gui.py
```

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.
