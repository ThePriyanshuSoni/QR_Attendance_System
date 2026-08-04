@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer and select "Add Python to PATH".
  pause
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
python seed_demo.py
if errorlevel 1 goto :error
echo.
echo Setup completed. Run run_windows.bat next.
pause
exit /b 0
:error
echo.
echo Setup failed. Read the error above.
pause
exit /b 1
