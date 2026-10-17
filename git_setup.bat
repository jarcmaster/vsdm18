@echo off
REM ============================================================
REM  First time: initialize the repo and push it to GitHub.
REM  (Equivalent to GitHub's quickstart commands.)
REM  Already run once; useful to set up again on another PC.
REM ============================================================
cd /d "%~dp0"

echo # vsdm18>> README.md
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/jarcmaster/vsdm18.git
git push -u origin main

pause
