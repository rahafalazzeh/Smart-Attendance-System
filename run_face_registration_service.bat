@echo off
echo Starting Face Registration Service...
echo.

cd /d "%~dp0model_runner"

python face_registration_service.py

echo.
echo Face registration service stopped.
echo.

pause