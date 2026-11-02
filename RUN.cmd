@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan python install.py terlebih dahulu.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" main.py
pause
