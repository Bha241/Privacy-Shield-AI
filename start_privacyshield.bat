@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
echo Starting PrivacyShieldAI backend and frontend...

start "PrivacyShieldAI Backend" /D "%PROJECT_ROOT%backend" cmd /k "call run_backend_guarded.cmd"
start "PrivacyShieldAI Frontend" /D "%PROJECT_ROOT%frontend" cmd /k "npm.cmd run dev"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:3000
echo.
echo Two CMD windows were opened. Keep them running while using the app.

endlocal
