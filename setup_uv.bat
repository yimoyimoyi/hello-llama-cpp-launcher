@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   Llama.cpp Launcher — uv 环境安装
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
    echo [1/4] 安装 uv 包管理器 ...
    pip install uv
    if errorlevel 1 (
        echo [备选] 通过 PowerShell 安装 uv ...
        powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
    )
)

echo [2/4] 创建虚拟环境 ...
if not exist .venv uv venv .venv

echo [3/4] 从 requirements.txt 安装依赖 ...
call .venv\Scripts\activate.bat && uv pip install -r requirements.txt
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo [4/4] 验证安装 ...
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('PySide6 安装成功')"
if errorlevel 1 (
    echo [错误] PySide6 验证失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成！
echo   双击 start.bat 启动 Llama Launcher
echo ========================================
pause
