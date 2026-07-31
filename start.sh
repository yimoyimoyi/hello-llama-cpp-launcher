#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Llama.cpp Launcher — 启动脚本 (Linux/macOS)
# 自动检测环境优先级：uv .venv > 系统 Python
# ═══════════════════════════════════════════════════════════════
cd "$(dirname "$0")"

if [ -f ".venv/bin/python" ]; then
    echo "[启动] 使用 uv 虚拟环境 ..."
    PYTHON=".venv/bin/python"
else
    if command -v python3 &>/dev/null; then
        PYTHON="$(command -v python3)"
    elif command -v python &>/dev/null; then
        PYTHON="$(command -v python)"
    else
        echo "[错误] 未找到 Python，请先运行 setup_pip.sh 或 setup_uv.sh"
        exit 1
    fi
    echo "[启动] 使用系统 Python: $PYTHON"
fi

exec "$PYTHON" main.py
