# Llama.cpp GUI Launcher

A **PySide6**-based graphical frontend for [llama.cpp](https://github.com/ggerganov/llama.cpp), supporting Windows / Linux / WSL.

- Visual model parameter configuration
- llama.cpp binary download (aria2c 16-thread acceleration)
- Process management with external console
- Dark / Light dual themes
- 简体中文 / English / 日本語

---
## Screenshots
<img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/0e132d24-9b0c-423c-b6a7-f01ce65bfa2c" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/b26ccd20-18c3-46ab-b5d5-da7ac86ff926" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/ceaf52df-077c-4eb7-b5e8-355f6ccb2c12" />



## Quick Start

### Requirements

- **Python** 3.8+
- **PySide6** ≥ 6.5.0

### Installation

All dependencies are declared in `requirements.txt` and installed via standard pip.

#### Windows

| Method | Action | Notes |
|--------|--------|-------|
| pip | Double-click `setup_pip.bat` | Install to system Python |
| uv | Double-click `setup_uv.bat` | Isolated `.venv` virtual environment |

Or manually: `pip install -r requirements.txt`

#### Linux / macOS

```bash
chmod +x setup_pip.sh setup_uv.sh start.sh
```

| Method | Action | Notes |
|--------|--------|-------|
| pip | `bash setup_pip.sh` | Install to system Python |
| uv | `bash setup_uv.sh` | Isolated `.venv` virtual environment |

Or manually: `pip3 install -r requirements.txt`

### Launch

| Platform | Action |
|----------|--------|
| Windows | Double-click `start.bat` |
| Linux/macOS | `bash start.sh` |

`start.bat` / `start.sh` auto-detect uv `.venv` > system Python, works out of the box.

---

## User Guide

### Basic Configuration

1. Open the **⚙ Settings** tab
2. Set **Bin Directory** — path containing `llama-cli` / `llama-server`
3. Set **Model Directory** — path containing `.gguf` files
4. Switch to the **📊 Parameters** tab
5. Select a model from the dropdown → adjust parameters → click **▶ Start**

### Download Binaries

If no local binaries are available:

1. In Settings, click **📡 Fetch Available Files**
2. Wait for the platform-specific release list (cached for 30 minutes on first fetch)
3. Find the desired backend in the button list and click to download
4. After download, files are auto-extracted to the Bin directory and detection is refreshed

Downloads use the GitHub Release API with aria2c (`--split=16 --min-split-size=1M`) multi-threaded acceleration.

### Server Mode

Check **Server (API) Mode** before starting to auto-open the browser at `http://localhost:8080`. The port is customizable.

### Model Presets

Each model saves its parameter preset independently. Presets are auto-loaded when switching models. Click **💾 Save** to store current parameters, **🗑 Delete** to clear.

### Reasoning Mode

- **Normal** — `--reasoning on`; thinking is output normally. The "Think Budget" field sets the reasoning token budget (`--reasoning-budget N`, effective for models/versions that support it)
- **Hidden** — `-rea off`; disables thinking (only works for models with reasoning support, e.g. Qwen3 / DeepSeek families; text-style thinking models like VibeThinker cannot disable thinking via parameters)

### External Console

Enable to interact via stdin in a terminal window.

---

## Project Structure

```
├── main.py                      # Main entry point
├── start.bat / start.sh         # Launch scripts
├── setup_pip.bat / setup_pip.sh # pip install
├── setup_uv.bat / setup_uv.sh   # uv install
│
├── src/
│   ├── config.py                # Paths / QSS loader / i18n engine / defaults
│   ├── widgets.py               # Custom widgets (collapsible panel / combobox / console)
│   ├── download.py              # Download thread + VRAM detection thread
│   ├── backends.py              # Backend registry (CUDA/Vulkan/SYCL/CPU)
│   ├── launcher.py              # Process launch thread
│   ├── platform.py              # Platform dispatch (Win/Linux auto-import)
│   ├── platform_win.py          # Windows platform functions
│   └── platform_linux.py        # Linux platform functions
│
├── assets/
│   ├── qss/dark_style.qss       # Dark theme stylesheet
│   ├── qss/light_style.qss      # Light theme stylesheet
│   ├── ui_config.json           # UI display element configuration
│   └── README.md
│
└── locales/
    ├── zh.json                  # Simplified Chinese
    ├── en.json                  # English
    └── ja.json                  # Japanese
```

Auto-generated at runtime (recommended for `.gitignore`):

| File | Description |
|------|-------------|
| `launcher_config.json` | Window position, presets, language, theme and other persistent config |
| `assets/release_cache.json` | GitHub Release cache (valid for 30 minutes) |
| `bin/` | Downloaded llama.cpp binaries |
| `.venv/` | uv virtual environment |

---

## Customization

### Changing Appearance

Edit `assets/qss/dark_style.qss` or `assets/qss/light_style.qss` using standard Qt Style Sheet syntax. Restart to apply.

Dark theme color system:

| Level | Color | Usage |
|-------|-------|-------|
| Base | `#1e1e2e` | Window / tab background |
| Surface | `#28283c` | Input / combobox / button |
| Hover | `#323248` | Mouse hover highlight |
| Border | `#3a3a50` | Divider / input border |
| Accent | `#5a9cf0` | Focus / selection / link |

Light theme mirror: `#f2f3f5` → `#ffffff` → `#e8eaf0` → `#d4d6dc` / `#3d88e0`

### Changing Text

| Need | File |
|------|------|
| i18n translations | `locales/*.json` |

### Adding a New Language

Place a `.json` file with the same structure as `zh.json` in `locales/`. The filename is the language code. The Settings dropdown will list it automatically.

---

## Backend Support

Downloadable backends (platform-adaptive, only `.zip` or `.tar.gz` shown):

| Backend | Windows | Linux |
|---------|:-------:|:-----:|
| NVIDIA CUDA 12.4 / 13.1 | ✅ | ✅ |
| AMD HIP / ROCm | ✅ | ✅ |
| Vulkan (Universal) | ✅ | ✅ |
| Intel SYCL / OpenVINO | ✅ | ✅ |
| CPU (Universal) | ✅ | ✅ |
| ARM64 | ✅ | ✅ |
| macOS | — | ✅ |

---

## Platform Notes

### Linux

- **aria2c** — Auto-attempts `sudo apt install aria2` / `sudo pacman -S aria2` on first download
- **Script export** — Saved as `.sh` and auto `chmod 755`
- **External console** — Launched via `subprocess.Popen` in system terminal
- **VRAM detection** — Depends on `nvidia-smi`

### macOS

- If double-click doesn't work → run `python3 main.py` in terminal
- Download functionality adapted for `.tar.gz`
- aria2c requires manual install: `brew install aria2`

### WSL

- GUI requires Windows-side X Server (VcXsrv / GWSL) or WSLg
- Download works normally
- Use Linux-format file paths

---

## FAQ

**Q: "Executable not found" error on startup?**  
A: Set the Bin directory in Settings, or click **📡 Fetch Available Files** to download.

**Q: How do I report an issue?**  
A: Please use the GitHub Issues feature responsibly.

**Q: How do I switch languages?**  
A: Settings → 🎨 Appearance → Language dropdown, takes effect instantly.

**Q: UI font too small / too large?**  
A: Settings → 📐 Scale → drag the slider (50%-200%). Adaptive mode scales with window size.

**Q: Download speed is slow?**  
A: Edit `MIRROR_BASE_URLS` in `src/config.py` to add mirrors, or set `PROXY_HOST` / `PROXY_PORT`. Using a proxy or downloading files manually is recommended.

**Q: How do I save current parameters for later use?**  
A: Click **💾 Save** on the Parameters tab. Parameters are stored per model name and auto-restored on model switch.

---

## License

MIT License
