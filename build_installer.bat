@echo off
REM Build the installer (requires Inno Setup 6 + dist\MetadataWriterPro.exe from build_app.bat)
REM Optional signing: build_installer.bat SIGN=1  (needs WIN_SIGN_PFX_B64 + WIN_SIGN_PASSWORD)
setlocal
cd /d "%~dp0"
if not exist dist\MetadataWriterPro.exe (
  echo ERROR: dist\MetadataWriterPro.exe not found. Run build_app.bat first.
  exit /b 1
)
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo ERROR: ISCC.exe not found. Install Inno Setup 6: winget install JRSoftware.InnoSetup
  exit /b 1
)
"%ISCC%" installer\setup.iss
if errorlevel 1 exit /b 1
if "%~1"=="SIGN=1" (
  python tools\sign.py sign MetadataWriterPro-Setup.exe
  if errorlevel 1 exit /b 1
)
for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash MetadataWriterPro-Setup.exe -Algorithm SHA256).Hash.ToLower()"') do set HASH=%%H
echo %HASH%  MetadataWriterPro-Setup.exe> SHA256SUMS.txt
type SHA256SUMS.txt
echo.
echo Built: MetadataWriterPro-Setup.exe
endlocal
