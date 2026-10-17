@echo off
REM ============================================================
REM  Primera vez: inicializa el repo y lo sube a GitHub.
REM  (Equivalente a los comandos del quickstart de GitHub.)
REM  Ya ejecutado una vez; util para reconfigurar en otra PC.
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
