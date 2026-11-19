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
echo Conferindo detector visual de FOLD (OpenCV)...
"%PYTHONEXE%" %PYTHONARGS% -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 (
  echo Instalando OpenCV (primeira execucao, pode precisar de internet)...
  "%PYTHONEXE%" %PYTHONARGS% -m pip install --user "opencv-python-headless>=4.8,<5"
  if errorlevel 1 (
    echo AVISO: OpenCV indisponivel. O analisador continua com OCR do Tesseract.
    echo Para habilitar a identificacao visual, rode INSTALAR_TUDO_WINDOWS.bat.
  )
)
echo Verificando sintaxe do analisador...
"%PYTHONEXE%" %PYTHONARGS% -m py_compile "%~dp0analise_video.py" "%~dp0hud_recognition.py" "%~dp0pasta_saida.py" "%~dp0analise_local.py" "%~dp0desfecho_local.py" "%~dp0cortador.py"
if errorlevel 1 (
  echo.
  echo ERRO DE SINTAXE: atualize os arquivos desta pasta.
  echo A janela sera mantida aberta para voce copiar o erro.
  pause
  exit /b 1
)
"%PYTHONEXE%" %PYTHONARGS% "%~dp0analise_video.py"
if errorlevel 1 pause
endlocal
