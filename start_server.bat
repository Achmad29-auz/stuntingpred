@echo off
title StuntingPred Server v2.0
color 0A
echo.
echo  ╔══════════════════════════════════════════╗
echo  ║  StuntingPred Server v2.0                ║
echo  ║  Heri Bahtiar / UMS 2025                 ║
echo  ╚══════════════════════════════════════════╝
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak ditemukan! Download: https://python.org
    pause & exit
)
echo [1/3] Menginstall dependencies...
pip install flask flask-cors gunicorn --quiet
echo [2/3] Mendeteksi IP...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do set IP=%%a
set IP=%IP:~1%
echo [3/3] Menjalankan server...
echo.
echo  Server: http://127.0.0.1:5000
echo  Network: http://%IP%:5000
echo  (Arahkan semua HP ke URL Network)
echo.
cd /d "%~dp0"
python server.py
pause
