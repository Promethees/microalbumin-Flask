:: Install Python 3.8.10 or 3.9.13
@echo off
:: Ensure the script runs from its own directory
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "PYENV_PATH_CLONE=%USERPROFILE%\.pyenv\pyenv-win"
set "PYENV_PATH=%USERPROFILE%\.pyenv\pyenv-win\pyenv-win"
set "BIN_PATH=%PYENV_PATH%\bin"
set "SHIMS_PATH=%PYENV_PATH%\shims"
set "PREFERRED_PYTHON=3.8.10"
set "FALLBACK_PYTHON=3.9.13"
set "PYTHON_VERSION="

:: Verify pyenv-win installation
"%BIN_PATH%\pyenv" --version >nul 2>&1 | echo Verifying pyenv-win installation...
if %ERRORLEVEL% equ 0 (
    for /f "delims=" %%v in ('"%BIN_PATH%\pyenv" --version') do (
    echo pyenv-win installed and configured successfully. Version: %%v
)
) else (
    echo ERROR: Failed to verify pyenv-win installation. Ensure the repository was cloned correctly.
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
        exit /b 1
    )
)

:: Set global Python version
:set_python
if %ERRORLEVEL% equ 0 (
    echo Setting Python %PYTHON_VERSION% as global version...
    pyenv global %PYTHON_VERSION% | echo Python %PYTHON_VERSION% is now set as the global version.
) else (
    echo ERROR: No Python version was set. Please check pyenv configuration.
    exit /b 1
)

:: Rehash shims
echo Updating pyenv shims... | pyenv rehash

echo Setup complete. Current Python Version: %PYTHON_VERSION%. Current Pyenv Version: %PYENV_VERSION%.
endlocal
