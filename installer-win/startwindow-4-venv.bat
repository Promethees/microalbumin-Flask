@echo off
setlocal enabledelayedexpansion
:: Ensure the script runs from its own directory
cd /d "%~dp0"

set "PYENV_PATH=%USERPROFILE%\.pyenv\pyenv-win\pyenv-win"
set "BIN_PATH=%PYENV_PATH%\bin"

echo ===============================================
echo  Welcome to the Easy Sensor Web Interface Setup
echo ===============================================
echo.
echo This script assumes Git and Python are already installed with pyenv.
echo It will set up a virtual environment and install required libraries.
echo.

REM Get the path to the pyenv Python
for /f "delims=" %%i in ('"%BIN_PATH%\pyenv" which python') do set PYENV_PYTHON=%%i
if not defined PYENV_PYTHON (
    echo ERROR: pyenv which python did not return a path. Check pyenv installation and local version.
    "%BIN_PATH%\pyenv" versions
    "%BIN_PATH%\pyenv" which python
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
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download jquery. & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js" -o "%VENDOR_DIR%\chart.umd.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download chart.js. & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.0.0/dist/chartjs-plugin-annotation.min.js" -o "%VENDOR_DIR%\chartjs-plugin-annotation-2.0.0.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download chartjs-plugin-annotation. & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/sweetalert2@11/dist/sweetalert2.all.min.js" -o "%VENDOR_DIR%\sweetalert2.all.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download sweetalert2. & exit /b 1 )
curl -fsSL "https://cdnjs.cloudflare.com/ajax/libs/numeric/1.2.6/numeric.min.js" -o "%VENDOR_DIR%\numeric-1.2.6.min.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download numeric.js. & exit /b 1 )
curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" -o "%VENDOR_DIR%\mathjax-tex-mml-chtml.js"
if %ERRORLEVEL% neq 0 ( echo ERROR: Failed to download mathjax. & exit /b 1 )

for %%F in (MathJax_AMS-Regular MathJax_Main-Regular MathJax_Main-Bold MathJax_Main-Italic MathJax_Math-Regular MathJax_Math-Italic MathJax_Math-BoldItalic MathJax_Size1-Regular MathJax_Size2-Regular MathJax_Size3-Regular MathJax_Size4-Regular MathJax_Calligraphic-Regular MathJax_Calligraphic-Bold MathJax_Fraktur-Regular MathJax_Fraktur-Bold MathJax_SansSerif-Regular MathJax_SansSerif-Bold MathJax_SansSerif-Italic MathJax_Script-Regular MathJax_Typewriter-Regular MathJax_Vector-Regular MathJax_Vector-Bold MathJax_Zero) do (
    curl -fsSL "https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2/%%F.woff" -o "%FONT_DIR%\%%F.woff"
    if !ERRORLEVEL! neq 0 ( echo ERROR: Failed to download %%F.woff & exit /b 1 )
)
echo Vendor libraries downloaded successfully.

echo Virtual environment setup complete.
