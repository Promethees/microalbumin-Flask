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

REM Đảm bảo pip đã được cài
echo Checking pip...
python -m ensurepip --upgrade

REM Cài đặt thư viện cần thiết
echo Installing requirements...
pip install --upgrade pip
pip install -r requirements.txt

REM Cài Flask nếu chưa có
python -m pip install flask

REM Cài pandas nếu chưa có
python -m pip install pandas

REM Chạy thử
echo Starting app...
python main.py

