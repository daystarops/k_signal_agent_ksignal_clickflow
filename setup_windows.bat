@echo off
setlocal
cd /d "%~dp0"
echo =============================================
echo Korea Signal Engine - Windows Setup
echo =============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher 'py' not found. Install Python 3.11+ from python.org and check "Add Python to PATH".
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 (
  echo Failed to create virtual environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
if not exist .env copy .env.example .env
notepad .env
echo.
echo Setup complete. Add OPENAI_API_KEY and optional WEBHOOK_URL in .env, then run launcher_windows.bat.
pause
