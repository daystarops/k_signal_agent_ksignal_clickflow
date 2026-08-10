#!/bin/bash
set -e
cd "$(dirname "$0")"
clear

echo "========================================"
echo "Korea Signal Engine - Inspect One URL"
echo "========================================"

if [ ! -d .venv ]; then
  echo "Virtual environment not found. Run setup.command first."
  read -p "Press Enter to exit..."
  exit 1
fi

source .venv/bin/activate
read -p "Paste Korean page URL: " URL
read -p "Short name for this page [manual_test]: " NAME
NAME=${NAME:-manual_test}

python main.py inspect-url "$URL" --name "$NAME" --vision true --card true

echo ""
echo "Done. Opening inspect outputs..."
open outputs/inspect || true
read -p "Press Enter to close..."
