@echo off
setlocal enabledelayedexpansion

:: Set console window icon to ht.ico
set "_ICON_PS=%TEMP%\easyokapi_icon.ps1"
if exist "%_ICON_PS%" del "%_ICON_PS%"
echo Add-Type -AssemblyName System.Drawing >> "%_ICON_PS%"
echo Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l); [DllImport("user32.dll")] public static extern IntPtr SetClassLongPtr(IntPtr h, int n, IntPtr v); [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();' -Name ConsW -Namespace Prg >> "%_ICON_PS%"
echo $ico = New-Object System.Drawing.Icon('%~dp0static\ht.ico') >> "%_ICON_PS%"
echo $hwnd = [Prg.ConsW]::GetConsoleWindow() >> "%_ICON_PS%"
echo [Prg.ConsW]::SendMessage($hwnd, 0x80, [IntPtr]::Zero, $ico.Handle) >> "%_ICON_PS%"
echo [Prg.ConsW]::SendMessage($hwnd, 0x80, [IntPtr]1, $ico.Handle) >> "%_ICON_PS%"
echo [Prg.ConsW]::SetClassLongPtr($hwnd, -34, $ico.Handle) >> "%_ICON_PS%"
echo [Prg.ConsW]::SetClassLongPtr($hwnd, -14, $ico.Handle) >> "%_ICON_PS%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%_ICON_PS%" 2>nul
del "%_ICON_PS%" 2>nul

:: Ensure the script runs from its parent directory (project root)
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

:: Install Python dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements-win.txt
if %ERRORLEVEL% neq 0 (
    cls
    echo.
    echo    [!] ERROR: Failed to install dependencies.
    echo.
    pause
    exit /b 1
)

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

:: ── AI Assistant Setup (first run only) ─────────────────────────────────────
if not exist "ai_settings.json" (
    echo.
    echo    ============================================================
    echo       AI Assistant  (Optional Feature)
    echo    ============================================================
    echo    Answers your data questions in 6 languages:
    echo    English / Tieng Viet / Chinese / Francais / Japanese / Russian
    echo    Powered by Ollama (local LLM - no internet needed after setup)
    echo    ============================================================
    echo.
    set /p AI_CHOICE="   Install AI Assistant? [y/N]: "
    if /i "!AI_CHOICE!"=="y" (
        set "AI_ENABLED=true"

        echo.
        echo    Choose languages (enter numbers separated by spaces, e.g. 1 2^):
        echo      1) English    2) Tieng Viet   3) Chinese (Simplified)
        echo      4) Francais   5) Japanese     6) Russian
        echo.
        set /p LANG_NUMS="   Enter numbers [1-6, default=1]: "
        if not defined LANG_NUMS set "LANG_NUMS=1"
        set "AI_LANGS_LIST="
        for %%n in (!LANG_NUMS!) do (
            set "LLANG="
            if "%%n"=="1" set "LLANG=en"
            if "%%n"=="2" set "LLANG=vi"
            if "%%n"=="3" set "LLANG=zh"
            if "%%n"=="4" set "LLANG=fr"
            if "%%n"=="5" set "LLANG=ja"
            if "%%n"=="6" set "LLANG=ru"
            if defined LLANG (
                if "!AI_LANGS_LIST!"=="" ( set "AI_LANGS_LIST=!LLANG!" ) else ( set "AI_LANGS_LIST=!AI_LANGS_LIST!,!LLANG!" )
            )
        )
        if "!AI_LANGS_LIST!"=="" set "AI_LANGS_LIST=en"
        echo    Languages: !AI_LANGS_LIST!

        echo.
        echo    Choose AI model:
        echo      1) qwen2.5:7b  (4.7 GB) - Best multilingual  [recommended]
        echo      2) qwen2.5:3b  (1.9 GB) - Lighter, still multilingual
        echo      3) llama3.2:3b (2.0 GB) - Good English/French
        echo      4) mistral:7b  (4.1 GB) - Good European languages
        echo.
        set /p MODEL_NUM="   Enter number [1-4, default=1]: "
        if "!MODEL_NUM!"=="2" ( set "AI_MODEL=qwen2.5:3b"  & set "AI_MODEL_SIZE=1.9 GB" ) else ^
        if "!MODEL_NUM!"=="3" ( set "AI_MODEL=llama3.2:3b" & set "AI_MODEL_SIZE=2.0 GB" ) else ^
        if "!MODEL_NUM!"=="4" ( set "AI_MODEL=mistral:7b"  & set "AI_MODEL_SIZE=4.1 GB" ) else ^
        ( set "AI_MODEL=qwen2.5:7b" & set "AI_MODEL_SIZE=4.7 GB" )
        echo    Model: !AI_MODEL!

        :: Check Ollama and pull model
        echo.
        where ollama >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo    [OK] Ollama is installed.
            set /p PULL_CHOICE="   Download !AI_MODEL! now? (!AI_MODEL_SIZE!, may take several minutes) [Y/n]: "
            if not defined PULL_CHOICE set "PULL_CHOICE=y"
            if /i "!PULL_CHOICE!"=="n" (
                echo    Skipped. Download later from the robot button inside the app.
            ) else (
                echo    Ensuring Ollama is running...
                curl -sf http://localhost:11434/api/tags >nul 2>&1
                if !ERRORLEVEL! neq 0 (
                    echo    Starting Ollama...
                    start /min "" ollama serve
                    timeout /t 8 /nobreak >nul
                )
                echo    Downloading !AI_MODEL! ...
                ollama pull !AI_MODEL!
                echo    [OK] Model downloaded.
            )
        ) else (
            echo    [!] Ollama is not installed.
            set /p OLLAMA_INSTALL="   Install Ollama now? (requires internet) [y/N]: "
            if /i "!OLLAMA_INSTALL!"=="y" (
                echo    Installing Ollama via winget...
                winget install ollama.ollama
                if !ERRORLEVEL! equ 0 (
                    echo    [OK] Ollama installed.
                    set /p PULL_CHOICE="   Download !AI_MODEL! now? (!AI_MODEL_SIZE!, several minutes) [Y/n]: "
                    if not defined PULL_CHOICE set "PULL_CHOICE=y"
                    if /i "!PULL_CHOICE!"=="n" (
                        echo    Skipped. Download later from the robot button inside the app.
                    ) else (
                        echo    Ensuring Ollama is running...
                        curl -sf http://localhost:11434/api/tags >nul 2>&1
                        if !ERRORLEVEL! neq 0 (
                            echo    Starting Ollama...
                            start /min "" ollama serve
                            timeout /t 10 /nobreak >nul
                        )
                        echo    Downloading !AI_MODEL! ...
                        ollama pull !AI_MODEL!
                        echo    [OK] Model downloaded.
                    )
                ) else (
                    echo    [!] Ollama install failed.
                    echo        Install manually from: https://ollama.com/download
                )
            ) else (
                echo    Skipped. Install manually later from: https://ollama.com/download
            )
        )

    ) else (
        set "AI_ENABLED=false"
        set "AI_LANGS_LIST=en"
        set "AI_MODEL=qwen2.5:7b"
        echo    AI Assistant disabled. Enable it later from the robot button in the app.
    )

    :: Write ai_settings.json using Python (already in venv)
    if "!AI_ENABLED!"=="true" (
        python -c "import json; langs=list(dict.fromkeys('!AI_LANGS_LIST!'.split(','))); open('ai_settings.json','w').write(json.dumps({'enabled':True,'preferred_languages':langs,'model':'!AI_MODEL!','ollama_url':'http://localhost:11434','first_run_shown':False},indent=2))"
    ) else (
        python -c "import json; open('ai_settings.json','w').write(json.dumps({'enabled':False,'preferred_languages':['en'],'model':'qwen2.5:7b','ollama_url':'http://localhost:11434','first_run_shown':False},indent=2))"
    )
    echo    [OK] Saved: ai_settings.json
    echo.
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
start /b "" venv\Scripts\python.exe main.py %*