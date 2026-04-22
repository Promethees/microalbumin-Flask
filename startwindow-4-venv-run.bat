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

:: Get the path to the pyenv Python
for /f "delims=" %%i in ('pyenv which python') do set PYENV_PYTHON=%%i
if not defined PYENV_PYTHON (
    cls
    echo.
    echo    [!] ERROR: pyenv Python not found.
    echo.
    pause
    exit /b 1
)

:: ── Step 2 : Virtual Environment (30 → 60%) ────────────────────────────────
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
if not exist "venv" (
    "%PYENV_PYTHON%" -m venv venv
)
call venv\Scripts\activate.bat

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
if not exist "main.py" (
    cls
    echo.
    echo    [!] ERROR: main.py not found.
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
start /b "" venv\Scripts\python.exe main.py