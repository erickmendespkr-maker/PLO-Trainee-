@echo off
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (echo Execute Preparar_Integrado.bat primeiro. & pause & exit /b 1)
if "%~1"=="" (echo Uso: Verificar_Candidato.bat NOVA_PASTA_DE_LOGS [--native] & pause & exit /b 1)
set OMP_THREAD_LIMIT=1
set PYTHONUTF8=1
.venv\Scripts\python.exe packaging\Verificar_Candidato.py %*
exit /b %errorlevel%
