@echo off
chcp 65001 >nul 2>&1
title LOL 海克斯大乱斗符文推荐

echo ============================================
echo   LOL 海克斯大乱斗符文推荐助手
echo   一键启动脚本
echo ============================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10-3.12
    echo 下载地址: https://www.python.org/downloads/release/python-3129/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM 检查是否是正确的 Python 版本 (需要 <3.13)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo 检测到 Python 版本: %PYVER%

REM 检查依赖是否已安装
echo.
echo 正在检查依赖...
python -c "import tkinter; import requests; import psutil; from thefuzz import process; from pypinyin import lazy_pinyin" 2>nul
if errorlevel 1 (
    echo 依赖未完整安装，正在自动安装...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请手动运行:
        echo   pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo.
    echo 依赖安装完成!
) else (
    echo 依赖已就绪
)

echo.
echo ============================================
echo  正在启动程序...
echo  使用说明:
echo  1. 选择英雄 -> 点击推荐
echo  2. 或点击"自动识别"连接游戏客户端
echo  3. 游戏选人后自动推荐海克斯
echo ============================================
echo.

REM 启动程序
python app.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出，请检查错误信息
    pause
)
