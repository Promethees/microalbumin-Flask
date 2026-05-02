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

:: Download vendor libraries if not present
if not exist "static\vendor\" (
    echo Downloading front-end vendor libraries...
    set "VENDOR_DIR=%~dp0static\vendor"
    set "FONT_DIR=!VENDOR_DIR!\mathjax-fonts"
    mkdir "!VENDOR_DIR!"
    mkdir "!FONT_DIR!"

    curl -fsSL "https://code.jquery.com/jquery-3.6.0.min.js" -o "!VENDOR_DIR!\jquery-3.6.0.min.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download jquery. & pause & exit /b 1 )
    curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" -o "!VENDOR_DIR!\chart.umd.min.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download chart.js. & pause & exit /b 1 )
    curl -fsSL "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js" -o "!VENDOR_DIR!\chartjs-plugin-annotation-2.0.0.min.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download chartjs-plugin-annotation. & pause & exit /b 1 )
    curl -fsSL "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js" -o "!VENDOR_DIR!\sweetalert2.all.min.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download sweetalert2. & pause & exit /b 1 )
    curl -fsSL "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js" -o "!VENDOR_DIR!\numeric-1.2.6.min.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download numeric.js. & pause & exit /b 1 )
    curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" -o "!VENDOR_DIR!\mathjax-tex-mml-chtml.js"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download mathjax. & pause & exit /b 1 )

    for %%F in (MathJax_AMS-Regular MathJax_Main-Regular MathJax_Main-Bold MathJax_Main-Italic MathJax_Math-Italic MathJax_Math-BoldItalic MathJax_Size1-Regular MathJax_Size2-Regular MathJax_Size3-Regular MathJax_Size4-Regular MathJax_Calligraphic-Regular MathJax_Calligraphic-Bold MathJax_Fraktur-Regular MathJax_Fraktur-Bold MathJax_SansSerif-Regular MathJax_SansSerif-Bold MathJax_SansSerif-Italic MathJax_Script-Regular MathJax_Typewriter-Regular MathJax_Vector-Regular MathJax_Vector-Bold MathJax_Zero) do (
        curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/%%F.woff" -o "!FONT_DIR!\%%F.woff"
        if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download %%F.woff & pause & exit /b 1 )
    )
    echo Vendor libraries downloaded successfully.
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