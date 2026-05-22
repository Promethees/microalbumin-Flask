@echo off
:: Ensure the script runs from its own directory
cd /d "%~dp0"
setlocal EnableDelayedExpansion

:: Purpose: Install Git (with architecture compatibility for Boot Camp on C:\)
:: Set Git variables
set "GIT_URL_64=https://github.com/git-for-windows/git/releases/download/v2.50.0.windows.1/Git-2.50.0-64-bit.exe"
set "GIT_URL_32=https://github.com/git-for-windows/git/releases/download/v2.50.0.windows.1/Git-2.50.0-32-bit.exe"
set "GIT_INSTALLER_64=Git-2.50.0-64-bit.exe"
set "GIT_INSTALLER_32=Git-2.50.0-32-bit.exe"
set "DOWNLOAD_PATH=%TEMP%"
set "INSTALL_PATH=C:\Program Files\Git"

:: Check if running as administrator
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: This script must be run as Administrator to modify system PATH.
    echo Please right-click the script and select "Run as administrator".
    exit /b 1
)

:: Check if Git is already installed
echo Checking if Git is already installed...
git --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Git is already installed and available in PATH.
    git --version
    exit /b 0
)

:: Check if Git exists in the default installation path
if exist "%INSTALL_PATH%\cmd\git.exe" (
    echo Git is installed at %INSTALL_PATH% but not in PATH.
    echo Adding Git to PATH...
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSTEM_PATH=%%b"
    if "!SYSTEM_PATH:~-1!"==";" set "SYSTEM_PATH=!SYSTEM_PATH:~0,-1!"
    echo !SYSTEM_PATH! | findstr /I /C:"%INSTALL_PATH%\cmd" >nul
    if !ERRORLEVEL! neq 0 (
        set "NEW_PATH=!SYSTEM_PATH!;%INSTALL_PATH%\cmd"
        reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH /t REG_EXPAND_SZ /d "!NEW_PATH!" /f >nul
        if !ERRORLEVEL! neq 0 (
            echo ERROR: Failed to update PATH. Please check permissions.
            exit /b 1
        )
        echo Git added to PATH. Please restart Command Prompt to use Git.
    ) else (
        echo Git path already exists in PATH. Skipping PATH update.
    )
    exit /b 0
)

:: Check system architecture for Boot Camp (typically 64-bit on modern Macs)
echo Checking system architecture...
wmic OS get OSArchitecture | findstr /C:"64-bit" >nul
if %ERRORLEVEL% equ 0 (
    set "GIT_URL=%GIT_URL_64%"
    set "GIT_INSTALLER=%GIT_INSTALLER_64%"
    echo Detected 64-bit system. Using 64-bit Git installer.
) else (
    set "GIT_URL=%GIT_URL_32%"
    set "GIT_INSTALLER=%GIT_INSTALLER_32%"
    echo Detected 32-bit system. Using 32-bit Git installer.
)

:: Download preferred Git installer
echo Downloading Git installer from %GIT_URL%...
curl -L -o "%DOWNLOAD_PATH%\%GIT_INSTALLER%" "%GIT_URL%"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to download Git installer from %GIT_URL%.
    exit /b 1
)

if exist "%DOWNLOAD_PATH%\%GIT_INSTALLER%" (
    echo Installing Git to %INSTALL_PATH%...
    start /wait "" "%DOWNLOAD_PATH%\%GIT_INSTALLER%" /VERYSILENT /NORESTART /DIR="%INSTALL_PATH%" /COMPONENTS="icons,ext,ext\shellhere,ext\guihere,gitlfs,console,console\gitbash,console\gitgui"

    :: Check if Git was installed successfully
    if exist "%INSTALL_PATH%\cmd\git.exe" (
        echo Git installed successfully at %INSTALL_PATH%
    ) else (
        echo Failed to install Git with %GIT_INSTALLER%. Trying alternative installer...
        :: Switch to alternative installer
        if "%GIT_URL%"=="%GIT_URL_64%" (
            set "GIT_URL=%GIT_URL_32%"
            set "GIT_INSTALLER=%GIT_INSTALLER_32%"
        ) else (
            set "GIT_URL=%GIT_URL_64%"
            set "GIT_INSTALLER=%GIT_INSTALLER_64%"
        )
        echo Downloading alternative Git installer from %GIT_URL%...
        curl -L -o "%DOWNLOAD_PATH%\%GIT_INSTALLER%" "%GIT_URL%"
        if %ERRORLEVEL% neq 0 (
            echo ERROR: Failed to download alternative Git installer.
            exit /b 1
        )
        if exist "%DOWNLOAD_PATH%\%GIT_INSTALLER%" (
            echo Installing Git with alternative installer...
            start /wait "" "%DOWNLOAD_PATH%\%GIT_INSTALLER%" /VERYSILENT /NORESTART /DIR="%INSTALL_PATH%" /COMPONENTS="icons,ext,ext\shellhere,ext\guihere,gitlfs,console,console\gitbash,console\gitgui"
            if exist "%INSTALL_PATH%\cmd\git.exe" (
                echo Git installed successfully with alternative installer at %INSTALL_PATH%
            ) else (
                echo ERROR: Failed to install Git with both installers. Please check compatibility and try again.
                del "%DOWNLOAD_PATH%\%GIT_INSTALLER%"
                exit /b 1
            )
        )
    )

    :: Clean up
    echo Cleaning up...
    del "%DOWNLOAD_PATH%\%GIT_INSTALLER%"
) else (
    echo ERROR: Failed to download Git installer.
    exit /b 1
)

:: Add Git to PATH
echo Adding Git to PATH...
:: Get current system and user PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSTEM_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v PATH') do set "USER_PATH=%%b"
set "CURRENT_PATH=%SYSTEM_PATH%;%USER_PATH%"
:: Remove any trailing semicolon
if "!CURRENT_PATH:~-1!"==";" set "CURRENT_PATH=!CURRENT_PATH:~0,-1!"
:: Check if Git path is already in PATH to avoid duplicates
echo !CURRENT_PATH! | findstr /I /C:"%INSTALL_PATH%\cmd" >nul
if !ERRORLEVEL! neq 0 (
    set "NEW_PATH=!CURRENT_PATH!;%INSTALL_PATH%\cmd"
    :: Check PATH length to avoid setx limitations
    set "PATH_LENGTH=0"
    for /L %%n in (0,1,8192) do if "!NEW_PATH:~%%n,1!" neq "" set /a PATH_LENGTH+=1
    if !PATH_LENGTH! GTR 1024 (
        echo WARNING: PATH length exceeds 1024 characters, which may cause issues with setx.
        echo Please shorten the existing PATH manually before proceeding.
        exit /b 1
    )
    setx PATH "!NEW_PATH!" /M
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to update PATH. Please check permissions.
        exit /b 1
    )
    echo Git added to PATH.
) else (
    echo Git path already exists in PATH. Skipping PATH update.
)

echo Setup complete. Git installed at %INSTALL_PATH%.
endlocal
