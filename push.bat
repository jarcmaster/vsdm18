@echo off
REM ============================================================
REM  Update the repository (daily use).
REM  Stages all changes, commits and pushes to GitHub.
REM  Optional: pass the commit message as an argument.
REM ============================================================
cd /d "%~dp0"

git add .

set "MSG=%*"
if "%MSG%"=="" set /p MSG=Commit message:
if "%MSG%"=="" set "MSG=update"

git commit -m "%MSG%"
git push origin main

echo.
echo Done. Repository: https://github.com/jarcmaster/vsdm18
pause
