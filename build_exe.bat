@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Construction de TBI Pro.exe ===
where python >nul 2>nul || (echo Installez Python 3.11 ou 3.12 depuis python.org. & pause & exit /b)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller || (pause & exit /b)
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name "TBI Pro" ^
  --icon tbipro\icon.ico ^
  --add-data "tbipro\phone;tbipro\phone" ^
  --add-data "tbipro\icon.ico;tbipro" ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtQuick ^
  --exclude-module tkinter --exclude-module matplotlib ^
  run.py || (pause & exit /b)
echo.
echo Termine : le logiciel est dans dist\TBI Pro\TBI Pro.exe
echo Copiez tout le dossier "dist\TBI Pro" sur les autres PC (ou compressez-le en .zip).
pause
