@echo off
title Codex
echo.
echo  =========================================
echo    Codex - Starting up...
echo  =========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python from https://python.org
    pause
    exit /b
)

:: Install all dependencies from requirements.txt
echo  Checking and installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo  Starting server...
echo  Open your browser at: http://localhost:5050
echo.
start "" "http://localhost:5050"
python app.py

pause
