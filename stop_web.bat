@echo off
echo Stopping Smart Attendance Web System...
echo.

cd /d "%~dp0web_app"

echo Stopping Docker containers...
docker compose down

echo.
echo Closing Docker Desktop...
taskkill /IM "Docker Desktop.exe" /F >nul 2>&1

echo.
echo Web system and Docker Desktop stopped.
echo.

pause