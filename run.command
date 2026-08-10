#!/bin/bash
set -e
cd "$(dirname "$0")"
clear

echo "========================================"
echo "Korea Signal Engine - Run Pipeline"
echo "========================================"

if [ ! -d .venv ]; then
  echo "Virtual environment not found. Run setup.command first."
  read -p "Press Enter to exit..."
  exit 1
fi

source .venv/bin/activate

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Add OPENAI_API_KEY first."
  open -a TextEdit .env || true
  read -p "Press Enter to exit..."
  exit 1
fi

python main.py run --limit-per-source 3 --max-cards 5 --download-images true --render-screenshots true --vision true

echo ""
echo "Done. Opening outputs folder and newsletter draft..."
open outputs || true
open outputs/brief.md || true
read -p "Press Enter to close..."
