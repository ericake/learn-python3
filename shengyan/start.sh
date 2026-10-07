#!/usr/bin/env bash
# Mac / Linux 一键启动：bash start.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "第一次运行：正在创建虚拟环境并安装依赖……"
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python setup_env.py
exec .venv/bin/python run.py
