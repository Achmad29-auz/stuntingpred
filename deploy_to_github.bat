@echo off
setlocal enabledelayedexpansion
echo.
echo  ====================================================
echo   StuntingPred v2.0 - Push ke GitHub untuk Koyeb
echo  ====================================================
echo.
set /p GH_USER=GitHub Username  : 
set /p GH_TOKEN=GitHub Token     : 
set /p REPO_NAME=Nama repo (contoh: stuntingpred): 
if "%REPO_NAME%"=="" set REPO_NAME=stuntingpred

echo.
echo [1/4] Membuat repo GitHub...
curl -s -X POST "https://api.github.com/user/repos" ^
  -H "Authorization: token %GH_TOKEN%" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"%REPO_NAME%\",\"private\":false}" >nul 2>&1

echo [2/4] Init git...
cd /d "%~dp0"
del /f /q stunting.db stunting.db-shm stunting.db-wal 2>nul
git init
git config user.email "deploy@stuntingpred.app"
git config user.name "StuntingPred"

echo [3/4] Commit...
git add -A
git commit -m "StuntingPred v2.0"

echo [4/4] Push ke GitHub...
git remote remove origin 2>nul
git remote add origin "https://%GH_USER%:%GH_TOKEN%@github.com/%GH_USER%/%REPO_NAME%.git"
git branch -M main
git push -u origin main --force

echo.
echo  ====================================================
echo   BERHASIL! https://github.com/%GH_USER%/%REPO_NAME%
echo.
echo   Lanjut ke Koyeb:
echo   1. Buka https://app.koyeb.com
echo   2. Create App - GitHub - pilih %REPO_NAME%
echo   3. Run: gunicorn server:app --bind 0.0.0.0:$PORT
echo   4. Env: SECRET_KEY=xxxxx PORT=8000
echo   5. Deploy - dapat URL https://xxx.koyeb.app
echo  ====================================================
pause
