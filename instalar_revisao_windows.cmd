@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:python
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install "Pillow==12.3.0"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import tkinter; import PIL"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" video_analyzer\plo5_release_check.py
if errorlevel 1 goto failed
echo Dependencias iniciais da revisao visual conferidas.
echo A base de equity e a validacao completa continuam separadas.
echo Abra abrir_plo5.cmd. Consulte docs\PLO5_FINAL_F5_DELIVERY.md.
pause
exit /b 0
:failed
echo Instalacao incompleta. Confira os erros acima e o PATH.
echo Nao execute como administrador.
pause
exit /b 1
