@echo off
chcp 65001 >nul
set VIRTUAL_ENV=
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" English.py %*
) else (
    py English.py %*
)
if %errorlevel% neq 0 pause
