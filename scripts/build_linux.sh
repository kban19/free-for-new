#!/usr/bin/env bash
set -euo pipefail
echo "=== Building Kurmanji-TTS for Linux ==="
source .venv/bin/activate
pip install pyinstaller
flet pack main.py --name "Kurmanji-TTS" --add-data "THIRD-PARTY-LICENSES.md:."
echo "Build finished! Copy models/ and piper/ alongside dist/Kurmanji-TTS or run setup_runtime.py."
