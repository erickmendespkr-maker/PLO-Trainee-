@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (echo Execute Preparar_Integrado.bat primeiro. & pause & exit /b 1)
set OMP_THREAD_LIMIT=1
set PYTHONUTF8=1
.venv\Scripts\python.exe video_analyzer\plo5_integrated_desktop.py
if errorlevel 1 pause
