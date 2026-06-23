@echo off
echo === Structo Compare — Build EXE ===

REM Install dependencies
pip install -r requirements.txt
pip install pyinstaller

REM Build single-file exe
pyinstaller structo_compare.spec

echo.
echo Done! Find StructoCompare.exe in the dist\ folder.
pause
