@echo off
echo Starting Docker Desktop...
echo.

start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo Waiting for Docker to be ready...
echo This may take a minute...
echo.

:waitDocker
docker info >nul 2>&1

if errorlevel 1 (
    timeout /t 5 >nul
    goto waitDocker
)

echo Docker is ready.
echo.
echo Starting Smart Attendance Web System...
echo.

cd /d "%~dp0web_app"

docker compose up --build -d

echo.
echo Web system is running.
echo Open this link in your browser:
echo http://localhost:5000
echo.

pause