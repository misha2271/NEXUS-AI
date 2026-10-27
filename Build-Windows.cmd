@echo off
setlocal
cd /d "%~dp0"
echo NEXUS AI v1.0 - Windows builder (without Git or GitHub)
echo Python will be installed via Windows Package Manager if missing.
echo Dependencies are downloaded from PyPI.
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_no_github.ps1"
set "STATUS=%ERRORLEVEL%"
echo.
if "%STATUS%"=="0" (
  echo SUCCESS: See dist\NEXUS-AI.exe and dist\NEXUS-AI-Portable.zip
) else (
  echo BUILD FAILED: Read the error above.
)
pause
exit /b %STATUS%
