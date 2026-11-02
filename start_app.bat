@echo off
title Angaza Rentals Management System
echo ============================================================
echo   Starting Angaza Rentals Management System...
echo ============================================================

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

REM Run initialization to ensure DB exists
python init_db.py

REM Start application
echo Starting web server at http://127.0.0.1:5000 ...
python run.py

pause

