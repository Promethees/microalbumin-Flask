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
set "VERSION_TAG=v1.0.0"

:: Set installation directory and token
set "INSTALL_DIR=%~1"
set "GITHUB_TOKEN=%~2"

:: Define GitHub repository URL
set "REPO_BASE=https://github.com/Promethees/microalbumin-Flask.git"
set "REPO_URL=https://!GITHUB_TOKEN!@github.com/Promethees/microalbumin-Flask.git"

:: Check if installation directory exists and is not empty
echo.
echo    ============================================
echo       EasyOKAPI - Installation Check
echo    ============================================
echo.

:: If installation directory doesn't exist, proceed directly to cloning
if not exist "!INSTALL_DIR!" (
    echo [*] Installation directory does not exist. Proceeding with new installation...
    echo.
    goto :skip_menu
)

:: Directory exists, count items to check if it's non-empty
set "item_count=0"
for /f %%i in ('dir /b "!INSTALL_DIR!" 2^>nul ^| find /c /v ""') do set "item_count=%%i"

if !item_count! gtr 0 (
    echo [*] An existing installation was found at:
    echo     !INSTALL_DIR!
    echo.
    
    :: Check if version file exists to display current version
    if exist "!INSTALL_DIR!\VERSION.txt" (
        set /p CURRENT_VERSION=<"!INSTALL_DIR!\VERSION.txt"
        echo     Current version: !CURRENT_VERSION!
    ) else (
        echo     Current version: Unknown (no version file found)
        set "CURRENT_VERSION=Unknown"
    )
    
    echo     New version: !VERSION_TAG!
    echo.
    echo Options:
    echo   [1] Overwrite existing installation (recommended for updates)
    echo   [2] Cancel and keep existing installation
    echo.
    
    set /p "CHOICE=Enter your choice [1 or 2]: "
    
    if "!CHOICE!"=="1" (
        echo.
        echo Removing existing installation...
        rmdir /s /q "!INSTALL_DIR!"
        if !ERRORLEVEL! neq 0 (
            echo ERROR: Failed to remove existing installation.
            echo Please check permissions and try again.
            pause >nul
            exit /b 1
        )
        :: Recreate the empty directory
        mkdir "!INSTALL_DIR!"
        echo Existing installation removed successfully.
    ) else if "!CHOICE!"=="2" (
        echo.
        echo Installation cancelled. Keeping existing installation.
        pause >nul
        exit /b 0
    ) else (
        echo.
        echo ERROR: Invalid choice. Please enter 1 or 2.
        pause >nul
        exit /b 1
    )
    echo.
) else (
    echo [*] Installation directory exists but is empty. Proceeding with installation...
    echo.
)

:skip_menu

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

:: Remove Git ignore file if it exists
if exist ".gitignore" (
    del /q ".gitignore"
    if %ERRORLEVEL% neq 0 (
        echo WARNING: Failed to remove .gitignore file.
    )
)

:: Remove unwanted files (customize this list as needed)
echo Removing unwanted files...
del /s /q "!INSTALL_DIR!\*.command" >nul 2>&1
del /s /q "!INSTALL_DIR!\*.bat" >nul 2>&1
del /s /q "!INSTALL_DIR!\log_hid_data.py" >nul 2>&1
del /s /q "!INSTALL_DIR!\requirements.txt" >nul 2>&1
del /s /q "!INSTALL_DIR!\generate-tree.sh" >nul 2>&1
del /s /q "!INSTALL_DIR!\BUILD_MAC.md" >nul 2>&1
del /s /q "!INSTALL_DIR!\Rule.md" >nul 2>&1
if exist "!INSTALL_DIR!\mac" (
    rmdir /s /q "!INSTALL_DIR!\mac"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "mac" directory.
    )
)
if exist "!INSTALL_DIR!\easyokapi-knowledge" (
    rmdir /s /q "!INSTALL_DIR!\easyokapi-knowledge"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "easyokapi-knowledge" directory.
    )
)
if exist "!INSTALL_DIR!\images" (
    rmdir /s /q "!INSTALL_DIR!\images"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "images" directory.
    )
)
if exist "!INSTALL_DIR!\installer-mac" (
    rmdir /s /q "!INSTALL_DIR!\installer-mac"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "installer-mac" directory.
    )
)
if exist "!INSTALL_DIR!\installer-win" (
    rmdir /s /q "!INSTALL_DIR!\installer-win"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "installer-win" directory.
    )
)
if exist "!INSTALL_DIR!\tests" (
    rmdir /s /q "!INSTALL_DIR!\tests"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove "tests" directory.
    )
)
if exist "!INSTALL_DIR!\.github" (
    rmdir /s /q "!INSTALL_DIR!\.github"
    if !ERRORLEVEL! neq 0 (
        echo WARNING: Failed to remove ".github" directory.
    )
)

:: Add more file patterns or directories to exclude here, e.g.:
:: del /s /q "!INSTALL_DIR!\*.txt" >nul 2>&1
:: rmdir /s /q "!INSTALL_DIR!\test" >nul 2>&1

:: Save version information for future checks
echo !VERSION_TAG!> "!INSTALL_DIR!\VERSION.txt"

echo Repository cloned successfully to "!INSTALL_DIR!" with tag "!VERSION_TAG!".
echo You can now proceed with the next steps in the setup process.
echo Press any key to continue...
pause >nul
exit /b 0