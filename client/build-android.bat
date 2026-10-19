@echo off
REM Build the Android app, sign it and (with "install") put it on the connected phone.
REM
REM   build-android.bat            - builds dist\Wavelane-android.apk
REM   build-android.bat install   - ...and installs it over adb
REM
REM Everything is pinned to the toolchain under E:\Wavelane\tools, as build.bat is:
REM Qt 6.8.3 for Android (arm64), NDK r26b, JDK 17, Android SDK 34.
REM The signing key is E:\Wavelane\tools\android\wavelane.keystore; keep a copy of it, since an
REM update can only be installed over an app signed with the same key.

setlocal
set TOOLS=E:\Wavelane\tools
set JAVA_HOME=%TOOLS%\jdk-17.0.20.1+1
set GRADLE_USER_HOME=%TOOLS%\gradle-home
set ANDROID_SDK_ROOT=%TOOLS%\android\sdk
set ANDROID_HOME=%ANDROID_SDK_ROOT%
set ANDROID_NDK_ROOT=%TOOLS%\android\sdk\ndk\26.1.10909125
set BUILD_DIR=E:\Wavelane\client\build-android
set QT_ANDROID=%TOOLS%\Qt\6.8.3\android_arm64_v8a
set QT_HOST=%TOOLS%\Qt\6.8.3\msvc2022_64
set BUILD_TOOLS=%ANDROID_SDK_ROOT%\build-tools\34.0.0
set PATH=%JAVA_HOME%\bin;E:\Wavelane\.venv\Scripts;%PATH%
set OUT=E:\Wavelane\dist\Wavelane-android.apk

REM A Gradle daemon left from the last build still holds the dex file open.
if exist "%BUILD_DIR%\android-build\gradlew.bat" call "%BUILD_DIR%\android-build\gradlew.bat" --stop >nul 2>&1

call "%QT_ANDROID%\bin\qt-cmake.bat" -S E:\Wavelane\client -B "%BUILD_DIR%" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="%QT_HOST%" ^
  -DANDROID_SDK_ROOT="%ANDROID_SDK_ROOT%" -DANDROID_NDK_ROOT="%ANDROID_NDK_ROOT%" ^
  -DCMAKE_MAKE_PROGRAM=E:\Wavelane\.venv\Scripts\ninja.exe
if errorlevel 1 exit /b 1

E:\Wavelane\.venv\Scripts\cmake.exe --build "%BUILD_DIR%" --target apk
if errorlevel 1 exit /b 1

if not exist E:\Wavelane\dist mkdir E:\Wavelane\dist
set UNSIGNED=%BUILD_DIR%\android-build\build\outputs\apk\release\android-build-release-unsigned.apk
call "%BUILD_TOOLS%\zipalign.exe" -p -f 4 "%UNSIGNED%" "%BUILD_DIR%\aligned.apk"
if errorlevel 1 exit /b 1
call "%BUILD_TOOLS%\apksigner.bat" sign --ks "%TOOLS%\android\wavelane.keystore" ^
  --ks-pass pass:android --key-pass pass:android --out "%OUT%" "%BUILD_DIR%\aligned.apk"
if errorlevel 1 exit /b 1

echo.
echo Built: %OUT%
if /i "%1"=="install" "%ANDROID_SDK_ROOT%\platform-tools\adb.exe" install -r "%OUT%"
endlocal
