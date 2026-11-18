@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PLO - Analisador Visual (somente videos)
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%ProgramFiles%\WinGet\Links;%PATH%"

where ffmpeg >nul 2>&1
if errorlevel 1 if not exist "%~dp0ffmpeg.exe" (
  echo.
  echo FFmpeg nao encontrado. Instale FFmpeg e adicione ao PATH,
  echo ou copie ffmpeg.exe e ffprobe.exe para esta pasta.
  echo https://ffmpeg.org/download.html
  pause
  exit /b 1
)
where ffprobe >nul 2>&1
if errorlevel 1 if not exist "%~dp0ffprobe.exe" (
  echo FFprobe nao encontrado. Instale-o junto com FFmpeg.
  pause
  exit /b 1
)

if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles%\Tesseract-OCR;%PATH%"
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "PATH=%LOCALAPPDATA%\Programs\Tesseract-OCR;%PATH%"
where tesseract >nul 2>&1
if errorlevel 1 if not exist "%~dp0tesseract.exe" (
  echo.
  echo Tesseract OCR nao encontrado.
  echo Instale Tesseract para Windows, confira o idioma ingles
  echo e adicione tesseract.exe ao PATH.
  echo Consulte as instrucoes no README.md.
  pause
  exit /b 1
)

set "PYTHONEXE="
set "PYTHONARGS="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PYTHONEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  goto ready
)
py -3 -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
  set "PYTHONEXE=py"
  set "PYTHONARGS=-3"
  goto ready
)
python -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
  set "PYTHONEXE=python"
  goto ready
)

echo Python com Tkinter nao encontrado. Instale Python 3.12 do site oficial:
echo https://www.python.org/downloads/windows/
pause
exit /b 1

:ready
"%PYTHONEXE%" %PYTHONARGS% -c "import PIL, PIL.ImageTk" >nul 2>&1
if errorlevel 1 (
  echo Instalando dependencia Pillow na sua conta...
  "%PYTHONEXE%" %PYTHONARGS% -m pip install --user "Pillow>=10,<13"
  if errorlevel 1 (
    echo Falha instalando Pillow. Confira sua conexao.
    pause
    exit /b 1
  )
)
"%PYTHONEXE%" %PYTHONARGS% "%~dp0analise_video.py"
if errorlevel 1 pause
endlocal
