@echo off
echo ===============================================
echo  Welcome to the Easy Sensor Web Interface Setup
echo ===============================================
echo.
echo This script will automatically set up and start the program.
echo.
echo If you see errors about permissions or installation, please:
echo   1. Close this window.
echo   2. Right-click startwindow.bat and select "Run as administrator".
echo.

REM Note: This script does not exit on every error automatically.
REM Each critical step checks for errors and exits if needed.

REM Check if git is installed
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Git is not installed. Downloading and installing Git for Windows...
    powershell -Command "Invoke-WebRequest -Uri https://github.com/git-for-windows/git/releases/latest/download/Git-2.45.2-64-bit.exe -OutFile git-installer.exe"
    if exist git-installer.exe (
        start /wait git-installer.exe /VERYSILENT /NORESTART
        del git-installer.exe
        echo Git installation complete. Please close this window and re-run startwindow.bat.
    ) else (
        echo Failed to download Git installer. Please check your internet connection or download Git manually from https://git-scm.com/download/win
    )
    pause
    exit /b 1
)

REM Change to the script's directory (must be before any pyenv or Python commands)
cd /d "%~dp0%"
echo Current directory: %CD%

REM Check if pyenv-win is installed, if not, install it
if not exist "%USERPROFILE%\.pyenv\pyenv-win" (
    echo ❌ pyenv not found. Installing pyenv-win...
    powershell -Command "git clone https://github.com/pyenv-win/pyenv-win.git $env:USERPROFILE\.pyenv\pyenv-win"
)
REM Always set environment variables and PATH for pyenv-win
set "PYENV=%USERPROFILE%\.pyenv\pyenv-win"
set "PYENV_ROOT=%USERPROFILE%\.pyenv"
set "PYENV_HOME=%USERPROFILE%\.pyenv\pyenv-win"
set "PATH=%USERPROFILE%\.pyenv\pyenv-win\bin;%USERPROFILE%\.pyenv\pyenv-win\shims;%PATH%"
REM Check if pyenv is now available
where pyenv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ pyenv is still not recognized. Please restart your computer or log out and log in again, then re-run this script.
    pause
    exit /b 1
)

REM Check if Python 3.8.10 or 3.9.13 is installed via pyenv
set "PYTHON_VERSION=3.8.10"
pyenv versions | findstr 3.8.10 >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python 3.8.10 not found. Checking for Python 3.9.13...
    pyenv versions | findstr 3.9.13 >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo ❌ Python 3.9.13 not found. Installing Python 3.8.10 via pyenv...
        pyenv install 3.8.10
        if %ERRORLEVEL% neq 0 (
            echo Failed to install Python 3.8.10. Trying Python 3.9.13...
            pyenv install 3.9.13
            if %ERRORLEVEL% neq 0 (
                echo ERROR: Failed to install Python 3.9.13. Please check pyenv and try again.
                pause
                exit /b 1
            )
            set "PYTHON_VERSION=3.9.13"
        )
    ) else (
        echo Python 3.9.13 already installed. Using 3.9.13...
        set "PYTHON_VERSION=3.9.13"
    )
) else (
    echo Python 3.8.10 already installed. Proceeding...
)

REM Check if pyenv shims are available after install
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: pyenv shims are not available in PATH. Try closing and reopening this window, or run 'refreshenv' if available.
    pause
    exit /b 1
)

echo Setting Python %PYTHON_VERSION% as the local version for this directory...
pyenv local %PYTHON_VERSION% | echo %PYTHON_VERSION% > .python-version
if exist .python-version (
    echo Successfully set Python %PYTHON_VERSION% as local version.
) else (
    echo Failed to set Python %PYTHON_VERSION% as local version. Could not write .python-version file.
    pause
    exit /b 1
)

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
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment with pyenv Python.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat
echo Virtual environment activated.

REM Ensure pip is installed
echo Checking pip...
python -m ensurepip --upgrade

REM Install required libraries
echo Installing requirements...
pip install --upgrade pip
pip install -r requirements.txt

REM Debug: List hid twisted package location after pip install
echo Debug: Listing hid package files...
dir /s /b venv\Lib\site-packages\hid*

REM Check if hid/__init__.py exists
set "HID_INIT_PATH=%CD%\venv\Lib\site-packages\hid\__init__.py"
if not exist "%HID_INIT_PATH%" (
    echo ❌ hid/__init__.py not found after pip install. The hid package may not be installed correctly.
    echo Try running: pip install hid
    pause
    exit /b 1
)

REM Ensure hidapi.dll is present in the windows folder
if not exist "windows\hidapi.dll" (
    echo ❌ hidapi.dll not found in windows folder. Please place it in the 'windows' folder and retry.
    pause
    exit /b 1
)

REM Patch hid/__init__.py to load hidapi.dll directly
echo Patching hid/__init__.py to load hidapi.dll from windows/ directory...
set "TEMP_FILE=%CD%\hid_init_temp.py"
if exist "%HID_INIT_PATH%" (
    REM Create a backup
    copy "%HID_INIT_PATH%" "%HID_INIT_PATH%.bak"
    echo Created backup of hid/__init__.py at %HID_INIT_PATH%.bak

    REM Write new hidapi loading code to temporary file
    (
        echo # Generated by startwindow.bat
        echo import os
        echo import ctypes
        echo import atexit
        echo import enum
        echo.
        echo __all__ = ['HIDException', 'DeviceInfo', 'Device', 'enumerate', 'BusType']
        echo.
        echo lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__^), '../../../../windows/hidapi.dll'^)^)
        echo try:
        echo     hidapi = ctypes.cdll.LoadLibrary(lib_path^)
        echo except OSError as e:
        echo     raise ImportError(f"Unable to load hidapi.dll from {lib_path}: {str(e)}"^)
        echo.
        echo hidapi.hid_init(^)
        echo # Generated by startwindow.bat
    ) > "%TEMP_FILE%"

    REM Append the rest of __init__.py starting from hidapi.hid_init()
    @REM findstr /r /c:"hidapi\.hid_init()" /c:".*" "%HID_INIT_PATH%" >> "%TEMP_FILE%"
    setlocal enabledelayedexpansion
    set "SKIP=1"
    for /f "usebackq delims=" %%L in ("%HID_INIT_PATH%") do (
        if !SKIP! EQU 1 (
            echo %%L | findstr /c:"hidapi.hid_init()" >nul
            if not errorlevel 1 (
                set "SKIP=0"
            )
        ) else (
            echo %%L>>"%TEMP_FILE%"
        )
    )
    endlocal
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to extract content from hid/__init__.py. Please check the file content.
        pause
        exit /b 1
    )

    REM Replace the original file with the patched content
    move /Y "%TEMP_FILE%" "%HID_INIT_PATH%"
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to patch hid/__init__.py. Please check permissions and try again.
        pause
        exit /b 1
    )
    echo Successfully patched hid/__init__.py to load hidapi.dll directly.
) else (
    echo ❌ Could not find hid/__init__.py at %HID_INIT_PATH%. Please ensure the hid package is installed.
    pause
    exit /b 1
)

REM Set the library path and start the app
echo Starting app...
set "PATH=%PATH%;%~dp0windows"
python main.py
pause