@echo off
setlocal enabledelayedexpansion

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
%DRAW_PROGRESS% 0 "Initialising environment ..."
for /L %%p in (0,1,15) do ( %DRAW_PROGRESS% %%p "Initialising environment ..." & timeout /t 0 /nobreak >nul )

:: Check if virtual environment exists
if not exist "code\venv\Scripts\python.exe" (
    echo.
    echo    [!] ERROR: Virtual environment not found in code\venv.
    pause
    exit /b 1
)
for /L %%p in (15,1,30) do ( %DRAW_PROGRESS% %%p "Initialising environment ..." & timeout /t 0 /nobreak >nul )

:: ── Step 2 : Activate (30 → 60%) ───────────────────────────────────────────
for /L %%p in (30,1,45) do ( %DRAW_PROGRESS% %%p "Activating virtual environment ..." & timeout /t 0 /nobreak >nul )
call code\venv\Scripts\activate.bat
for /L %%p in (45,1,60) do ( %DRAW_PROGRESS% %%p "Activating virtual environment ..." & timeout /t 0 /nobreak >nul )

:: ── Step 3 : Preflight (60 → 70%) ──────────────────────────────────────────
for /L %%p in (60,1,70) do ( %DRAW_PROGRESS% %%p "Running preflight checks ..." & timeout /t 0 /nobreak >nul )
if not exist "code\main.py" (
    echo.
    echo    [!] ERROR: main.py not found in code directory.
    pause
    exit /b 1
)

:: ── Launch application and Poll Progress (70 → 100%) ───────────────────────
start /b "" code\venv\Scripts\python.exe code\main.py > nul 2>&1

:poll
if not exist "%PROGRESS_FILE%" (
    timeout /t 1 /nobreak >nul
    goto poll
)

set /a "last_pct=-1"
:loop
for /f "usebackq tokens=1*" %%a in ("%PROGRESS_FILE%") do (
    set "raw_pct=%%a"
    set "label=%%b"
    set /a "pct=raw_pct"
    :: Map Python 0-100 -> display 70-100
    set /a "mapped=70 + (pct * 30 / 100)"
    if !mapped! gtr 100 set mapped=100
    
    if !mapped! neq !last_pct! (
        %DRAW_PROGRESS% !mapped! "!label!"
        set /a "last_pct=mapped"
    )
    if !pct! geq 100 goto done
)
timeout /t 0 /nobreak >nul
goto loop

:done
%DRAW_PROGRESS% 100 "Server ready!         "
echo.
echo.
echo    [OK] EasyOKAPI is running - opening browser...
echo.
if exist "%PROGRESS_FILE%" del "%PROGRESS_FILE%"
pause