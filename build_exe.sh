#!/bin/bash
set -e
echo "=== Structo Compare — Build EXE ==="

pip install -r requirements.txt
pip install pyinstaller

pyinstaller structo_compare.spec

echo ""
echo "Done! Find StructoCompare in the dist/ folder."
