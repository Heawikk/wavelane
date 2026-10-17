@echo off
REM Start the Wavelane desktop client.
REM
REM   run-client.bat                      - open the app
REM   run-client.bat --wave               - start playing the wave straight away
REM   run-client.bat --server http://host:8000   - connect elsewhere
REM
REM Writes a log to %LOCALAPPDATA%\Wavelane\client.log, because a Windows GUI
REM build has no console for warnings to go to.

setlocal

set "EXE=E:\Wavelane\client\build\wavelane.exe"

if not exist "%EXE%" (
  echo.
  echo   The client is not built yet:
  echo     %EXE%
  echo.
  echo   Build it with:
  echo     E:\Wavelane\client\build.bat Release
  echo.
  goto failed
)

if not exist "%EXE%\..\Qt6Core.dll" (
  if not exist "E:\Wavelane\client\build\Qt6Core.dll" (
    echo.
    echo   The Qt libraries are not next to the executable, so it cannot start.
    echo   Deploy them once with:
    echo     tools\Qt\6.8.3\msvc2022_64\bin\windeployqt.exe --qmldir client\qml "%EXE%"
    echo.
    goto failed
  )
)

if not exist "%LOCALAPPDATA%\Wavelane" mkdir "%LOCALAPPDATA%\Wavelane"
set "WAVELANE_LOG_FILE=%LOCALAPPDATA%\Wavelane\client.log"

REM Not fatal - the app can still open so the server address can be corrected
REM on the sign-in page - but it is the usual reason nothing loads.
netstat -ano | findstr /c:"LISTENING" | findstr /c:":8000 " >nul 2>&1
if errorlevel 1 (
  echo   Note: nothing is listening on port 8000. Start the server first with
  echo   run-server.bat, or pass --server with the right address.
)

start "" "%EXE%" %*
endlocal
exit /b 0

:failed
echo   Press any key to close this window.
pause >nul
endlocal
exit /b 1
