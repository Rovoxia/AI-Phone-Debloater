# setup-adb.ps1
# Detects/installs ADB for Windows and verifies an authorized device connection.
# Compatible with Windows PowerShell 5.1 and PowerShell Core.

$ErrorActionPreference = 'Stop'

# Resolve project folders relative to this script.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $scriptDir) { $scriptDir = '.' }
$projectRoot = Resolve-Path (Join-Path $scriptDir '..') | Select-Object -ExpandProperty Path
$toolsDir = Join-Path $projectRoot 'tools'
$platformToolsDir = Join-Path $toolsDir 'platform-tools'
$adbExe = Join-Path $platformToolsDir 'adb.exe'

function Find-AdbInPath {
    $adb = Get-Command 'adb.exe' -ErrorAction SilentlyContinue
    if ($adb) { return $adb.Source }
    return $null
}

function Test-AdbLocation($path) {
    $candidate = Join-Path $path 'adb.exe'
    if (Test-Path $candidate -PathType Leaf) { return $candidate }
    return $null
}

# 1. Check PATH.
$found = Find-AdbInPath
if ($found) {
    Write-Host "ADB found in PATH: $found" -ForegroundColor Green
    $adbExe = $found
    exit 0
}

# 2. Check standard install locations.
$standardLocations = @(
    (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools'),
    'C:\platform-tools'
)
if ($env:ANDROID_SDK_ROOT) { $standardLocations += Join-Path $env:ANDROID_SDK_ROOT 'platform-tools' }
if ($env:ANDROID_HOME) { $standardLocations += Join-Path $env:ANDROID_HOME 'platform-tools' }

foreach ($loc in $standardLocations) {
    $found = Test-AdbLocation $loc
    if ($found) {
        Write-Host "ADB found at: $found" -ForegroundColor Green
        $adbExe = $found
        $env:PATH = "$loc;$env:PATH"
        exit 0
    }
}

# 3. Not found: prompt to download official Google platform-tools for Windows.
Write-Host "ADB (adb.exe) was not found in PATH or standard locations." -ForegroundColor Yellow
Write-Host "Official download: https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -ForegroundColor Cyan
Write-Host

$download = "Y"
try {
    $input = Read-Host "Download and install platform-tools to ./tools/platform-tools now? [Y/n]"
    if ($input) { $download = $input }
} catch {
    $download = "Y"
}

if ($download -notmatch '^[Yy]$') {
    Write-Host "Aborted. Install ADB manually and re-run this script." -ForegroundColor Red
    exit 1
}

# Download.
if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }
$zipPath = Join-Path $toolsDir 'platform-tools-latest-windows.zip'
$url = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
Write-Host "Downloading $url ..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $url -OutFile $zipPath
} catch {
    Write-Host "Download failed: $_" -ForegroundColor Red
    exit 1
}

# Extract.
Write-Host "Extracting to $platformToolsDir ..." -ForegroundColor Cyan
if (-not (Test-Path $platformToolsDir)) { New-Item -ItemType Directory -Path $platformToolsDir -Force | Out-Null }
Expand-Archive -Path $zipPath -DestinationPath $platformToolsDir -Force

# The zip extracts into a nested platform-tools folder; flatten it.
$inner = Join-Path $platformToolsDir 'platform-tools'
if (Test-Path $inner -PathType Container) {
    Get-ChildItem $inner | Move-Item -Destination $platformToolsDir -Force
    Remove-Item $inner -Recurse -Force
}
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

# Add to session PATH.
$env:PATH = "$platformToolsDir;$env:PATH"

# Verify.
$adbExe = Join-Path $platformToolsDir 'adb.exe'
if (-not (Test-Path $adbExe -PathType Leaf)) {
    Write-Host "Failed to install adb.exe at $adbExe" -ForegroundColor Red
    exit 1
}
Write-Host "ADB installed at: $adbExe" -ForegroundColor Green

# Test connection.
Write-Host
Write-Host "Starting adb server..." -ForegroundColor Cyan
& $adbExe start-server | Out-Null
Start-Sleep -Seconds 2

Write-Host "Running adb devices..." -ForegroundColor Cyan
$devices = & $adbExe devices
Write-Host $devices

if ($devices -match '\tunauthorized') {
    Write-Host
    Write-Host "A device is listed as 'unauthorized'." -ForegroundColor Yellow
    Write-Host "On your phone screen, accept the RSA authorization prompt to allow USB debugging." -ForegroundColor Yellow
} elseif ($devices -match '\toffline') {
    Write-Host
    Write-Host "A device is listed as 'offline'." -ForegroundColor Yellow
    Write-Host "Check the USB cable and try again." -ForegroundColor Yellow
} elseif ($devices -match '\tdevice') {
    Write-Host "A device is authorized and ready." -ForegroundColor Green
} else {
    Write-Host
    Write-Host "No authorized device found." -ForegroundColor Yellow
    Write-Host "To connect:" -ForegroundColor Cyan
    Write-Host "  1. Enable Developer Options on your phone (tap Build Number 7 times in Settings)." -ForegroundColor Cyan
    Write-Host "  2. Enable USB debugging in Developer Options." -ForegroundColor Cyan
    Write-Host "  3. Connect the phone via USB." -ForegroundColor Cyan
    Write-Host "  4. Accept the 'Allow USB debugging?' RSA prompt on the phone screen." -ForegroundColor Cyan
    Write-Host "  5. Re-run this script." -ForegroundColor Cyan
}
