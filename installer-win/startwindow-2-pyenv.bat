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
    exit /b 1
)

:: Check pyenv-win installation
:check_pyenv
echo Checking for pyenv-win installation...
if exist "%BIN_PATH%\pyenv.bat" (
    echo pyenv-win is already installed at %PYENV_PATH%.
    goto :set_pyenv
)

:: Install pyenv-win — three-tier fallback so this works even when Git was
:: just installed in the same NSIS session (setx /M updates the registry but
:: the parent process environment is not refreshed until a new login session,
:: so 'git' may not yet be on PATH even though the exe is on disk).
echo pyenv-win not found. Installing pyenv-win to %PYENV_PATH_CLONE%...
set "PYENV_CLONED=0"

:: Attempt 1 — git already in PATH (pre-existing install)
git clone https://github.com/pyenv-win/pyenv-win.git "%PYENV_PATH_CLONE%" >nul 2>&1
if !ERRORLEVEL! equ 0 set "PYENV_CLONED=1"
if "!PYENV_CLONED!"=="1" echo pyenv-win cloned via git (PATH).

:: Attempt 2 — git at the default Git-for-Windows install path (just installed
:: this session; PATH not yet refreshed in the NSIS parent environment)
if "!PYENV_CLONED!"=="0" (
    if exist "C:\Program Files\Git\cmd\git.exe" (
        "C:\Program Files\Git\cmd\git.exe" clone https://github.com/pyenv-win/pyenv-win.git "%PYENV_PATH_CLONE%"
        if !ERRORLEVEL! equ 0 (
            set "PYENV_CLONED=1"
            echo pyenv-win cloned via git ^(full path^).
        )
    )
)

:: Attempt 3 — no git available; download the master zip via PowerShell
if "!PYENV_CLONED!"=="0" (
    echo Git not available. Downloading pyenv-win archive via PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$zip='%TEMP%\pyenv-win.zip'; $dst='%PYENV_PATH_CLONE%'; Invoke-WebRequest -UseBasicParsing 'https://github.com/pyenv-win/pyenv-win/archive/refs/heads/master.zip' -OutFile $zip; Expand-Archive -Force $zip '%TEMP%\pyenv-win-extract'; if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }; Move-Item '%TEMP%\pyenv-win-extract\pyenv-win-master' $dst; Remove-Item $zip -ErrorAction SilentlyContinue"
    if !ERRORLEVEL! equ 0 (
        set "PYENV_CLONED=1"
        echo pyenv-win downloaded via PowerShell.
    )
)

if "!PYENV_CLONED!"=="0" (
    echo ERROR: Failed to install pyenv-win. Ensure you have an internet connection and try again.
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
    exit /b 1
)

:: Add pyenv-win to System PATH only (never mix User PATH in — causes duplicates on retries).
:: Uses reg add instead of setx to bypass setx's 1024-char truncation limit.
echo Adding pyenv-win to PATH...
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSTEM_PATH=%%b"
:: Remove any trailing semicolon
if "!SYSTEM_PATH:~-1!"==";" set "SYSTEM_PATH=!SYSTEM_PATH:~0,-1!"
:: Check System PATH only — avoids re-adding entries already present from a previous run
echo !SYSTEM_PATH! | findstr /I /C:"%BIN_PATH%" >nul
if !ERRORLEVEL! neq 0 (
    set "NEW_PATH=!SYSTEM_PATH!;%BIN_PATH%;%SHIMS_PATH%;%PYENV_PATH%"
    reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH /t REG_EXPAND_SZ /d "!NEW_PATH!" /f >nul
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to update PATH. Please check permissions.
        exit /b 1
    )
    echo Added pyenv-win paths to PATH.
) else (
    echo pyenv-win paths already exist in PATH. Skipping PATH update.
)

echo Pyenv is ready to use on C:\ drive.
endlocal
