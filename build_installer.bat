@echo off
REM Build the installer (requires Inno Setup 6 + dist\MetadataWriterPro.exe from build_app.bat)
setlocal
cd /d "%~dp0"
if not exist dist\MetadataWriterPro.exe (
  echo ERROR: dist\MetadataWriterPro.exe not found. Run build_app.bat first.
  exit /b 1
)
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
%ISCC% installer\setup.iss
echo.
echo Built: MetadataWriterPro-Setup.exe
endlocal
