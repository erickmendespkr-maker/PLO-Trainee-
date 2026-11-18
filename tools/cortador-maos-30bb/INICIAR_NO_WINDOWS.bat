@echo off
setlocal
cd /d "%~dp0"
echo Abrindo o analisador que utiliza APENAS videos gravados...
call "%~dp0INICIAR_ANALISE_VIDEO.bat"
exit /b %errorlevel%
