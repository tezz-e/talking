@echo off
echo Starting Talking backend server...

IF NOT EXIST "venv\Scripts\python.exe" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    echo Installing requirements...
    .\venv\Scripts\pip install -r requirements.txt
)

.\venv\Scripts\python.exe run.py
pause
