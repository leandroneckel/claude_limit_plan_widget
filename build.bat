@echo off
REM ============================================================
REM build.bat - compila o widget em um executavel unico (.exe)
REM
REM Gera dist\TokenWidget.exe usando o PyInstaller.
REM Pre-requisito: ter rodado a instalacao das dependencias no .venv
REM   python -m venv .venv
REM   .venv\Scripts\activate
REM   pip install -r requirements.txt
REM ============================================================

setlocal

REM Usa o Python do venv se existir, senao o Python do PATH.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo Compilando TokenWidget com PyInstaller...

"%PY%" -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name TokenWidget ^
  --paths src ^
  src\main.py

if errorlevel 1 (
    echo.
    echo Falha na compilacao.
    exit /b 1
)

echo.
echo Build concluido. Veja dist\TokenWidget.exe
endlocal
