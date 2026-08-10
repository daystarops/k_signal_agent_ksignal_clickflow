@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Virtual environment missing. Run setup_windows.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
:menu
cls
echo =============================================
echo K Signal - Windows Click Launcher
echo =============================================
echo 1. Generate K Signal issue - 4 lanes, screenshots, vision, guardrail
echo 2. Inspect one Korean URL - screenshot + vision + card
echo 3. Push latest issue to n8n webhook
echo 4. Generate K Signal issue, then push to n8n
echo 5. Open latest HTML newsletter
echo 6. Open outputs folder
echo 7. Edit .env keys
echo 8. Edit source config
echo 9. Enrich Issue 001 with images/video
echo 10. Rebuild Issue 001
echo 11. Open Issue 001 newsletter
echo 12. Open social card folder
echo 13. Check Issue 001 links
echo 14. Repair Issue 001 backup links
echo 15. Open Issue 001 publish audit
echo 16. Create Netlify host package
echo 17. Create Issue 001 distribution pack
echo 18. Create Issue 001 Instagram content pack
echo 19. Scout Issue 001 creatives
echo 20. Render Issue 001 reels
echo 0. Exit
echo.
echo Default issue lanes: Government, Idols, Sports, Local Phenomenon
echo.
set /p choice=Choose an option: 
if "%choice%"=="1" goto run
if "%choice%"=="2" goto inspect
if "%choice%"=="3" goto push
if "%choice%"=="4" goto runpush
if "%choice%"=="5" goto openhtml
if "%choice%"=="6" goto openoutputs
if "%choice%"=="7" goto editenv
if "%choice%"=="8" goto editconfig
if "%choice%"=="9" goto enrichissue001
if "%choice%"=="10" goto rebuildissue001
if "%choice%"=="11" goto openissue001
if "%choice%"=="12" goto opensocial001
if "%choice%"=="13" goto checklinks001
if "%choice%"=="14" goto repairlinks001
if "%choice%"=="15" goto openaudit001
if "%choice%"=="16" goto createhost001
if "%choice%"=="17" goto createdistribution001
if "%choice%"=="18" goto createinstagram001
if "%choice%"=="19" goto scoutcreatives001
if "%choice%"=="20" goto renderreels001
if "%choice%"=="0" exit /b 0
goto menu

:run
python main.py run --limit-per-source 4 --max-cards 8 --cards-per-category 1 --download-images true --max-images-per-item 3 --render-screenshots true --vision true
if exist "%~dp0outputs\newsletter.html" start "" "%~dp0outputs\newsletter.html"
start "" "%~dp0outputs"
pause
goto menu

:inspect
set /p url=Paste Korean URL to inspect: 
python main.py inspect-url "%url%" --vision true --card true
start "" "%~dp0outputs\inspect"
pause
goto menu

:push
python main.py push-webhook
pause
goto menu

:runpush
python main.py run --limit-per-source 4 --max-cards 8 --cards-per-category 1 --download-images true --max-images-per-item 3 --render-screenshots true --vision true
python main.py push-webhook
if exist "%~dp0outputs\newsletter.html" start "" "%~dp0outputs\newsletter.html"
start "" "%~dp0outputs"
pause
goto menu

:openhtml
if exist "%~dp0outputs\newsletter.html" start "" "%~dp0outputs\newsletter.html" else echo No newsletter.html yet. Run option 1 first.
pause
goto menu

:openoutputs
if not exist outputs mkdir outputs
start "" "%~dp0outputs"
goto menu

:editenv
if not exist .env copy .env.example .env
notepad .env
goto menu

:editconfig
notepad configs\sources.yaml
goto menu

:enrichissue001
python main.py enrich-media --issue 001
if exist "%~dp0outputs\issues\001\media\media_manifest.json" echo Media enrichment complete.
pause
goto menu

:rebuildissue001
python main.py rebuild-issue --issue 001
pause
goto menu

:openissue001
if exist "%~dp0outputs\issues\001\newsletter.html" start "" "%~dp0outputs\issues\001\newsletter.html" else echo No Issue 001 newsletter yet. Run option 10 first.
pause
goto menu
:opensocial001
if exist "%~dp0outputs\issues\001\social" start "" "%~dp0outputs\issues\001\social" else echo No social cards yet. Run export-social first.
pause
goto menu
:checklinks001
python main.py check-links --issue 001
pause
goto menu

:repairlinks001
python main.py repair-links --issue 001
pause
goto menu

:openaudit001
if exist "%~dp0outputs\issues\001\link_audit.html" start "" "%~dp0outputs\issues\001\link_audit.html" else echo No publish audit yet. Run option 13 first.
pause
goto menu
:createhost001
python main.py create-host-package --issue 001
if exist "%~dp0outputs\issues\001\host_package.zip" echo Netlify host package ready.
pause
goto menu
:createdistribution001
python main.py create-distribution-pack --issue 001
if exist "%~dp0outputs\issues\001\distribution_pack" echo Issue 001 distribution pack ready.
pause
goto menu
:createinstagram001
python main.py create-instagram-pack --issue 001
if exist "%~dp0outputs\issues\001\distribution_pack\instagram" echo Issue 001 Instagram content pack ready.
pause
goto menu

:scoutcreatives001
python main.py scout-creatives --issue 001
pause
goto menu
:renderreels001
python main.py render-reels --issue 001
pause
goto menu
