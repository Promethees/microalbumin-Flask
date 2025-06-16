@echo off

REM Check Python version
for /f "tokens=2 delims= " %%a in ('python --version') do set PY_VER=%%a
if not "%PY_VER%"=="3.7.2" (
    echo ❌ Python 3.7.2 is required. Current version: %PY_VER%
    exit /b 1
)

REM Create venv if not exists
if not exist "venv" (
    python -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Run the app (no sudo in Windows)
echo ✅ Starting Flask app...
python main.py --port 5000
