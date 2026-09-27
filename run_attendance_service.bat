@echo off
echo Starting Attendance Model Service...
echo.

cd /d "%~dp0model_runner"

python model_service.py

echo.
echo Attendance service stopped.
echo.

pause