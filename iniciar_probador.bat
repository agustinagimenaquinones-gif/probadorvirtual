@echo off
title Probador Virtual Inteligente - Boutique Femenina
color 0D
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ==========================================================
echo    INICIANDO VESTIDOR VIRTUAL FEMENINO (BOUTIQUE)
echo ==========================================================

REM 1. Entorno virtual del proyecto (tiene todas las dependencias)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    goto FIN
)

REM 2. Iniciador 'py' de Windows
where py > nul 2> nul
if %ERRORLEVEL% EQU 0 (
    py -3 main.py
    goto FIN
)

REM 3. Python global del sistema
where python > nul 2> nul
if %ERRORLEVEL% EQU 0 (
    python main.py
    goto FIN
)

echo [ERROR] No se encontro Python. Crea el entorno con:
echo     py -3 -m venv .venv
echo     .venv\Scripts\python.exe -m pip install -r requirements.txt

:FIN
echo.
echo Presiona cualquier tecla para cerrar esta ventana...
pause > nul
