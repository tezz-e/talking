@echo off
cd /d "%~dp0"
echo ============================================================
echo   TALKING -- PROOF DESK BACKEND SERVER
echo   http://127.0.0.1:8000
echo ============================================================
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" run.py
) else if exist ".\venv\Scripts\python.exe" (
    .\venv\Scripts\python.exe run.py
) else (
    python run.py
)
pause
