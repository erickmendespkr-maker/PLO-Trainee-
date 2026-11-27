@echo off
setlocal
cd /d "%~dp0.."
where g++ >nul 2>nul || exit /b 1
g++ -O3 -std=c++17 native\plo5_multiway_cfr.cpp -o native\multiway.exe || exit /b 1
g++ -O3 -std=c++17 native\plo5_rank_worker.cpp -o native\rank_worker.exe || exit /b 1
exit /b 0
