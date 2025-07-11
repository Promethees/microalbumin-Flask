:: Install pyenv-win 
@echo off   
:: Ensure the script runs from its own directory
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "PYENV_PATH_CLONE=%USERPROFILE%\.pyenv\pyenv-win"
set "PYENV_PATH=%USERPROFILE%\.pyenv\pyenv-win\pyenv-win"
set "BIN_PATH=%PYENV_PATH%\bin"
set "SHIMS_PATH=%PYENV_PATH%\shims"

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
setx PYENV "%PYENV_PATH%"
setx PYENV_ROOT "%PYENV_PATH%"
setx PYENV_HOME "%PYENV_PATH%"

:: Add pyenv-win to PATH
echo Adding pyenv-win to PATH...
setx PATH "%BIN_PATH%;%SHIMS_PATH%;%PYENV_PATH%"

echo Pyenv is ready to use on C:\ drive.
echo Proceed to install Python in pyenv with "startwindow-3-python.bat"
echo Press any key to continue . . .
pause >nul
endlocal
