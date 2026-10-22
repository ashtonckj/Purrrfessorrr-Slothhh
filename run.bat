@echo off
rem Purrfessorrr Slothhh - Windows launcher.
rem Creates .venv on first run, installs requirements, starts the app (opens your browser).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || (pause & exit /b 1)
)

echo Installing requirements (first run takes a minute)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (pause & exit /b 1)

".venv\Scripts\python.exe" app.py %*
pause
