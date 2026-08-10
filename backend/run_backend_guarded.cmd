@echo off
setlocal

set "BACKEND_ROOT=%~dp0"
set "PYTHON_EXE=C:\Users\vighn\AppData\Local\Python\pythoncore-3.12-64\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

rem Do not start a second backend if port 8000 is already owned.
netstat -ano | findstr /C:"127.0.0.1:8000" | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo PrivacyShieldAI backend is already listening on http://127.0.0.1:8000.
  echo This launcher will exit without starting a duplicate process.
  exit /b 0
)

:run_backend
echo Starting PrivacyShieldAI backend on http://127.0.0.1:8000 ...
pushd "%BACKEND_ROOT%"
"%PYTHON_EXE%" run_backend.py
set "EXIT_CODE=%ERRORLEVEL%"
popd

if "%EXIT_CODE%"=="0" (
  echo Backend stopped normally with exit code 0.
  echo Press any key to close this backend window.
  pause >nul
  exit /b 0
)

if "%EXIT_CODE%"=="3" (
  echo Backend could not bind port 8000 because another process owns it.
  echo Stop the existing backend or use that running instance; this launcher will not retry.
  exit /b 3
)

echo Backend exited unexpectedly with code %EXIT_CODE%.
echo It will restart in 3 seconds. Review the traceback above if present.
timeout /t 3 /nobreak >nul
goto run_backend
