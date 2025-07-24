@echo off
cd /d "%~dp0"
setlocal EnableDelayedExpansion

:: Check if installation directory and token are provided
if "%~1"=="" (
    echo ERROR: Installation directory not provided.
    echo Usage: %0 "install_dir" "github_token"
    echo Please provide the installation directory and GitHub token.
    pause >nul
    exit /b 1
)
if "%~2"=="" (
    echo ERROR: GitHub token not provided.
    echo Usage: %0 "install_dir" "github_token"
    echo Please provide the GitHub token.
    pause >nul
    exit /b 1
)

:: Set Version tag
set "VERSION_TAG=v0.0.1beta"

:: Set installation directory and token
set "INSTALL_DIR=%~1"
set "GITHUB_TOKEN=%~2"

:: Define GitHub repository URL
set "REPO_BASE=https://github.com/Promethees/microalbumin-Flask.git"
set "REPO_URL=https://!GITHUB_TOKEN!@github.com/Promethees/microalbumin-Flask.git"

:: Check if Git is installed
where git >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Git is not installed or not found in PATH.
    echo Please install Git and ensure it is in your PATH.
    pause >nul
    exit /b 1
)

:: Create installation directory if it doesn't exist
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!"
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to create directory "!INSTALL_DIR!".
        echo Please check permissions and try again.
        pause >nul
        exit /b 1
    )
)

:: Clone the repository and capture output
echo Cloning repository to "!INSTALL_DIR!"...
git clone "!REPO_URL!" "!INSTALL_DIR!" 2>&1 | findstr /V "Cloning into"

:: Change to the installation directory
cd /d "!INSTALL_DIR!"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to change to directory "!INSTALL_DIR!".
    echo Please check the directory path and try again.
    pause >nul
    exit /b 1
)

:: Checkout specific tag
echo Checking out tag "!VERSION_TAG!"...
git checkout tags/"!VERSION_TAG!"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to checkout tag "!VERSION_TAG!".
    echo Please check if the tag exists.
    pause >nul
    exit /b 1
)

:: Remove Git history
echo Removing Git history...
rd /s /q ".git"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to remove Git history.
    pause >nul
    exit /b 1
)

:: Remove unwanted files (customize this list as needed)
echo Removing unwanted files...
del /s /q "!INSTALL_DIR!\*.command" >nul 2>&1
del /s /q "!INSTALL_DIR!\*.bat" >nul 2>&1
del /s /q "!INSTALL_DIR!\log_hid_data.py" >nul 2>&1
del /s /q "!INSTALL_DIR!\main.py" >nul 2>&1
del /s /q "!INSTALL_DIR!\requirements.txt" >nul 2>&1
if exist "!INSTALL_DIR!\mac" (
    rmdir /s /q "!INSTALL_DIR!\mac"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "mac" directory.
    )
)

:: Add more file patterns or directories to exclude here, e.g.:
:: del /s /q "!INSTALL_DIR!\*.txt" >nul 2>&1
:: rmdir /s /q "!INSTALL_DIR!\test" >nul 2>&1

echo Repository cloned successfully to "!INSTALL_DIR!" with tag "!VERSION_TAG!".
echo You can now proceed with the next steps in the setup process.
echo Press any key to continue...
pause >nul
exit /b 0