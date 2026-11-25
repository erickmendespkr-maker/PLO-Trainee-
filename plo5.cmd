@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Execute instalar_windows.cmd primeiro.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0video_analyzer\plo5_windows_candidate.py" %*
exit /b %errorlevel%
