@echo off
setlocal enabledelayedexpansion

:: Set console window icon to ht.ico
set "_ICON_PS=%TEMP%\easyokapi_icon.ps1"
if exist "%_ICON_PS%" del "%_ICON_PS%"
echo Add-Type -AssemblyName System.Drawing >> "%_ICON_PS%"
echo Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l); [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();' -Name ConsW -Namespace Prg >> "%_ICON_PS%"
echo $ico = New-Object System.Drawing.Icon('%~dp0ht.ico') >> "%_ICON_PS%"
echo $hwnd = [Prg.ConsW]::GetConsoleWindow() >> "%_ICON_PS%"
echo [Prg.ConsW]::SendMessage($hwnd, 0x80, [IntPtr]::Zero, $ico.Handle) >> "%_ICON_PS%"
echo [Prg.ConsW]::SendMessage($hwnd, 0x80, [IntPtr]1, $ico.Handle) >> "%_ICON_PS%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%_ICON_PS%" 2>nul
del "%_ICON_PS%" 2>nul

:: Ensure the script runs from its own directory
cd /d "%~dp0"

:: ── Progress Bar Setup ─────────────────────────────────────────────────────
set "BAR_WIDTH=40"
set "PROGRESS_FILE=%TEMP%\easyokapi_progress.txt"
if exist "%PROGRESS_FILE%" del "%PROGRESS_FILE%"

:: Helper to draw the progress bar using PowerShell
set "DRAW_PROGRESS=powershell -NoProfile -ExecutionPolicy Bypass -ArgumentList"  "^" "-Command" ^
    "param($pct, $label); $filled=[int]($pct * %BAR_WIDTH% / 100); $empty=%BAR_WIDTH% - $filled; $bar = ('=' * $filled) + ('-' * $empty); Write-Host -NoNewline \"`r  [$bar] $([string]$pct).PadLeft(3)%%  $label\""

:: Smoothly fill the bar from %1 to %2
set "FILL_TO=for /L %%p in (%1,1,%2) do ( %DRAW_PROGRESS% %%p \"%~3\" & timeout /t 0 /nobreak >nul )"

:: ── Banner ──────────────────────────────────────────────────────────────────
cls
echo.
echo    ============================================
echo       EasyOKAPI - Launching...
echo    ============================================
echo.

:: ── Step 1 : Initialise (0 → 30%) ──────────────────────────────────────────
echo Initialising environment...
for /L %%p in (0,1,30) do (
    cls
    echo.
    echo    ============================================
    echo       EasyOKAPI - Launching...
    echo    ============================================
    echo.
    echo Initialising environment...
    set /a "filled=%%p * %BAR_WIDTH% / 100"
    set /a "empty=%BAR_WIDTH% - !filled!"
    set "bar="
    for /L %%i in (1,1,!filled!) do set "bar=!bar!=" 
    for /L %%i in (1,1,!empty!) do set "bar=!bar!-"
    echo [!bar!] %%p%%
    timeout /t 0 /nobreak >nul 2>&1
)

:: ── Step 2 : Activate (30 → 60%) ───────────────────────────────────────────
echo Activating virtual environment...
for /L %%p in (30,1,60) do (
    cls
    echo.
    echo    ============================================
    echo       EasyOKAPI - Launching...
    echo    ============================================
    echo.
    echo Activating virtual environment...
    set /a "filled=%%p * %BAR_WIDTH% / 100"
    set /a "empty=%BAR_WIDTH% - !filled!"
    set "bar="
    for /L %%i in (1,1,!filled!) do set "bar=!bar!=" 
    for /L %%i in (1,1,!empty!) do set "bar=!bar!-"
    echo [!bar!] %%p%%
    timeout /t 0 /nobreak >nul 2>&1
)
call code\venv\Scripts\activate.bat

:: ── Step 3 : Preflight (60 → 80%) ──────────────────────────────────────────
echo Running preflight checks...
for /L %%p in (60,1,80) do (
    cls
    echo.
    echo    ============================================
    echo       EasyOKAPI - Launching...
    echo    ============================================
    echo.
    echo Running preflight checks...
    set /a "filled=%%p * %BAR_WIDTH% / 100"
    set /a "empty=%BAR_WIDTH% - !filled!"
    set "bar="
    for /L %%i in (1,1,!filled!) do set "bar=!bar!=" 
    for /L %%i in (1,1,!empty!) do set "bar=!bar!-"
    echo [!bar!] %%p%%
    timeout /t 0 /nobreak >nul 2>&1
)
if not exist "code\main.py" (
    cls
    echo.
    echo    [!] ERROR: main.py not found in code directory.
    echo.
    pause
    exit /b 1
)

:: ── Launch application (80 → 100%) ────────────────────────────────────────
echo Launching application...
for /L %%p in (80,1,100) do (
    cls
    echo.
    echo    ============================================
    echo       EasyOKAPI - Launching...
    echo    ============================================
    echo.
    echo Launching application...
    set /a "filled=%%p * %BAR_WIDTH% / 100"
    set /a "empty=%BAR_WIDTH% - !filled!"
    set "bar="
    for /L %%i in (1,1,!filled!) do set "bar=!bar!=" 
    for /L %%i in (1,1,!empty!) do set "bar=!bar!-"
    echo [!bar!] %%p%%
    timeout /t 0 /nobreak >nul 2>&1
)

:: Launch application in background and exit this window
start /b /min "" code\venv\Scripts\python.exe code\main.py
exit /b 0