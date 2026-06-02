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

REM Locate the pyenv Python by checking known version paths directly.
REM Avoids "pyenv which python" which can capture error messages (e.g. "pyenv local 3.7.4")
REM instead of a real path when a .python-version file specifies an uninstalled version.
set "PYENV_VERSIONS=%PYENV_PATH%\versions"
set "PYENV_PYTHON="
if exist "%PYENV_VERSIONS%\3.8.10\python.exe" set "PYENV_PYTHON=%PYENV_VERSIONS%\3.8.10\python.exe"
if not defined PYENV_PYTHON (
    if exist "%PYENV_VERSIONS%\3.9.13\python.exe" set "PYENV_PYTHON=%PYENV_VERSIONS%\3.9.13\python.exe"
)
if not defined PYENV_PYTHON (
    echo Python 3.8.10 and 3.9.13 not found in pyenv versions.
    echo Downloading official Python 3.8.10 installer...
    set "PY_INSTALLER=%TEMP%\python-3.8.10-amd64.exe"
    set "PY_URL_64=https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe"
    set "PY_URL_32=https://www.python.org/ftp/python/3.8.10/python-3.8.10.exe"
    set "PY_INSTALL_DIR=%PYENV_VERSIONS%\3.8.10"

    :: Detect architecture
    wmic OS get OSArchitecture | findstr /C:"64-bit" >nul
    if !ERRORLEVEL! equ 0 (
        curl -L -o "!PY_INSTALLER!" "!PY_URL_64!"
    ) else (
        curl -L -o "!PY_INSTALLER!" "!PY_URL_32!"
    )
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Failed to download Python 3.8.10 installer.
        exit /b 1
    )

    :: Install into pyenv versions directory so both pyenv and direct-path lookups find it
    start /wait "" "!PY_INSTALLER!" /quiet InstallAllUsers=0 TargetDir="!PY_INSTALL_DIR!" ^
        Include_pip=1 Include_launcher=0 Include_test=0 Include_doc=0
    del "!PY_INSTALLER!" 2>nul

    if exist "%PYENV_VERSIONS%\3.8.10\python.exe" (
        set "PYENV_PYTHON=%PYENV_VERSIONS%\3.8.10\python.exe"
    ) else (
        echo ERROR: Python 3.8.10 installation failed. Check installer logs.
        exit /b 1
    )
)
echo Using Python: %PYENV_PYTHON%

REM Use 8.3 short path to avoid spaces in "Program Files" breaking subprocess calls
set "VENV_DIR=%~sdp0code\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

REM A running EasyOKAPI instance keeps venv\Scripts\python.exe and its DLLs
REM locked, so the rmdir/create below fails with [Errno 13] / [WinError 5] and a
REM broken app ships. EasyOKAPI runs elevated, so we CANNOT force-kill it from
REM here (Stop-Process is denied by the system). Instead, if the venv python is
REM present and still locked, bail with a distinct exit code (2) so the installer
REM can ask the user to shut EasyOKAPI down and retry this step. A short poll
REM absorbs the brief window after a just-issued shutdown before the handle frees.
echo Checking the virtual environment is not locked by a running instance...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%VENV_PYTHON%'; $deadline=(Get-Date).AddSeconds(5); while ($true) { if (-not (Test-Path -LiteralPath $p)) { exit 0 }; try { $fs=[System.IO.File]::Open($p,'Open','ReadWrite','None'); $fs.Close(); exit 0 } catch { if ((Get-Date) -ge $deadline) { exit 2 }; Start-Sleep -Milliseconds 300 } }"
if "%ERRORLEVEL%"=="2" (
    echo ERROR: EasyOKAPI is still running and is locking its virtual environment.
    echo Please shut EasyOKAPI down ^(open http://localhost:5099 and click "Shutdown Program"^), then run Setup again.
    exit /b 2
)

REM Recreate the venv if python.exe is missing OR the venv is broken.
REM Checking only python.exe (the old behaviour) let a HALF-BUILT venv survive a
REM reinstall: an aborted run - or antivirus quarantining pyvenv.cfg/pythonw.exe -
REM leaves python.exe behind without pyvenv.cfg, so the venv python exits instantly
REM with "No pyvenv.cfg file" and the app silently never launches. pyvenv.cfg is the
REM reliable health marker, so treat its absence as "rebuild from scratch".
REM --without-pip avoids the internal ensurepip subprocess that fails on paths with spaces;
REM pip is bootstrapped separately below via "%VENV_PYTHON%" -m ensurepip.
set "VENV_BROKEN="
if not exist "%VENV_PYTHON%" set "VENV_BROKEN=1"
if not exist "%VENV_DIR%\pyvenv.cfg" set "VENV_BROKEN=1"
if defined VENV_BROKEN (
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
    echo Creating virtual environment...
    "%PYENV_PYTHON%" -m venv --without-pip "%VENV_DIR%"
    if not exist "%VENV_PYTHON%" (
        echo ERROR: Failed to create virtual environment at %VENV_DIR%.
        exit /b 1
    )
    if not exist "%VENV_DIR%\pyvenv.cfg" (
        echo ERROR: virtual environment created without pyvenv.cfg at %VENV_DIR%.
        exit /b 1
    )
    echo Created virtual environment in 'code\venv'.
)

call "%VENV_DIR%\Scripts\activate.bat"
echo Virtual environment activated.

REM Ensure pip is installed
echo Checking pip...
"%VENV_PYTHON%" -m ensurepip --upgrade
if errorlevel 1 (
    echo ERROR: Failed to bootstrap pip into the virtual environment.
    exit /b 1
)

REM Install required libraries. Each step's exit code MUST be checked: an
REM unchecked pip failure (network blip, AV, a wheel that won't build) used to
REM leave a partial venv - e.g. flask/pandas/requests/groq missing - while the
REM installer still reported success and shipped a broken app.
echo Installing requirements...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    exit /b 1
)
"%VENV_PYTHON%" -m pip install -r "%~dp0code\requirements-win.txt"
if errorlevel 1 (
    echo ERROR: Failed to install required packages from requirements-win.txt.
    exit /b 1
)

REM Verify the core imports actually work so a partial install can never ship.
echo Verifying environment...
"%VENV_PYTHON%" -c "import flask, pandas, requests, scipy, groq"
if errorlevel 1 (
    echo ERROR: Environment verification failed - core packages are missing.
    exit /b 1
)
echo Environment verified.

REM Pre-compile bytecode for scipy/numpy so first app launch is not slow
echo Pre-compiling Python bytecode for scientific libraries...
"%VENV_PYTHON%" -m compileall -q "code\venv\Lib\site-packages\scipy" "code\venv\Lib\site-packages\numpy" 2>nul
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
