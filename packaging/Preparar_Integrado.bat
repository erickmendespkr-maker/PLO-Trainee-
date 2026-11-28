@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul || goto fail
if not exist .venv\Scripts\python.exe py -3 -m venv .venv || goto fail
.venv\Scripts\python.exe -m pip install -r packaging\requirements-integrado.txt || goto fail
.venv\Scripts\python.exe video_analyzer\plo5_integrated_desktop.py --check || goto fail
echo Ambiente preparado para o candidato integrado. Beta ainda nao validado.
pause
exit /b 0
:fail
echo Verifique Python 3.11+ 64-bit com Tkinter, FFmpeg, ffprobe e Tesseract eng no PATH.
pause
exit /b 1
