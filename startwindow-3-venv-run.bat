@echo off
echo ===============================================
echo  Welcome to the Easy Sensor Web Interface Setup
echo ===============================================
echo.
echo This script assumes Git and Python are already installed with pyenv.
echo It will set up a virtual environment and install required libraries.
echo If you haven't installed Git and Python yet, please run startwindow-1-git.bat first. 
echo.
echo If you see errors about permissions or installation, please:
echo   1. Close this window.
echo   2. Right-click startwindow.bat and select "Run as administrator".
echo.

REM Note: This script does not exit on every error automatically.
REM Each critical step checks for errors and exits if needed.

REM Check if Python 3.8.10 or 3.9.13 is installed via pyenv
:: Purpose: Check for Python 3.8.10, install if not found, else check/install Python 3.9.13
:: Initialize variables

REM Get the path to the pyenv Python
for /f "delims=" %%i in ('pyenv which python') do set PYENV_PYTHON=%%i
if not defined PYENV_PYTHON (
    echo ERROR: pyenv which python did not return a path. Check pyenv installation and local version.
    pyenv versions
    pyenv which python
    pause
    exit /b 1
)
echo Using Python: %PYENV_PYTHON%

REM Create venv if not exists
if not exist "venv" (
    "%PYENV_PYTHON%" -m venv venv
    echo Created virtual environment in 'venv'.
)

call venv\Scripts\activate.bat
echo Virtual environment activated.

REM Ensure pip is installed
echo Checking pip...
python -m ensurepip --upgrade

REM Install required libraries
echo Installing requirements...
pip install --upgrade pip
pip install -r requirements-win.txt


REM Set the library path and start the app
echo Starting app...
set "PATH=%PATH%;%~dp0windows"
python main.py
pause