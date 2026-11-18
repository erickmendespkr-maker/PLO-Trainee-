@echo off
setlocal
cd /d "%~dp0"
echo Requer Python instalado. Construindo EXE localmente...
py -3 -m pip install --user --upgrade pyinstaller
if errorlevel 1 goto failed
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name Cortador_Maos_PLO cortador.py
if errorlevel 1 goto failed
echo.
echo Executavel criado: dist\Cortador_Maos_PLO.exe
echo Necessario manter FFmpeg e FFprobe no PATH ou na mesma pasta do EXE.
pause
exit /b 0
:failed
echo Falha na compilacao. Verifique instalacao do Python/py e o log acima.
pause
exit /b 1
