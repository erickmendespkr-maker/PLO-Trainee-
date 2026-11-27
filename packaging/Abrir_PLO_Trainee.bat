@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (echo Execute Instalar_Windows.bat primeiro. & pause & exit /b 1)
.venv\Scripts\python.exe video_analyzer\plo5_mvp_gui.py
if errorlevel 1 pause
