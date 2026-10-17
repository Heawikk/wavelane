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

setlocal EnableDelayedExpansion

REM Keep the full argument list before shifting through it below.
set "ARGS=%*"

set "PYTHON=E:\Wavelane\.venv\Scripts\python.exe"
set "HOST=127.0.0.1"
set "PORT=8000"

REM Read --host/--port so the checks below talk about the address really used.
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--port" set "PORT=%~2"
if /i "%~1"=="--host" set "HOST=%~2"
shift
goto parse_args
:args_done

if not exist "%PYTHON%" (
  echo.
  echo   The virtual environment is missing:
  echo     %PYTHON%
  echo.
  echo   Create it and install the server with:
  echo     python -m venv E:\Wavelane\.venv
  echo     E:\Wavelane\.venv\Scripts\python.exe -m pip install -e E:\Wavelane\server[dev]
  echo.
  goto failed
)

REM A port already in use is by far the most common reason this will not start,
REM usually another copy of the server left running. Say so plainly instead of
REM letting uvicorn's socket error flash past as the window closes.
netstat -ano | findstr /c:"LISTENING" | findstr /c:":%PORT% " >nul 2>&1
if not errorlevel 1 (
  echo.
  echo   Port %PORT% is already in use - a Wavelane server is probably
  echo   already running. Processes holding it:
  echo.
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:"LISTENING" ^| findstr /c:":%PORT% "') do (
    for /f "tokens=1,2 delims=," %%A in ('tasklist /fi "PID eq %%P" /fo csv /nh 2^>nul') do (
      echo       PID %%P   %%~A
    )
  )
  echo.
  echo   Either use that one - http://%HOST%:%PORT%/docs - or stop it:
  echo       taskkill /F /PID ^<pid^>
  echo   or start this one on another port:
  echo       run-server.bat --port 8001
  echo.
  goto failed
)

cd /d E:\Wavelane\server
if errorlevel 1 (
  echo   Could not enter E:\Wavelane\server
  goto failed
)

if not exist ".env" (
  echo   No .env found - copying .env.example.
  echo   Set WAVELANE_SECRET_KEY in it before exposing this server.
  copy .env.example .env >nul
)

echo.
echo   Wavelane server   http://%HOST%:%PORT%
echo   API docs          http://%HOST%:%PORT%/docs
echo   Stop with Ctrl+C
echo.

REM %ARGS% comes last so anything you pass overrides these defaults.
"%PYTHON%" -m uvicorn wavelane.main:app --host %HOST% --port %PORT% %ARGS%
set "RESULT=%ERRORLEVEL%"

REM Ctrl+C leaves 0 or 2 depending on timing; neither is a failure worth a prompt.
if "%RESULT%"=="0" goto done
if "%RESULT%"=="2" goto done

echo.
echo   The server stopped with exit code %RESULT%. The error is above.
goto failed

:failed
REM Without this the window vanishes before the message can be read, which is
REM exactly what makes a failure look like "nothing happened".
echo   Press any key to close this window.
pause >nul
endlocal
exit /b 1

:done
endlocal
exit /b 0
