@echo off
REM Build the standalone .exe (requires: pip install -r requirements.txt pyinstaller)
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
if not exist assets\icon.ico python tools\make_icon.py
python -m PyInstaller MetadataWriterPro.spec --noconfirm
echo.
echo Built: dist\MetadataWriterPro.exe
endlocal
