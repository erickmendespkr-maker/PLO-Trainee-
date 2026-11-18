@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Instalador - Analisador PLO por Video
echo.
echo ============================================================
echo    ANALISADOR PLO - INSTALACAO GUIADA PARA WINDOWS 10 / 11
echo ============================================================
echo.
echo Instala tres componentes gratuitos:
echo   1. Python 3.12 (Python Software Foundation)
echo   2. FFmpeg (Gyan)
echo   3. Tesseract OCR (UB Mannheim)
echo Tambem instala a biblioteca Pillow para mostrar imagens.
echo.
echo O processo usa o gerenciador WinGet da Microsoft.
echo Os downloads sao feitos pelos pacotes de seus fornecedores.
echo Podera ser solicitada permissao do Windows (UAC).
echo Sua gravacao NAO sera enviada para a internet.
echo.
choice /C SN /M "Autoriza instalar os componentes listados?"
if errorlevel 2 goto cancelado

where winget >nul 2>&1
if errorlevel 1 goto sem_winget

echo.
echo [1/4] Instalando Python 3.12...
winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 echo AVISO: Python pode nao ter sido instalado. Consulte o texto final.

echo.
echo [2/4] Instalando FFmpeg + FFprobe...
winget install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 echo AVISO: FFmpeg pode nao ter sido instalado. Consulte o texto final.

echo.
echo [3/4] Instalando Tesseract OCR...
winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 echo AVISO: Tesseract pode nao ter sido instalado. Consulte o texto final.

echo.
echo [4/4] Verificando Python e instalando Pillow...
set "PYEXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=\"%LOCALAPPDATA%\Programs\Python\Python312\python.exe\""
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=\"%ProgramFiles%\Python312\python.exe\""
if not defined PYEXE (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYEXE=py -3.12"
)
if not defined PYEXE (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE goto sem_python
%PYEXE% -m pip install --user "Pillow>=10,<13"
if errorlevel 1 goto sem_pillow

echo.
echo ============================================================
echo INSTALACAO TENTADA - confirme os componentes:
echo ============================================================
%PYEXE% -c "import tkinter, PIL; print('OK: Python, Tkinter e Pillow')"
if errorlevel 1 echo AVISO: Python/Tkinter/Pillow nao foram validados.
echo.
echo Python instalado. A existencia de FFmpeg e Tesseract
echo deve ser verificada ao abrir o programa. Se nao forem
echo reconhecidos, reinicie o computador e tente novamente.
echo.
echo Agora execute INICIAR_ANALISE_VIDEO.bat na mesma pasta.
pause
exit /b 0

:sem_winget
echo.
echo ERRO: WinGet nao esta instalado/ativo neste Windows.
echo No Windows Ghost Spectre alguns componentes Microsoft
echo podem ter sido removidos.
echo Instale o App Installer da Microsoft ou use os links:
echo Python: https://www.python.org/downloads/windows/
echo FFmpeg: https://ffmpeg.org/download.html
echo Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
echo Consulte o README do programa para instalacao manual.
pause
exit /b 1

:sem_python
echo.
echo Python nao foi encontrado depois da tentativa de instalacao.
echo Feche esta janela e abra novamente o INSTALAR_TUDO_WINDOWS.bat,
echo ou instale Python 3.12 manualmente.
pause
exit /b 1

:sem_pillow
echo.
echo Falha ao instalar Pillow. Verifique internet e permissao
echo de instalacao e execute novamente este arquivo.
pause
exit /b 1

:cancelado
echo Instalacao cancelada. Nenhum novo comando de instalacao foi executado.
pause
exit /b 0
