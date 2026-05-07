@echo off
setlocal enabledelayedexpansion
:: Ensure the script runs from its own directory
cd /d "%~dp0"
echo ===============================================
echo  Welcome to the Easy Sensor Web Interface Setup
echo ===============================================
echo.
echo This script assumes Git and Python are already installed with pyenv.
echo It will set up a virtual environment and install required libraries.
echo If you haven't installed Git and Python yet, please run startwindow-1-git.bat first. 
echo.
echo If you see errors about permissions or installation, please:
echo   1. Close this window.
echo   2. Right-click startwindow.bat and select "Run as administrator".
echo.

REM Note: This script does not exit on every error automatically.
REM Each critical step checks for errors and exits if needed.

REM Check if Python 3.8.10 or 3.9.13 is installed via pyenv
:: Purpose: Check for Python 3.8.10, install if not found, else check/install Python 3.9.13
:: Initialize variables

REM Get the path to the pyenv Python
for /f "delims=" %%i in ('pyenv which python') do set PYENV_PYTHON=%%i
if not defined PYENV_PYTHON (
    echo ERROR: pyenv which python did not return a path. Check pyenv installation and local version.
    pyenv versions
    pyenv which python
    pause
    exit /b 1
)
echo Using Python: %PYENV_PYTHON%

REM Create venv if not exists
if not exist "code\venv" (
    "%PYENV_PYTHON%" -m venv code\venv
    echo Created virtual environment in 'code\venv'.
)

call code\venv\Scripts\activate.bat
echo Virtual environment activated.

REM Ensure pip is installed
echo Checking pip...
python -m ensurepip --upgrade

REM Install required libraries
echo Installing requirements...
pip install --upgrade pip
pip install -r "%~dp0code\requirements-win.txt"

REM Pre-compile bytecode for scipy/numpy so first app launch is not slow
echo Pre-compiling Python bytecode for scientific libraries...
python -m compileall -q "code\venv\Lib\site-packages\scipy" "code\venv\Lib\site-packages\numpy" 2>nul
echo Bytecode pre-compilation complete.

REM Download front-end vendor libraries
echo Downloading front-end vendor libraries...
set "VENDOR_DIR=%~dp0code\static\vendor"
set "FONT_DIR=%VENDOR_DIR%\mathjax-fonts"
if not exist "%VENDOR_DIR%" mkdir "%VENDOR_DIR%"
if not exist "%FONT_DIR%" mkdir "%FONT_DIR%"

curl -fsSL "https://code.jquery.com/jquery-3.6.0.min.js" -o "%VENDOR_DIR%\jquery-3.6.0.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download jquery. & pause & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" -o "%VENDOR_DIR%\chart.umd.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download chart.js. & pause & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js" -o "%VENDOR_DIR%\chartjs-plugin-annotation-2.0.0.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download chartjs-plugin-annotation. & pause & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js" -o "%VENDOR_DIR%\sweetalert2.all.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download sweetalert2. & pause & exit /b 1 )
curl -fsSL "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js" -o "%VENDOR_DIR%\numeric-1.2.6.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download numeric.js. & pause & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" -o "%VENDOR_DIR%\mathjax-tex-mml-chtml.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download mathjax. & pause & exit /b 1 )

for %%F in (MathJax_AMS-Regular MathJax_Main-Regular MathJax_Main-Bold MathJax_Main-Italic MathJax_Math-Regular MathJax_Math-Italic MathJax_Math-BoldItalic MathJax_Size1-Regular MathJax_Size2-Regular MathJax_Size3-Regular MathJax_Size4-Regular MathJax_Calligraphic-Regular MathJax_Calligraphic-Bold MathJax_Fraktur-Regular MathJax_Fraktur-Bold MathJax_SansSerif-Regular MathJax_SansSerif-Bold MathJax_SansSerif-Italic MathJax_Script-Regular MathJax_Typewriter-Regular MathJax_Vector-Regular MathJax_Vector-Bold MathJax_Zero) do (
    curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/%%F.woff" -o "%FONT_DIR%\%%F.woff"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download %%F.woff & pause & exit /b 1 )
)
echo Vendor libraries downloaded successfully.

:: ── AI Assistant Setup (first run only) ─────────────────────────────────────
if not exist "code\ai_settings.json" (
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
                    timeout /t 8 /nobreak >nul
                )
                echo    Downloading !AI_MODEL! ...
                ollama pull !AI_MODEL!
                echo    [OK] Model downloaded.
            )
        ) else (
            echo    [!] Ollama is not installed.
            echo        Install from: https://ollama.com/download
            echo        Then download the model from inside the app.
        )

    ) else (
        set "AI_ENABLED=false"
        set "AI_LANGS_LIST=en"
        set "AI_MODEL=qwen2.5:7b"
        echo    AI Assistant disabled. Enable later from the robot button in the app.
    )

    :: Write ai_settings.json using Python (in venv)
    if "!AI_ENABLED!"=="true" (
        code\venv\Scripts\python.exe -c "import json; langs=list(dict.fromkeys('!AI_LANGS_LIST!'.split(','))); open('code/ai_settings.json','w').write(json.dumps({'enabled':True,'preferred_languages':langs,'model':'!AI_MODEL!','ollama_url':'http://localhost:11434','first_run_shown':False},indent=2))"
    ) else (
        code\venv\Scripts\python.exe -c "import json; open('code/ai_settings.json','w').write(json.dumps({'enabled':False,'preferred_languages':['en'],'model':'qwen2.5:7b','ollama_url':'http://localhost:11434','first_run_shown':False},indent=2))"
    )
    echo    [OK] Saved: code\ai_settings.json
    echo.
)

echo Virtual environment setup complete.
echo Press any key to continue...
pause > nul
