@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo 第一次运行：正在创建虚拟环境并安装依赖……
  python -m venv .venv || (echo 没找到 Python，请先安装 Python 3.10 及以上版本，安装时勾选 "Add Python to PATH" & pause & exit /b 1)
  .venv\Scripts\python -m pip install -r requirements.txt || (echo 依赖安装失败，请把上面的报错发给开发者 & pause & exit /b 1)
)
if not exist .env copy .env.example .env >nul
.venv\Scripts\python run.py
pause
