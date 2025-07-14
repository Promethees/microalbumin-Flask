@echo off   
:: Ensure the script runs from its own directory
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "PYENV_PATH_CLONE=%USERPROFILE%\.pyenv\pyenv-win"
set "PYENV_PATH=%USERPROFILE%\.pyenv\pyenv-win\pyenv-win"
set "BIN_PATH=%PYENV_PATH%\bin"
set "SHIMS_PATH=%PYENV_PATH%\shims"

:: Check if running as administrator
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: This script must be run as Administrator to modify system PATH.
    echo Please right-click the script and select "Run as administrator".
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Check pyenv-win installation
:check_pyenv
echo Checking for pyenv-win installation...
if exist "%BIN_PATH%\pyenv.bat" (
    echo pyenv-win is already installed at %PYENV_PATH%.
    goto :set_pyenv
)

:: Install pyenv-win
echo pyenv-win not found. Cloning pyenv-win repository to %PYENV_PATH_CLONE%...
git clone https://github.com/pyenv-win/pyenv-win.git "%PYENV_PATH_CLONE%"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to clone pyenv-win repository. Ensure Git is installed and try again.
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Set pyenv-win environment variables
:set_pyenv
echo Setting pyenv-win environment variables...
setx PYENV "%PYENV_PATH%" /M
setx PYENV_ROOT "%PYENV_PATH%" /M
setx PYENV_HOME "%PYENV_PATH%" /M
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to set pyenv environment variables. Please check permissions.
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Add pyenv-win to PATH without overwriting existing PATH
echo Adding pyenv-win to PATH...
:: Get current system and user PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSTEM_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH') do set "USER_PATH=%%b"
set "CURRENT_PATH=%SYSTEM_PATH%;%USER_PATH%"
:: Remove any trailing semicolon
if "!CURRENT_PATH:~-1!"==";" set "CURRENT_PATH=!CURRENT_PATH:~0,-1!"
:: Check if pyenv paths are already in PATH to avoid duplicates
echo !CURRENT_PATH! | findstr /I /C:"%BIN_PATH%" >nul
if !ERRORLEVEL! neq 0 (
    set "NEW_PATH=!CURRENT_PATH!;%BIN_PATH%;%SHIMS_PATH%;%PYENV_PATH%"
    :: Check PATH length to avoid setx limitations
    set "PATH_LENGTH=0"
    for /L %%n in (0,1,8192) do if "!NEW_PATH:~%%n,1!" neq "" set /a PATH_LENGTH+=1
    if !PATH_LENGTH! GTR 1024 (
        echo WARNING: PATH length exceeds 1024 characters, which may cause issues with setx.
        echo Please shorten the existing PATH manually before proceeding.
        echo Press any key to continue . . .
        pause >nul
        exit /b 1
    )
    setx PATH "!NEW_PATH!" /M
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to update PATH. Please check permissions.
        echo Press any key to continue . . .
        pause >nul
        exit /b 1
    )
    echo Added pyenv-win paths to PATH.
) else (
    echo pyenv-win paths already exist in PATH. Skipping PATH update.
)

echo Pyenv is ready to use on C:\ drive.
echo Proceed to install Python in pyenv with "startwindow-3-python.bat"
echo Press any key to continue . . .
pause >nul
endlocal