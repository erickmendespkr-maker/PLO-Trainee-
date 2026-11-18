@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Verificar Cortador PLO
echo.
echo ================================================
echo  VERIFICACAO LOCAL DO CORTADOR PLO
echo ================================================
echo.
echo 1. Valida sintaxe dos arquivos Python.
echo 2. Executa testes do detector e das regras de BB.
echo Nao altera videos e nao exige Tesseract.
echo.
set "PYEXE="
set "PYARGS="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  goto check
)
if exist "%ProgramFiles%\Python312\python.exe" (
  set "PYEXE=%ProgramFiles%\Python312\python.exe"
  goto check
)
py -3 -c "import PIL" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=py"
  set "PYARGS=-3"
  goto check
)
python -c "import PIL" >nul 2>&1
if not errorlevel 1 (
  set "PYEXE=python"
  goto check
)
echo Python e Pillow nao encontrados. Execute INSTALAR_TUDO_WINDOWS.bat.
pause
exit /b 1

:check
"%PYEXE%" %PYARGS% -m py_compile "analise_video.py" "cortador.py" "diagnostico_mesas.py" "analise_local.py" "hud_recognition.py" "pasta_saida.py" "testes_contexto.py" "testes_hud.py" "testes_pasta_saida.py"
if errorlevel 1 (
  echo.
  echo ERRO: a verificacao de sintaxe falhou.
  pause
  exit /b 1
)
echo.
echo Sintaxe OK. Executando testes de reconhecimento:
"%PYEXE%" %PYARGS% "testes_visuais.py"
if errorlevel 1 (
  echo.
  echo Existem testes que falharam. Copie a mensagem acima e envie no chat.
  pause
  exit /b 1
)
echo.
echo Testando a pasta padrao dos MP4:
"%PYEXE%" %PYARGS% "testes_pasta_saida.py"
if errorlevel 1 (
  echo.
  echo ERRO nos testes da pasta de saida.
  pause
  exit /b 1
)
echo.
echo Verificando reconhecimento completo de HUD sem Tesseract real:
"%PYEXE%" %PYARGS% "testes_hud.py"
if errorlevel 1 (
  echo.
  echo ERRO nos testes do HUD. Copie a mensagem exibida.
  pause
  exit /b 1
)
echo.
echo Testando aporte intra-mao e rebuy sem API:
"%PYEXE%" %PYARGS% "testes_contexto.py"
if errorlevel 1 (
  echo.
  echo ERRO nos testes de rebuy e leitura contextual do pote.
  pause
  exit /b 1
)
echo.
echo Verificacoes sinteticas passaram.
echo Todos os testes foram locais e nao fizeram chamadas de rede.
echo Isto nao garante reconhecer corretamente o seu video.
pause
endlocal
