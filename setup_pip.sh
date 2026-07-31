#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Llama.cpp Launcher — pip 环境安装 (Linux/macOS)
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

echo "========================================"
echo "  Llama.cpp Launcher — pip 环境安装"
echo "========================================"
echo ""

# 检测 Python
if ! command -v python3 &>/dev/null; then
    echo "[错误] 未找到 python3，请先安装 Python 3.8+"
    echo "       Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "       Arch:          sudo pacman -S python python-pip"
    echo "       Fedora:        sudo dnf install python3 python3-pip"
    exit 1
fi

PYTHON="$(command -v python3)"
echo "[检测] Python: $PYTHON ($($PYTHON --version))"

# 检测 pip
if ! command -v pip3 &>/dev/null && ! $PYTHON -m pip --version &>/dev/null 2>&1; then
    echo "[错误] 未找到 pip，请安装 python3-pip"
    exit 1
fi

PIP="$PYTHON -m pip"

echo "[1/2] 从 requirements.txt 安装依赖 ..."
$PIP install -r requirements.txt

echo "[2/2] 验证安装 ..."
$PYTHON -c "from PySide6.QtWidgets import QApplication; print('PySide6 安装成功')"

echo ""
echo "========================================"
echo "  安装完成！"
echo "  运行: bash start.sh  或  python3 main.py"
echo "========================================"
