#!/bin/sh
set -e
cd "$(dirname "$0")"
PYTHON="/opt/homebrew/opt/python@3.13/bin/python3.13"
if [ ! -x "$PYTHON" ]; then
  echo "请先安装 Homebrew Python 3.13 和 Tk：brew install python@3.13 python-tk@3.13"
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python main.py
