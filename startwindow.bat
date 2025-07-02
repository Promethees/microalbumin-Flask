@echo off

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python not found. Installing Python 3.7.9...
    REM Download Python 3.7.9 installer
    curl -o python-installer.exe https://www.python.org/ftp/python/3.7.9/python-3.7.9-amd64.exe
    REM Install Python 3.7.9 silently
    python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
    REM Clean up
    del python-installer.exe
    REM Refresh environment variables
    set "PATH=%PATH%;C:\Program Files\Python37;C:\Program Files\Python37\Scripts"
)

REM Check Python version
for /f "tokens=2 delims= " %%a in ('python --version 2^>nul') do set PY_VER=%%a
if not "%PY_VER%"=="3.7.9" (
    echo ❌ Python 3.7.9 is required. Current version: %PY_VER%
    echo Installing Python 3.7.9...
    REM Download Python 3.7.9 installer
    curl -o python-installer.exe https://www.python.org/ftp/python/3.7.9/python-3.7.9-amd64.exe
    REM Install Python 3.7.9 silently
    python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
    REM Clean up
    del python-installer.exe
    REM Refresh environment variables
    set "PATH=%PATH%;C:\Program Files\Python37;C:\Program Files\Python37\Scripts"
)

REM Create venv if not exists
if not exist "venv" (
    python -m venv venv
)

call venv\Scripts\activate

REM Ensure pip is installed
echo Checking pip...
python -m ensurepip --upgrade

REM Install required libraries
echo Installing requirements...
pip install --upgrade pip
pip install -r requirements.txt

REM Install Flask if not already installed
python -m pip install flask

REM Install pandas if not already installed
python -m pip install pandas

REM Start the app
echo Starting app...
python main.py