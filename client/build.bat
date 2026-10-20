@echo off
REM Configure and build the Wavelane client.
REM Everything is pinned to the toolchain installed under E:\Wavelane\tools,
REM so the build does not depend on what happens to be on PATH.

setlocal
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo Could not initialise the MSVC environment.
  exit /b 1
)

set QT_DIR=E:\Wavelane\tools\Qt\6.8.3\msvc2022_64
set CMAKE=E:\Wavelane\.venv\Scripts\cmake.exe
set NINJA=E:\Wavelane\.venv\Scripts\ninja.exe
if not defined BUILD_DIR set BUILD_DIR=E:\Wavelane\client\build
set BUILD_TYPE=%1
if "%BUILD_TYPE%"=="" set BUILD_TYPE=Release

"%CMAKE%" -S E:\Wavelane\client -B "%BUILD_DIR%" -G Ninja ^
  -DCMAKE_BUILD_TYPE=%BUILD_TYPE% ^
  -DCMAKE_PREFIX_PATH="%QT_DIR%" ^
  -DCMAKE_MAKE_PROGRAM="%NINJA%"
if errorlevel 1 exit /b 1

"%CMAKE%" --build "%BUILD_DIR%" --parallel
if errorlevel 1 exit /b 1

echo.
echo Built: %BUILD_DIR%\wavelane.exe
endlocal
