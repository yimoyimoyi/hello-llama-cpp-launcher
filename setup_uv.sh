#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Llama.cpp Launcher — uv 环境安装 (Linux/macOS)
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

echo "========================================"
echo "  Llama.cpp Launcher — uv 环境安装"
echo "========================================"
echo ""

# 检测 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.8+"
    echo "       Ubuntu/Debian: sudo apt install python3"
    echo "       Arch:          sudo pacman -S python"
    echo "       Fedora:        sudo dnf install python3"
    exit 1
fi

PYTHON="$(command -v python3)"
echo "[检测] Python: $PYTHON ($($PYTHON --version))"

# 安装 uv
if ! command -v uv &>/dev/null; then
    echo "[1/4] 安装 uv 包管理器 ..."
    if command -v pip3 &>/dev/null; then
        pip3 install uv
    else
        $PYTHON -m pip install uv
    fi
    # 若 pip 安装后仍不可用，通过官方脚本安装
    if ! command -v uv &>/dev/null; then
        echo "[备选] 通过官方脚本安装 uv ..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # 重新加载 PATH
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

echo "[2/4] 创建虚拟环境 ..."
if [ ! -d ".venv" ]; then
    uv venv .venv
fi

echo "[3/4] 从 requirements.txt 安装依赖 ..."
. .venv/bin/activate 2>/dev/null || true
uv pip install -r requirements.txt

echo "[4/4] 验证安装 ..."
.venv/bin/python -c "from PySide6.QtWidgets import QApplication; print('PySide6 安装成功')"

echo ""
echo "========================================"
echo "  安装完成！"
echo "  运行: bash start.sh  或  .venv/bin/python main.py"
echo "========================================"
