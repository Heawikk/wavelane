@echo off
REM Start the Wavelane server.
REM
REM   run-server.bat              - localhost only, port 8000
REM   run-server.bat --reload     - restart automatically when code changes
REM   run-server.bat --port 9000  - a different port
REM   run-server.bat --host 0.0.0.0   - reachable from other devices on the LAN
REM
REM Any uvicorn option can be passed through; the defaults below are used for
REM whatever you do not override.

setlocal
set PYTHON=E:\Wavelane\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
  echo The virtual environment is missing: %PYTHON%
  echo Create it with:  python -m venv E:\Wavelane\.venv
  exit /b 1
)

cd /d E:\Wavelane\server

if not exist ".env" (
  echo No .env found - copying .env.example.
  echo Remember to set WAVELANE_SECRET_KEY before exposing this server.
  copy .env.example .env >nul
)

REM %* lets you override any of these, since uvicorn takes the last value given.
"%PYTHON%" -m uvicorn wavelane.main:app --host 127.0.0.1 --port 8000 %*

endlocal
