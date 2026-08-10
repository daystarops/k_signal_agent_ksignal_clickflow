@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set /p url=Paste Korean URL to inspect: 
python main.py inspect-url "%url%" --vision true --card true
start "" "%~dp0outputs\inspect"
pause
