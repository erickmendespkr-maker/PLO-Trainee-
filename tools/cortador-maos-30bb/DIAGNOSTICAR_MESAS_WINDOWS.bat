@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Diagnostico Automatico de Mesas PLO
echo.
echo ===================================================
echo   DIAGNOSTICO DE MESAS - VIDEO COMPLETO
echo ===================================================
echo.
echo Examina aproximadamente 1 frame a cada 5 segundos.
echo Nao usa Tesseract. Nao exporta maos e nao altera o video.
echo Gera um CSV de quadros e outro dos horarios de mudanca.
echo.
set "PYEXE="
set "PYARGS="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  goto pronto
)
if exist "%ProgramFiles%\Python312\python.exe" (
  set "PYEXE=%ProgramFiles%\Python312\python.exe"
  goto pronto
)
py -3 -c "import tkinter, PIL" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py"
  set "PYARGS=-3"
  goto pronto
)
python -c "import tkinter, PIL" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  goto pronto
)
echo.
echo Python com Pillow nao encontrado.
echo Execute INSTALAR_TUDO_WINDOWS.bat primeiro.
pause
exit /b 1

:pronto
if "%~1"=="" (
    "%PYEXE%" %PYARGS% "%~dp0diagnostico_mesas.py"
) else (
    "%PYEXE%" %PYARGS% "%~dp0diagnostico_mesas.py" "%~1"
)
if errorlevel 1 (
  echo.
  echo Falha no diagnostico: veja o erro acima.
)
echo.
pause
endlocal
