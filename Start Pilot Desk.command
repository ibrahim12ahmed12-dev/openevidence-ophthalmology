#!/bin/bash
# Double-click to start Pilot Desk (Mac). Keep this window open while you work.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ and double-click again."
  read -r -p "Press Enter to close." _; exit 1
fi
python3 -c "import openpyxl" 2>/dev/null || python3 -m pip install --user --quiet openpyxl
python3 -m oe app
read -r -p "Pilot Desk stopped. Press Enter to close." _
