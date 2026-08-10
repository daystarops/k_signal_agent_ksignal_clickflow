@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py run --limit-per-source 4 --max-cards 8 --cards-per-category 1 --download-images true --max-images-per-item 3 --render-screenshots true --vision true
python main.py push-webhook
if exist "%~dp0outputs\newsletter.html" start "" "%~dp0outputs\newsletter.html"
start "" "%~dp0outputs"
pause
