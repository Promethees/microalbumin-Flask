@echo off
:: Ensure the script runs from its own directory
cd /d "%~dp0"
@REM echo ===============================================
@REM echo  Welcome to the Easy Sensor Web Interface Setup
@REM echo ===============================================
@REM echo.
@REM echo This script assumes Git and Python are already installed with pyenv.
@REM echo It will set up a virtual environment and install required libraries.
@REM echo If you haven't installed Git and Python yet, please run startwindow-1-git.bat first. 
@REM echo.
@REM echo If you see errors about permissions or installation, please:
@REM echo   1. Close this window.
@REM echo   2. Right-click startwindow.bat and select "Run as administrator".
@REM echo.

@REM REM Note: This script does not exit on every error automatically.
@REM REM Each critical step checks for errors and exits if needed.

@REM REM Check if Python 3.8.10 or 3.9.13 is installed via pyenv
@REM :: Purpose: Check for Python 3.8.10, install if not found, else check/install Python 3.9.13
@REM :: Initialize variables

@REM REM Get the path to the pyenv Python
@REM for /f "delims=" %%i in ('pyenv which python') do set PYENV_PYTHON=%%i
@REM if not defined PYENV_PYTHON (
@REM     echo ERROR: pyenv which python did not return a path. Check pyenv installation and local version.
@REM     pyenv versions
@REM     pyenv which python
@REM     pause
@REM     exit /b 1
@REM )
@REM echo Using Python: %PYENV_PYTHON%

@REM REM Create venv if not exists
@REM if not exist "code\venv" (
@REM     "%PYENV_PYTHON%" -m venv code\venv
@REM     echo Created virtual environment in 'code\venv'.
@REM )

@REM call code\venv\Scripts\activate.bat
@REM echo Virtual environment activated.

@REM REM Ensure pip is installed
@REM echo Checking pip...
@REM python -m ensurepip --upgrade

@REM REM Install required libraries
@REM echo Installing requirements...
@REM pip install --upgrade pip
@REM pip install -r "%~dp0code\requirements-win.txt"

REM Set the library path and start the app
echo Starting app...

:: Ensure python executable is used from the virtual environment
if not exist "%~dp0code\venv\Scripts\python.exe" (
    echo ERROR: Python executable not found in the virtual environment.
    echo Please run script "startwindow-2-pyenv-python.bat" to set up Python and pyenv.
    echo If you have already run it, ensure the virtual environment is created correctly.
    pause
    exit /b 1
)
"%~dp0code\venv\Scripts\python.exe" "%~dp0code\main.py"
pause