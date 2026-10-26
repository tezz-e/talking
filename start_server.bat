@echo off
echo ============================================================
echo   TALKING -- PROOF DESK BACKEND SERVER
echo   http://127.0.0.1:8000
echo ============================================================
if exist ".\venv\Scripts\python.exe" (
    .\venv\Scripts\python.exe run.py
) else if exist "D:\Talking\venv\Scripts\python.exe" (
    D:\Talking\venv\Scripts\python.exe run.py
) else (
    python run.py
)
pause
