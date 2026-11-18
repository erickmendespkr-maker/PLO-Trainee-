@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Cortador de Maos PLO

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto run_local
)

py -3 -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    set "PYCOMMAND=py -3"
    goto run_command
)
python -c "import tkinter" >nul 2>&1
if not errorlevel 1 (
    set "PYCOMMAND=python"
    goto run_command
)

echo.
echo Python com interface grafica nao foi encontrado.
echo Esta rotina pode baixar o instalador oficial Python 3.12.9 (64 bits) do site python.org.
echo Sera instalado apenas na sua conta do Windows.
echo.
choice /C SN /M "Deseja instalar Python agora?"
if errorlevel 2 goto no_python

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $p=Join-Path $env:TEMP 'python-3.12.9-amd64.exe'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile $p; $x=Start-Process -FilePath $p -ArgumentList '/quiet InstallAllUsers=0 PrependPath=0 Include_tcltk=1 Include_test=0' -Wait -PassThru; if($x.ExitCode -ne 0) { throw ('Instalador retornou ' + $x.ExitCode) }"
if errorlevel 1 goto install_failed
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto run_local
)
goto install_failed

:run_local
"%PYEXE%" "%~dp0cortador.py"
if errorlevel 1 pause
goto end

:run_command
%PYCOMMAND% "%~dp0cortador.py"
if errorlevel 1 pause
goto end

:no_python
echo Abra https://www.python.org/downloads/windows/ e instale Python com Tcl/Tk.
pause
goto end

:install_failed
echo.
echo A instalacao automatica falhou.
echo Instale Python 3.12 no site oficial: https://www.python.org/downloads/windows/
echo Em seguida execute este mesmo arquivo BAT.
pause

:end
endlocal
