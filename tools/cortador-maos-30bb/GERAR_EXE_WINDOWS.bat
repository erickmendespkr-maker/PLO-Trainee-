@echo off
setlocal
cd /d "%~dp0"
echo Criando EXE local do analisador visual (sem DriveHUD)...
py -3 -m pip install --user --upgrade pyinstaller "Pillow>=10,<13"
if errorlevel 1 goto failed
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name Analisador_PLO_Video --hidden-import=PIL._tkinter_finder analise_video.py
if errorlevel 1 goto failed
echo.
echo EXE gerado: dist\Analisador_PLO_Video.exe
echo FFmpeg/FFprobe e Tesseract OCR ainda devem estar instalados
echo no PATH ou ao lado do EXE. Inclua a pasta tessdata do Tesseract.
pause
exit /b 0
:failed
echo Falha ao gerar EXE. Verifique Python, PyInstaller, Pillow e o log.
pause
exit /b 1
