@echo off
cd /d "%~dp0\.."
where py >nul 2>nul
if not errorlevel 1 (
  py -3 iniciar_clipes.py --check
  if errorlevel 1 goto fail
  py -3 iniciar_clipes.py
) else (
  python iniciar_clipes.py --check
  if errorlevel 1 goto fail
  python iniciar_clipes.py
)
if errorlevel 1 goto fail
exit /b 0
:fail
echo Verifique Python, FFmpeg e FFprobe e os arquivos do pacote.
pause
exit /b 1
