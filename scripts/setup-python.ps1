# scripts\setup-python.ps1
# Bootstraps the official Python 3.11.9 embeddable package (windows-amd64)
# into ./tools/python/ so debloat.bat can run with zero pre-installed Python.
# Compatible with Windows PowerShell 5.1 and PowerShell Core.
#
# Prints the path to python.exe on success and exits 0; exits non-zero on failure.

$ErrorActionPreference = 'Stop'

# Resolve project folders relative to this script.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $scriptDir) { $scriptDir = '.' }
$projectRoot = Resolve-Path (Join-Path $scriptDir '..') | Select-Object -ExpandProperty Path
$toolsDir = Join-Path $projectRoot 'tools'
$pythonDir = Join-Path $toolsDir 'python'
$pythonExe = Join-Path $pythonDir 'python.exe'

# Already bootstrapped?
if (Test-Path $pythonExe -PathType Leaf) {
    Write-Host ("Python ready at: " + $pythonExe) -ForegroundColor Green
    exit 0
}

$url = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'
$zipPath = Join-Path $toolsDir 'python-3.11.9-embed-amd64.zip'

if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Path $toolsDir -Force | Out-Null }

Write-Host 'Python was not found on this system.' -ForegroundColor Yellow
Write-Host "Downloading official Python 3.11.9 embeddable package:" -ForegroundColor Cyan
Write-Host ("  " + $url) -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $url -OutFile $zipPath
} catch {
    Write-Host ("Failed to download Python: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Install Python 3 manually from https://www.python.org/downloads/ and re-run.' -ForegroundColor Red
    exit 1
}

Write-Host ("Extracting to " + $pythonDir + " ...") -ForegroundColor Cyan
if (-not (Test-Path $pythonDir)) { New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null }
try {
    Expand-Archive -Path $zipPath -DestinationPath $pythonDir -Force
} catch {
    Write-Host ("Failed to extract Python: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $pythonExe -PathType Leaf)) {
    Write-Host ("Python embeddable extraction did not produce python.exe at " + $pythonExe) -ForegroundColor Red
    exit 1
}

Write-Host ("Python ready at: " + $pythonExe) -ForegroundColor Green
exit 0
