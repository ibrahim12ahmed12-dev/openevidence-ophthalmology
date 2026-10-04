@echo off
REM Double-click to start Pilot Desk (Windows). Keep this window open while you work.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys" >nul 2>nul || (echo Python 3 is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and double-click again. & pause & exit /b 1)
%PY% -c "import openpyxl" >nul 2>nul || %PY% -m pip install --user --quiet openpyxl
%PY% -m oe app
pause
