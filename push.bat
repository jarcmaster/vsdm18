@echo off
REM ============================================================
REM  Actualizar el repositorio (uso diario).
REM  Agrega todos los cambios, hace commit y los sube a GitHub.
REM ============================================================
cd /d "%~dp0"

git add .

set "MSG=%*"
if "%MSG%"=="" set /p MSG=Mensaje del commit:
if "%MSG%"=="" set "MSG=update"

git commit -m "%MSG%"
git push origin main

echo.
echo Listo. Repositorio: https://github.com/jarcmaster/vsdm18
pause
