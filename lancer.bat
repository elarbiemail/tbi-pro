@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python n'est pas installe : installez-le depuis python.org en cochant "Add Python to PATH". & pause & exit /b)
if not exist ".venv\Scripts\python.exe" (
  echo Premiere utilisation : installation des bibliotheques...
  python -m venv .venv || (pause & exit /b)
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt || (pause & exit /b)
)
start "" ".venv\Scripts\pythonw.exe" run.py
