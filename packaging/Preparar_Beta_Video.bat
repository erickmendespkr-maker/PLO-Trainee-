@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul || (echo Instale Python 3.11+ 64-bit com Tkinter e py launcher. & goto fail)
if not exist .venv\Scripts\python.exe py -3 -m venv .venv || goto fail
.venv\Scripts\python.exe -m pip install -r packaging\requirements.txt || goto fail
.venv\Scripts\python.exe video_analyzer\plo5_beta_desktop.py --check || goto fail
 echo Ambiente preparado para reconhecimento experimental. Nao e beta validado.
 echo Execute Abrir_Beta_Video.bat.
pause
exit /b 0
:fail
echo Falha no preparo. Verifique Python 3.11+, Tkinter, FFmpeg, ffprobe e Tesseract com idioma eng no PATH.
pause
exit /b 1
