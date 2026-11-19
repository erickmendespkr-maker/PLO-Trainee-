@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PLO Cortes - Iniciar analisador
echo =================================================
echo  PLO CORTES - ANALISE OFFLINE DE MAOS
echo =================================================
echo.
set "RUN=%~dp0tools\cortador-maos-30bb\INICIAR_ANALISE_VIDEO.bat"
if not exist "%RUN%" (
  echo ERRO: arquivo INICIAR_ANALISE_VIDEO.bat nao encontrado.
  echo Reextraia o ZIP completo, sem executar dentro do compactador.
  goto fim
)
if not exist "%~dp0tools\cortador-maos-30bb\analise_video.py" (
  echo ERRO: analisador Python nao encontrado.
  echo Este ZIP esta incompleto ou nao foi extraido corretamente.
  goto fim
)
call "%RUN%"
set "RESULTADO=%ERRORLEVEL%"
if not "%RESULTADO%"=="0" (
  echo.
  echo O analisador encerrou com codigo de erro: %RESULTADO%
)
:fim
echo.
echo A janela permanecera aberta para permitir leitura de erros.
pause
endlocal
