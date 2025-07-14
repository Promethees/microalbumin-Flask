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

:: Check for sufficient disk space on C:\ (Boot Camp may have limited space)
@REM echo Checking available disk space on C:\...
@REM for /f "tokens=2" %%a in ('fsutil volume diskfree C: ^| findstr /C:"Total # of free bytes"') do set "FREE_BYTES=%%a"
@REM set /a FREE_GB=%FREE_BYTES% / 1024 / 1024 / 1024
@REM if %FREE_GB% LSS 2 (
@REM     echo ERROR: Insufficient disk space on C:\. At least 2 GB is required.
@REM     echo Current free space: ~%FREE_GB% GB
@REM     echo Press any key to continue . . .
@REM     pause >nul
@REM     exit /b 1
@REM )

:: Check if Git is already installed
echo Checking if Git is already installed...
git --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Git is already installed and available in PATH.
    git --version
    echo Press any key to continue . . .
    pause >nul
    exit /b 0
)

:: Check if Git exists in the default installation path
if exist "%INSTALL_PATH%\cmd\git.exe" (
    echo Git is installed at %INSTALL_PATH% but not in PATH.
    echo Adding Git to PATH...
    :: Get current PATH
    for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "CURRENT_PATH=%%b"
    :: Check if Git path is already in PATH to avoid duplicates
    echo !CURRENT_PATH! | findstr /I /C:"%INSTALL_PATH%\cmd" >nul
    if !ERRORLEVEL! neq 0 (
        set "NEW_PATH=%CURRENT_PATH%;%INSTALL_PATH%\cmd"
        setx PATH "!NEW_PATH!"
        if !ERRORLEVEL! neq 0 (
            echo ERROR: Failed to update PATH. Please check permissions and try running as administrator.
            echo Press any key to continue . . .
            pause >nul
            exit /b 1
        )
        echo Git added to PATH. Please restart Command Prompt to use Git.
    ) else (
        echo Git path already exists in PATH. Skipping PATH update.
    )
    echo Press any key to continue . . .
    pause >nul
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
    echo Press any key to continue . . .
    pause >nul
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
            echo Press any key to continue . . .
            pause >nul
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
                echo Press any key to continue . . .
                pause >nul
                exit /b 1
            )
        )
    )
    
    :: Clean up
    echo Cleaning up...
    del "%DOWNLOAD_PATH%\%GIT_INSTALLER%"
) else (
    echo ERROR: Failed to download Git installer.
    echo Press any key to continue . . .
    pause >nul
    exit /b 1
)

:: Add Git to PATH
echo Adding Git to PATH...
:: Get current PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "CURRENT_PATH=%%b"
:: Check if Git path is already in PATH to avoid duplicates
echo !CURRENT_PATH! | findstr /I /C:"%INSTALL_PATH%\cmd" >nul
if !ERRORLEVEL! neq 0 (
    set "NEW_PATH=%CURRENT_PATH%;%INSTALL_PATH%\cmd"
    setx PATH "!NEW_PATH!"
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to update PATH. Please check permissions and try running as administrator.
        echo Press any key to continue . . .
        pause >nul
        exit /b 1
    )
    echo Git added to PATH.
) else (
    echo Git path already exists in PATH. Skipping PATH update.
)

echo Setup complete. Git installed at %INSTALL_PATH%.
echo Proceed to install pyenv-win and Python with "startwindow-2-pyenv-python.bat"
echo Press any key to continue . . .
pause >nul
endlocal