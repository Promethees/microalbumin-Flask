@echo off

REM Exit on error
if errorlevel 1 exit /b 1

REM Change to the script's directory
cd /d "%~dp0"

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ❌ Python not found. Installing Python 3.8.10...
    REM Download Python 3.8.10 installer
    curl -o python-installer.exe https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe
    REM Install Python 3.8.10 silently
    python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
    REM Clean up
    del python-installer.exe
    REM Refresh environment variables
    set "PATH=%PATH%;C:\Program Files\Python38;C:\Program Files\Python38\Scripts"
) else (
    REM Check Python version
    for /f "tokens=2 delims= " %%a in ('python --version 2^>nul') do set PY_VER=%%a
    if not "%PY_VER%"=="3.8.10" (
        echo ❌ Python 3.8.10 is required. Current version: %PY_VER%
        echo Installing Python 3.8.10...
        curl -o python-installer.exe https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe
        python-installer.exe /quiet InstallAllUsers=1 PrependPath=1
        del python-installer.exe
        set "PATH=%PATH%;C:\Program Files\Python38;C:\Program Files\Python38\Scripts"
    )
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

REM Ensure libhidapi-0.dll is present in the windows folder
if not exist "windows\libhidapi-0.dll" (
    echo ❌ libhidapi-0.dll not found in windows folder. Please place it in the 'windows' folder and retry.
    exit /b 1
)

REM Modify hid/__init__.py to load libhidapi-0.dll explicitly
set "HID_INIT_PATH=venv\Lib\site-packages\hid\__init__.py"
if exist "%HID_INIT_PATH%" (
    REM Create a backup
    copy "%HID_INIT_PATH%" "%HID_INIT_PATH%.bak"
    echo Created backup of hid/__init__.py at %HID_INIT_PATH%.bak

    REM Use a temporary file to handle multiline insertion
    set "TEMP_FILE=%TEMP%\hid_init_temp.py"
    echo import os > "%TEMP_FILE%"
    echo import ctypes >> "%TEMP_FILE%"
    echo. >> "%TEMP_FILE%"
    echo # Explicitly load libhidapi-0.dll from windows folder >> "%TEMP_FILE%"
    echo lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../windows/hidapi.dll')) >> "%TEMP_FILE%"
    echo hidapi = ctypes.cdll.LoadLibrary(lib_path) >> "%TEMP_FILE%"
    echo. >> "%TEMP_FILE%"
    echo # Original library search loop disabled to prevent overwriting hidapi >> "%TEMP_FILE%"
    echo # hidapid = None >> "%TEMP_FILE%"
    echo # library_paths = ( >> "%TEMP_FILE%"
    echo #     'libhidapi-hidraw.so', >> "%TEMP_FILE%"
    echo #     'libhidapi-hidraw.so.0', >> "%TEMP_FILE%"
    echo #     'libhidapi-libusb.so', >> "%TEMP_FILE%"
    echo #     'libhidapi-libusb.so.0', >> "%TEMP_FILE%"
    echo #     'libhidapi-iohidmanager.so', >> "%TEMP_FILE%"
    echo #     'libhidapi-iohidmanager.so.0', >> "%TEMP_FILE%"
    echo #     'libhidapi.dylib', >> "%TEMP_FILE%"
    echo #     'hidapi.dll', >> "%TEMP_FILE%"
    echo #     'libhidapi-0.dll' >> "%TEMP_FILE%"
    echo # ) >> "%TEMP_FILE%"
    echo # >> "%TEMP_FILE%"
    echo # for lib in library_paths: >> "%TEMP_FILE%"
    echo #     try: >> "%TEMP_FILE%"
    echo #         hidapi = ctypes.cdll.LoadLibrary(lib) >> "%TEMP_FILE%"
    echo #         break >> "%TEMP_FILE%"
    echo #     except OSError: >> "%TEMP_FILE%"
    echo #         pass >> "%TEMP_FILE%"
    echo # else: >> "%TEMP_FILE%"
    echo #     error = "Unable to load any of the following libraries:{}" >> "%TEMP_FILE%"
    echo #         .format(' '.join(library_paths)) >> "%TEMP_FILE%"
    echo #     raise ImportError(error) >> "%TEMP_FILE%"
    echo. >> "%TEMP_FILE%"
    type "%HID_INIT_PATH%" >> "%TEMP_FILE%"
    REM Remove the original loop section from the appended file
    powershell -Command "(Get-Content '%TEMP_FILE%') -notmatch 'hidapi = None .*raise ImportError' | Set-Content '%TEMP_FILE%'"
    copy /Y "%TEMP_FILE%" "%HID_INIT_PATH%" >nul
    del "%TEMP_FILE%"
    echo Modified hid/__init__.py to load libhidapi-0.dll from windows/ directory and disabled original loop
) else (
    echo ❌ Could not find hid/__init__.py. Please ensure the hid package is installed.
    exit /b 1
)

REM Set the library path and start the app
echo Starting app...
set "PATH=%PATH%;%~dp0windows"
python main.py
pause