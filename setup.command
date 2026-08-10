#!/bin/bash
set -e
cd "$(dirname "$0")"
clear

echo "========================================"
echo "Korea Signal Engine - Local Setup"
echo "========================================"
echo "This will create a Python virtual environment, install dependencies,"
echo "install Playwright Chromium, and create your .env file if needed."
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed or not on PATH."
  echo "Install Python 3 first: https://www.python.org/downloads/"
  read -p "Press Enter to exit..."
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo ""
echo "Setup complete."
echo ""
echo "Next: add your OPENAI_API_KEY to .env."
echo "Opening .env in TextEdit now..."
open -a TextEdit .env || true

echo ""
echo "After saving your key, double-click run.command or inspect.command."
read -p "Press Enter to close..."
