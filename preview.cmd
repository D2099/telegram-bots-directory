@echo off
setlocal
cd /d "%~dp0"
python scripts/render_readme.py
if errorlevel 1 goto failed
python scripts/build_site.py
if errorlevel 1 goto failed
python scripts/validate.py
if errorlevel 1 goto failed
python scripts/preview.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Preview could not start. See the message above.
pause
exit /b 1
