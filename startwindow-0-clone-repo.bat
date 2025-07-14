@echo off
setlocal EnableDelayedExpansion

:: Check if installation directory and token are provided
if "%~1"=="" (
    echo ERROR: Installation directory not provided.
    echo Usage: %0 "install_dir" "github_token"
    pause >nul
    echo Please provide the installation directory and GitHub token.
    exit /b 1
)
if "%~2"=="" (
    echo ERROR: GitHub token not provided.
    echo Usage: %0 "install_dir" "github_token"
    pause >nul
    echo Please provide the GitHub token.
    exit /b 1
)

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
    pause >nul
    echo Please install Git and ensure it is in your PATH.
    exit /b 1
)

:: Create installation directory if it doesn't exist
if not exist "!INSTALL_DIR!" (
    mkdir "!INSTALL_DIR!"
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to create directory "!INSTALL_DIR!".
        pause >nul
        echo Please check permissions and try again.
        exit /b 1
    )
)

:: Clone the repository
:: Clone into a temporary folder inside INSTALL_DIR
echo Cloning repository to temporary directory...
set TEMP_CLONE_DIR=%INSTALL_DIR%\_temp_clone
git clone "!REPO_URL!" "%TEMP_CLONE_DIR%"

echo Moving cloned  "!INSTALL_DIR!"...
xcopy "%TEMP_CLONE_DIR%\*" "!INSTALL_DIR!\" /E /H /K /Y
xcopy "%TEMP_CLONE_DIR%\.*" "!INSTALL_DIR!\" /E /H /K /Y 2>nul

echo Remove the temporary clone folder
rmdir /S /Q "%TEMP_CLONE_DIR%"

@REM git clone "!REPO_URL!" "!INSTALL_DIR!"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to clone repository.
    pause >nul
    echo Please check the repository URL and your GitHub token.
    exit /b 1
)

:: Change to the installation directory
cd /d "!INSTALL_DIR!"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to change to directory "!INSTALL_DIR!".
    pause >nul
    echo Please check the directory path and try again.
    exit /b 1
)

:: Remove unwanted files (customize this list as needed)
echo Removing unwanted files...
del /s /q "!INSTALL_DIR!\*.command" >nul 2>&1
del /s /q "!INSTALL_DIR!\*.bat" >nul 2>&1
del /s /q "!INSTALL_DIR!\requirements.txt" >nul 2>&1
del /s /q "!INSTALL_DIR!\log_hid_data.py" >nul 2>&1
if exist "!INSTALL_DIR!\mac" (
    rmdir /s /q "!INSTALL_DIR!\mac"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "mac" directory.
    )
)

:: Add more file patterns or directories to exclude here, e.g.:
:: del /s /q "!INSTALL_DIR!\*.txt" >nul 2>&1
:: rmdir /s /q "!INSTALL_DIR!\test" >nul 2>&1

echo Repository cloned successfully to "!INSTALL_DIR!".
pause >nul
echo You can now proceed with the next steps in the setup process.
exit /b 0