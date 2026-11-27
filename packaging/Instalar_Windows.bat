@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul || (echo Instale Python 3.11+ 64-bit com Tkinter e py launcher. & pause & exit /b 1)
py -3 -m venv .venv || goto fail
.venv\Scripts\python.exe -m pip install -r packaging\requirements.txt || goto fail
where g++ >nul 2>nul || (echo C++ opcional: instale g++ C++17 e execute Build_Nativo.bat. & goto check)
call packaging\Build_Nativo.bat || goto fail
:check
.venv\Scripts\python.exe video_analyzer\plo5_mvp.py check
if errorlevel 1 echo Instale FFmpeg, ffprobe e Tesseract no PATH para o modo video.
echo Preparacao concluida. Execute Abrir_PLO_Trainee.bat.
pause
exit /b 0
:fail
echo Falha na preparacao; confira as mensagens acima.
pause
exit /b 1
