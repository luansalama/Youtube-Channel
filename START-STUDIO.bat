@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"

echo Minecraft Narrative Studio diagnostic launcher
echo The normal launcher is START-STUDIO.vbs, which opens without a terminal.
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
  if errorlevel 1 goto :old_python
  py -3 -m mcstudio studio
  set "EXIT_CODE=%errorlevel%"
  goto :finished
)

where python >nul 2>nul
if errorlevel 1 goto :missing_python
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto :old_python
python -m mcstudio studio
set "EXIT_CODE=%errorlevel%"
goto :finished

:missing_python
echo ERROR: Python was not found.
echo Install Python 3.11 or newer, then run this file again.
set "EXIT_CODE=1"
goto :finished

:old_python
echo ERROR: Minecraft Narrative Studio requires Python 3.11 or newer.
set "EXIT_CODE=1"

:finished
if not "%EXIT_CODE%"=="0" (
  echo.
  echo The studio stopped with error code %EXIT_CODE%.
  if exist "exports\studio-server.log" echo Details: exports\studio-server.log
  pause
)
endlocal & exit /b %EXIT_CODE%
