@echo off
REM Build the standalone .exe (requires: pip install -r requirements.txt pyinstaller)
REM Optional signing: set WIN_SIGN_PFX_B64 + WIN_SIGN_PASSWORD (+EXPECTED_PUBLISHER),
REM then call with SIGN=1:  build_app.bat SIGN=1
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
if not exist assets\icon.ico python tools\make_icon.py
python tools\check_version.py
if errorlevel 1 exit /b 1
python -m pytest tests -q
if errorlevel 1 exit /b 1
python -m PyInstaller MetadataWriterPro.spec --noconfirm
if errorlevel 1 exit /b 1
if "%~1"=="SIGN=1" (
  python tools\sign.py sign dist\MetadataWriterPro.exe
  if errorlevel 1 exit /b 1
)
echo.
echo Built: dist\MetadataWriterPro.exe
endlocal
