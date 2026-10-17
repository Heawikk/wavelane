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
set EXE=E:\Wavelane\client\build\wavelane.exe

if not exist "%EXE%" (
  echo The client is not built yet: %EXE%
  echo Build it with:  E:\Wavelane\client\build.bat Release
  exit /b 1
)

if not exist "%LOCALAPPDATA%\Wavelane" mkdir "%LOCALAPPDATA%\Wavelane"
set WAVELANE_LOG_FILE=%LOCALAPPDATA%\Wavelane\client.log

start "" "%EXE%" %*

endlocal
