:: Install pyenv-win and Python 3.8.10 or 3.9.13
@echo off   
setlocal EnableDelayedExpansion

set "PYENV_PATH_CLONE=%USERPROFILE%\.pyenv\pyenv-win"
set "PYENV_PATH=%USERPROFILE%\.pyenv\pyenv-win\pyenv-win"
set "BIN_PATH=%PYENV_PATH%\bin"
set "SHIMS_PATH=%PYENV_PATH%\shims"
set "PREFERRED_PYTHON=3.8.10"
set "FALLBACK_PYTHON=3.9.13"
set "PYTHON_VERSION="

:: Check pyenv-win installation
:check_pyenv
echo Checking for pyenv-win installation...
if exist "%BIN_PATH%\pyenv.bat" (
    echo pyenv-win is already installed at %PYENV_PATH%.
    goto :check_python
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
echo Setting pyenv-win environment variables...
setx PYENV "%PYENV_PATH%"
setx PYENV_ROOT "%PYENV_PATH%"
setx PYENV_HOME "%PYENV_PATH%"

:: Add pyenv-win to PATH
echo Adding pyenv-win to PATH...
setx PATH "%BIN_PATH%;%SHIMS_PATH%;%PATH%"

:: Verify pyenv-win installation
"%BIN_PATH%\pyenv" --version >nul 2>&1 | echo Verifying pyenv-win installation...
if %ERRORLEVEL% equ 0 (
    echo pyenv-win installed and configured successfully. Version: | "%BIN_PATH%\pyenv" --version
) else (
    echo ERROR: Failed to verify pyenv-win installation. Ensure the repository was cloned correctly.
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Check Python versions
:check_python
echo Checking for Python %PREFERRED_PYTHON%...
pyenv versions | findstr %PREFERRED_PYTHON% >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Python %PREFERRED_PYTHON% is already installed.
    set "PYTHON_VERSION=%PREFERRED_PYTHON%"
    goto :set_python
)

echo Python %PREFERRED_PYTHON% not found. Checking for Python %FALLBACK_PYTHON%...
pyenv versions | findstr %FALLBACK_PYTHON% >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Python %FALLBACK_PYTHON% is already installed.
    set "PYTHON_VERSION=%FALLBACK_PYTHON%"
    goto :set_python
)

:: Install preferred Python version
echo Neither Python %PREFERRED_PYTHON% nor %FALLBACK_PYTHON% found. 
echo Installing Python %PREFERRED_PYTHON%... | pyenv install %PREFERRED_PYTHON%
if %ERRORLEVEL% equ 0 (
    echo Python %PREFERRED_PYTHON% installed successfully.
    set "PYTHON_VERSION=%PREFERRED_PYTHON%"
) else (
    echo Failed to install Python %PREFERRED_PYTHON%. 
    echo Attempting to install Python %FALLBACK_PYTHON%... | pyenv install %FALLBACK_PYTHON%
    if %ERRORLEVEL% equ 0 (
        echo Python %FALLBACK_PYTHON% installed successfully.
        set "PYTHON_VERSION=%FALLBACK_PYTHON%"
    ) else (
        echo ERROR: Failed to install Python %FALLBACK_PYTHON%. Please check pyenv configuration and try again.
        echo Press any key to continue . . .
        pause >nul
        exit /b 1
    )
)

:: Set global Python version
:set_python
if %ERRORLEVEL% equ 0 (
    echo Setting Python %PYTHON_VERSION% as global version...
    pyenv global %PYTHON_VERSION% | echo Python %PYTHON_VERSION% is now set as the global version.
    @REM echo Verifying Python version...
    @REM python --version || echo Python %PYTHON_VERSION% is set as the global version.
) else (
    echo ERROR: No Python version was set. Please check pyenv configuration.
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Rehash shims
echo Updating pyenv shims... | pyenv rehash

echo Setup complete. Current Python Version: %PYTHON_VERSION%. Current Pyenv Version: %PYENV_VERSION%.
echo Git and Python are ready to use on C:\ drive.
echo Proceed to install dependencies with in the venv and run main program: with "startwindow.bat"
echo Press any key to continue . . .
pause >nul
endlocal