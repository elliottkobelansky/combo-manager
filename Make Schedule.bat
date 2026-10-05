@echo off
rem Windows: double-click to open the Combo Scheduler window.
cd /d "%~dp0"
set "VENV=%USERPROFILE%\.combo-scheduler-python"
if exist "%VENV%\Scripts\pythonw.exe" goto run
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 isn't installed. Get it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
  echo then double-click this again.
  pause
  exit /b 1
)
echo First run: setting up Python for the scheduler ^(only once^)...
%PY% -m venv "%VENV%"
if errorlevel 1 (
  echo Couldn't set up Python.
  pause
  exit /b 1
)
:run
start "" "%VENV%\Scripts\pythonw.exe" "%~dp0app\scheduler_app.py"
