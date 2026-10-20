# Builds what goes into a GitHub release, into dist\release:
#
#   Wavelane_<version>_x64-portable.zip   Windows, unpack and run (the in-app updater installs this one)
#   Wavelane_<version>_android.apk        Android, signed with the key from build-android.bat
#
# The version is the one in CMakeLists.txt. The updater of the app finds these files by their
# endings ("portable.zip" and ".apk"), so keep the names.
#
#   .\package-release.ps1                 both
#   .\package-release.ps1 -SkipAndroid    only the Windows zip

param(
    [switch]$SkipWindows,
    [switch]$SkipAndroid
)

# Windows PowerShell 5 turns a native tool's stderr into an error; the exit codes are checked by hand.
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$cmake = Get-Content (Join-Path $PSScriptRoot 'CMakeLists.txt') -Raw
if ($cmake -notmatch 'project\(Wavelane VERSION ([0-9]+\.[0-9]+\.[0-9]+)') { throw 'no version in CMakeLists.txt' }
$version = $Matches[1]
$out = Join-Path $root 'dist\release'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Write-Host "Packaging Wavelane $version into $out"

if (-not $SkipWindows) {
    # A build directory of its own, so a copy of the app running from client\build cannot block the linker.
    $env:BUILD_DIR = Join-Path $PSScriptRoot 'build-release'
    cmd /c "`"$PSScriptRoot\build.bat`" 2>&1"
    if ($LASTEXITCODE -ne 0) { throw 'the Windows build failed' }

    $stage = Join-Path $out 'stage'
    $app = Join-Path $stage 'Wavelane'
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $app | Out-Null
    Copy-Item (Join-Path $env:BUILD_DIR 'wavelane.exe') $app

    $deploy = Join-Path $root 'tools\Qt\6.8.3\msvc2022_64\bin\windeployqt.exe'
    & $deploy --qmldir (Join-Path $PSScriptRoot 'qml') --no-translations (Join-Path $app 'wavelane.exe')
    if ($LASTEXITCODE -ne 0) { throw 'windeployqt failed' }

    $zip = Join-Path $out "Wavelane_${version}_x64-portable.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    & tar.exe -a -cf $zip -C $stage Wavelane
    if ($LASTEXITCODE -ne 0) { throw 'could not make the zip' }
    Remove-Item $stage -Recurse -Force
}

if (-not $SkipAndroid) {
    cmd /c "`"$PSScriptRoot\build-android.bat`" 2>&1"
    if ($LASTEXITCODE -ne 0) { throw 'the Android build failed' }
    Copy-Item (Join-Path $root 'dist\Wavelane-android.apk') (Join-Path $out "Wavelane_${version}_android.apk") -Force
}

Get-ChildItem $out -File | ForEach-Object {
    '{0,-40} {1,8:N1} MB  sha256:{2}' -f $_.Name, ($_.Length / 1MB), (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
}
