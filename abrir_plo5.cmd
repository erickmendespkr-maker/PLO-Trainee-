@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute instalar_revisao_windows.cmd primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" video_analyzer\plo5_launcher.py %*
set "RC=%errorlevel%"
if not "%RC%"=="0" pause
exit /b %RC%
