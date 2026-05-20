@echo off
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "BACKUP_DIR="
set "HAS_BACKUP=0"
set "NSIS_MODE=0"

:: Check if installation directory is provided
if "%~1"=="" (
    echo ERROR: Installation directory not provided.
    echo Usage: %0 "install_dir" ["easyokapi_token"]
    exit /b 1
)

:: Resolve token — NSIS injects it as EASYOKAPI_DOWNLOAD_TOKEN (safe for all
:: special characters; never touches the cmd.exe command line).
:: Fall back to arg2 for direct / manual invocations.
if defined EASYOKAPI_DOWNLOAD_TOKEN (
    set "DOWNLOAD_TOKEN=%EASYOKAPI_DOWNLOAD_TOKEN%"
    set "NSIS_MODE=1"
) else if "%~2" neq "" (
    set "DOWNLOAD_TOKEN=%~2"
) else (
    echo ERROR: EasyOKAPI token not provided.
    echo Usage: %0 "install_dir" "easyokapi_token"
    exit /b 1
)

:: Version and auth service URL are substituted by the GitHub Actions build before packaging
set "VERSION_TAG=__APP_VERSION__"
set "AUTH_BASE_URL=__AUTH_BASE_URL__"

:: Set installation directory
set "INSTALL_DIR=%~1"

:: Convert to 8.3 short path at the top level (no surrounding block) so that
:: cmd.exe block parsing is never confused by parentheses in the path
:: (e.g. "C:\Program Files (x86)\...").  %%~sI resolves existing path
:: components to their 8.3 names; non-existent components are kept as-is but
:: any existing parent already loses its parens.
for %%I in ("!INSTALL_DIR!") do set "INSTALL_DIR=%%~sI"

:: Check if installation directory exists and is not empty
echo.
echo    ============================================
echo       EasyOKAPI - Installation Check
echo    ============================================
echo.

:: If installation directory doesn't exist, proceed directly to download
if not exist "!INSTALL_DIR!" (
    echo [*] Installation directory does not exist. Proceeding with new installation...
    echo.
    goto :skip_menu
)

:: Directory exists — count items to decide whether it is a real installation
set "item_count=0"
for /f %%i in ('dir /b "!INSTALL_DIR!" 2^>nul ^| find /c /v ""') do set "item_count=%%i"

:: Empty directory — skip the overwrite menu entirely
if !item_count! equ 0 (
    echo [*] Installation directory exists but is empty. Proceeding with installation...
    echo.
    goto :skip_menu
)

:: ── Existing installation found ───────────────────────────────────────────────
:: Everything below is at the TOP LEVEL (no outer block) so if-else is safe.
echo [*] An existing installation was found at:
echo     !INSTALL_DIR!
echo.

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

set "CHOICE="
if "!NSIS_MODE!"=="1" (
    echo [NSIS] Non-interactive mode - overwriting existing installation.
    set "CHOICE=1"
)
if "!CHOICE!"=="" set /p "CHOICE=Enter your choice [1 or 2]: "

if "!CHOICE!"=="2" (
    echo.
    echo Installation cancelled. Keeping existing installation.
    exit /b 0
)
if "!CHOICE!" neq "1" (
    echo.
    echo ERROR: Invalid choice. Please enter 1 or 2.
    exit /b 1
)

:: ── Overwrite path ────────────────────────────────────────────────────────────
echo.
echo Backing up user data (data, json, report)...
set "BACKUP_DIR=%TEMP%\easyokapi_backup_%RANDOM%"
for %%D in (data json report) do (
    if exist "!INSTALL_DIR!\%%D\" (
        if "!HAS_BACKUP!"=="0" (
            mkdir "!BACKUP_DIR!" >nul 2>&1
            set "HAS_BACKUP=1"
        )
        xcopy /e /i /q "!INSTALL_DIR!\%%D" "!BACKUP_DIR!\%%D\" >nul 2>&1
    )
)
echo Removing existing installation...
rmdir /s /q "!INSTALL_DIR!"
if !ERRORLEVEL! neq 0 (
    echo ERROR: Failed to remove existing installation.
    echo Please check permissions and try again.
    exit /b 1
)
mkdir "!INSTALL_DIR!"
echo Existing installation removed successfully.
echo.

:skip_menu

:: Check if curl is available (Windows 10+ has curl built-in)
where curl >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: curl is not installed or not found in PATH.
    echo Please install curl and ensure it is in your PATH.
    exit /b 1
)

:: Create installation directory if it doesn't exist
if not exist "!INSTALL_DIR!" mkdir "!INSTALL_DIR!"
if not exist "!INSTALL_DIR!" (
    echo ERROR: Failed to create directory "!INSTALL_DIR!".
    exit /b 1
)

:: Convert to 8.3 short path so cmd.exe block parsing is never tripped up by
:: parentheses in the path (e.g. "C:\Program Files (x86)\...").
for %%I in ("!INSTALL_DIR!") do set "INSTALL_DIR=%%~sI"

:: Download the application archive using the EasyOKAPI token
set "ARCHIVE_TMP=%TEMP%\easyokapi_app.tar.gz"
echo Downloading application to "!INSTALL_DIR!"...
curl -L -o "!ARCHIVE_TMP!" "!AUTH_BASE_URL!/api/download?token=!DOWNLOAD_TOKEN!"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to download the application. Check your token and network connection.
    exit /b 1
)

:: Extract archive (requires tar, available on Windows 10 1803+)
echo Extracting application...
tar -xzf "!ARCHIVE_TMP!" -C "!INSTALL_DIR!" --strip-components=1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to extract the application archive.
    del /q "!ARCHIVE_TMP!" >nul 2>&1
    exit /b 1
)
del /q "!ARCHIVE_TMP!" >nul 2>&1

:: Restore user data preserved from the previous installation
if "!HAS_BACKUP!"=="1" (
    echo Restoring user data (data, json, report)...
    pushd "!INSTALL_DIR!" >nul 2>&1
    for %%D in (data json report) do (
        if exist "!BACKUP_DIR!\%%D\" xcopy /e /i /q "!BACKUP_DIR!\%%D" "%%D\" >nul 2>&1
    )
    popd
    rmdir /s /q "!BACKUP_DIR!" >nul 2>&1
    echo User data restored successfully.
)

:: Remove dev-only files from the extracted archive
echo Removing development files...
pushd "!INSTALL_DIR!" >nul 2>&1
del /s /q "*.command" >nul 2>&1
del /s /q "*.bat" >nul 2>&1
del /s /q "log_hid_data.py" >nul 2>&1
del /s /q "generate-tree.sh" >nul 2>&1
del /s /q "BUILD_MAC.md" >nul 2>&1
del /s /q "Rule.md" >nul 2>&1
for %%D in (mac easyokapi-knowledge images installer-mac installer-win installer-linux tests .github) do (
    if exist "%%D" rmdir /s /q "%%D" >nul 2>&1
)
popd

:: Save version information for future checks
echo !VERSION_TAG!> "!INSTALL_DIR!\VERSION.txt"

:: Write activation.json — the download token doubles as the license token for the AI proxy
(echo {& echo   "license_token": "!DOWNLOAD_TOKEN!"& echo }) > "!INSTALL_DIR!\activation.json"

echo Application downloaded successfully to "!INSTALL_DIR!" (!VERSION_TAG!).
exit /b 0
