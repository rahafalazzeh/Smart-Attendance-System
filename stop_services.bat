@echo off
echo Stopping project services...
echo.

echo Closing Attendance Service if running...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'model_service.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo Closing Face Registration Service if running...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'face_registration_service.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo.
echo Done. Running model services have been stopped.
echo.

pause