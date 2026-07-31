<div align="right">

**简体中文** &nbsp;|&nbsp; [English](readme/README_en.md) &nbsp;|&nbsp; [日本語](readme/README_ja.md)

</div>

# Llama.cpp 图形启动器

基于 **PySide6** 的 [llama.cpp](https://github.com/ggerganov/llama.cpp) 图形化前端，支持 Windows / Linux / WSL。

- 模型参数可视化配置
- llama.cpp 二进制下载（aria2c 16 线程加速）
- 进程管理与外部控制台
- 深色/亮色双主题
- 界面语言：简体中文 / English / 日本語

---
## 基本展示
<img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/0e132d24-9b0c-423c-b6a7-f01ce65bfa2c" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/b26ccd20-18c3-46ab-b5d5-da7ac86ff926" /><img width="518" height="659" alt="image" src="https://github.com/user-attachments/assets/ceaf52df-077c-4eb7-b5e8-355f6ccb2c12" />



## 快速开始

### 环境要求

- **Python** 3.8+
- **PySide6** ≥ 6.5.0

### 安装

所有依赖声明在 `requirements.txt`，统一通过标准 pip 安装。

#### Windows

| 方式 | 操作 | 说明 |
|------|------|------|
| pip | 双击 `setup_pip.bat` | 安装到系统 Python |
| uv | 双击 `setup_uv.bat` | 隔离 `.venv` 虚拟环境 |

或手动：`pip install -r requirements.txt`

#### Linux / macOS

```bash
chmod +x setup_pip.sh setup_uv.sh start.sh
```

| 方式 | 操作 | 说明 |
|------|------|------|
| pip | `bash setup_pip.sh` | 安装到系统 Python |
| uv | `bash setup_uv.sh` | 隔离 `.venv` 虚拟环境 |

或手动：`pip3 install -r requirements.txt`

### 启动

| 平台 | 操作 |
|------|------|
| Windows | 双击 `start.bat` |
| Linux/macOS | `bash start.sh` |

`start.bat` / `start.sh` 自动检测 uv `.venv` > 系统 Python，开箱即用。

---

## 使用指南

### 基本配置

1. 打开 **⚙ 设置** 标签页
2. 设置 **Bin 目录** — 包含 `llama-cli` / `llama-server` 的路径
3. 设置 **模型目录** — 存放 `.gguf` 文件的路径
4. 切换到 **📊 参数** 标签页
5. 从下拉框选择模型 → 调整参数 → 点击 **▶ 启动**

### 下载二进制

如无本地二进制文件：

1. 设置页点击 **📡 获取可用文件**
2. 等待获取当前平台 Release 列表（首次 30 分钟内使用缓存）
3. 在按钮列表中找到对应后端，点击下载
4. 下载完成后自动解压到 Bin 目录并刷新检测

下载基于 GitHub Release API，使用 aria2c (`--split=16 --min-split-size=1M`) 多线程加速。

### Server 模式

勾选 **Server (API) 模式** 后启动，自动打开浏览器访问 `http://localhost:8080`。端口可自定义。

### 模型预设

每个模型独立保存参数预设，切换模型时自动加载。点击 **💾 保存** 存储当前参数，**🗑 删除** 清除。

### 思考模式

- **正常** — 打印 ` response` 标签包围的内容
- **隐藏** — `--reasoning-format none --reasoning-budget 0 -rea off`
- **停止** — 遇到 ` response` 后停止生成

### 外部控制台

勾选后可配合终端使用，通过 stdin 交互输入。

---

## 项目结构

```
├── main.py                      # 主入口
├── start.bat / start.sh         # 启动脚本
├── setup_pip.bat / setup_pip.sh # pip 安装
├── setup_uv.bat / setup_uv.sh   # uv 安装
│
├── src/
│   ├── config.py                # 路径 / QSS 加载 / 多语言引擎 / 默认配置
│   ├── widgets_pyside6.py       # 自定义控件（折叠面板 / 下拉框 / 控制台）
│   ├── download_pyside6.py      # 下载线程 + 显存检测线程
│   ├── backends.py              # 后端注册表（CUDA/Vulkan/SYCL/CPU）
│   ├── launcher_pyside6.py      # 进程启动线程
│   ├── platform.py              # 平台调度（Win/Linux 自动导入）
│   ├── platform_win.py          # Windows 平台函数
│   └── platform_linux.py        # Linux 平台函数
│
├── assets/
│   ├── qss/dark_style.qss       # 深色主题样式表
│   ├── qss/light_style.qss      # 亮色主题样式表
│   └── ui_config.json           # UI 显示元素配置
│
└── locales/
    ├── zh.json                  # 简体中文
    ├── en.json                  # English
    └── ja.json                  # 日本語
```

运行时自动生成（建议 `.gitignore`）：

| 文件 | 说明 |
|------|------|
| `launcher_config.json` | 窗口位置、预设、语言、主题等持久化配置 |
| `assets/release_cache.json` | GitHub Release 缓存（30 分钟有效） |
| `bin/` | 下载的 llama.cpp 二进制 |
| `.venv/` | uv 虚拟环境 |

---

## 自定义

### 修改外观

编辑 `assets/qss/dark_style.qss` 或 `assets/qss/light_style.qss`，支持标准 Qt Style Sheet 语法。重启即生效。

深色主题色调体系：

| 层级 | 色值 | 用途 |
|------|------|------|
| 基底 | `#1e1e2e` | 窗口/标签页背景 |
| 表面 | `#28283c` | 输入框/下拉框/按钮 |
| 悬停 | `#323248` | 鼠标悬停高亮 |
| 边框 | `#3a3a50` | 分割线/输入框边框 |
| 强调 | `#5a9cf0` | 焦点/选中/链接 |

亮色主题对称：`#f2f3f5` → `#ffffff` → `#e8eaf0` → `#d4d6dc` / `#3d88e0`

### 修改文字

| 需求 | 文件 |
|------|------|
| 按钮文字、tooltip、静态标签 | `assets/ui_config.json` |
| 多语言翻译 | `locales/*.json` |
| 动态参数定义（控件类型/范围/默认值） | `assets/ui_config.json` → `参数定义.schema` |

### 添加新语言

在 `locales/` 下放一个与 `zh.json` 同结构的 `.json` 文件，文件名即语言代码。设置页下拉会自动列出。

---

## 后端支持

可下载的后端列表（平台自适应，仅显示 `.zip` 或 `.tar.gz`）：

| 后端 | Windows | Linux |
|------|:-------:|:-----:|
| NVIDIA CUDA 12.4 / 13.1 | ✅ | ✅ |
| AMD HIP / ROCm | ✅ | ✅ |
| Vulkan (通用) | ✅ | ✅ |
| Intel SYCL / OpenVINO | ✅ | ✅ |
| CPU (通用) | ✅ | ✅ |
| ARM64 | ✅ | ✅ |
| macOS | — | ✅ |

---

## 平台注意事项

### Linux

- **aria2c** — 首次下载自动尝试 `sudo apt install aria2` / `sudo pacman -S aria2`
- **脚本导出** — 保存为 `.sh` 并自动 `chmod 755`
- **外部控制台** — 通过 `subprocess.Popen` 在系统终端运行
- **显存检测** — 依赖 `nvidia-smi`

### macOS

- 双击无法启动 → 终端执行 `python3 main.py`
- 下载功能已适配 (`.tar.gz`)
- aria2c 需手动安装：`brew install aria2`

### WSL

- GUI 需 Windows 端 X Server (VcXsrv / GWSL) 或 WSLg
- 下载功能正常工作
- 文件路径注意使用 Linux 格式

---

## 常见问题

**Q: 启动报错"找不到可执行文件"？**  
A: 在设置页设置 Bin 目录，或点击 **📡 获取可用文件** 下载。

**Q: 如何反馈问题？**  
A: 请合理使用issue功能。

**Q: 如何切换语言？**  
A: 设置页 → 🎨 外观 → 语言下拉，即时生效。

**Q: 界面字体太小/太大？**  
A: 设置页 → 📐 缩放 → 拖动滑块（50%-200%），自适应模式随窗口大小自动缩放。

**Q: 下载速度慢？**  
A: 编辑 `src/config.py` 中 `MIRROR_BASE_URLS` 添加镜像，或设置 `PROXY_HOST` / `PROXY_PORT`。推荐使用代理解决或手动下载文件

**Q: 如何保存当前参数供下次使用？**  
A: 参数页点击 **💾 保存**，参数按模型名称独立存储。切换模型时自动恢复。

---

## 许可

MIT License
