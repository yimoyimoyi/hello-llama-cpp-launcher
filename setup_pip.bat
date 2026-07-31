@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   Llama.cpp Launcher — pip 环境安装
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/2] 从 requirements.txt 安装依赖 ...
pip install -r requirements.txt
if errorlevel 1 (
    echo [警告] 系统 pip 安装失败，尝试 --user ...
    pip install --user -r requirements.txt
)

echo [2/2] 验证安装 ...
python -c "from PySide6.QtWidgets import QApplication; print('PySide6 安装成功')"
if errorlevel 1 (
    echo [错误] PySide6 验证失败，请检查 Python 和 pip 环境
    pause
    exit /b 1
)

echo.
echo ========================================
echo   安装完成！
echo   双击 start.bat 启动 Llama Launcher
echo ========================================
pause
