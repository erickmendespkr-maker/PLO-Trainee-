@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:usepython
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install "Pillow==12.3.0"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" video_analyzer\plo5_windows_candidate.py check data\plo5_equity.sqlite
if errorlevel 1 goto failed
echo Instalacao de dependencias conferida. Leia LEIA-ME_PLO5.md antes de usar.
pause
exit /b 0
:failed
echo Instalacao incompleta. Confira Python, Pillow, FFmpeg, FFprobe e Tesseract.
echo Nao execute como administrador. Consulte LEIA-ME_PLO5.md.
pause
exit /b 1
