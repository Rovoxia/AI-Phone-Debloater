import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `
$ErrorActionPreference = 'Stop'

$RepoUrl   = "https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
$Subfolder = "cli"
$InstallDir  = "$HOME\\.ai-phone-debloater"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  AI-Phone-Debloater Zero-Git Installer (Windows)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

$TempDir  = Join-Path $env:TEMP ([Guid]::NewGuid().ToString())
$ZipFile  = Join-Path $TempDir "repo.zip"

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

try {
    Write-Host "[INFO] Downloading repository archive from GitHub..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $RepoUrl -OutFile $ZipFile

    Write-Host "[INFO] Extracting archive..." -ForegroundColor Yellow
    Expand-Archive -Path $ZipFile -DestinationPath $TempDir -Force

    $ExtractedRoot = Get-ChildItem -Path $TempDir -Directory | Select-Object -First 1
    $SourceSubfolder = Join-Path $ExtractedRoot.FullName $Subfolder

    if (-not (Test-Path $SourceSubfolder)) {
        throw "Subfolder '$Subfolder' not found in the repository archive."
    }

    Write-Host "[INFO] Installing CLI to $InstallDir..." -ForegroundColor Yellow
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item -Recurse -Force "$SourceSubfolder\\*" $InstallDir

    Write-Host "[SUCCESS] Installation complete!" -ForegroundColor Green
    Write-Host "[INFO] Location: $InstallDir" -ForegroundColor Cyan

    $Launcher = Join-Path $InstallDir "bin\\debloat.bat"
    if (-not (Test-Path $Launcher)) {
        $Launcher = Join-Path $InstallDir "debloat.bat"
    }

    if (Test-Path $Launcher) {
        Write-Host "[INFO] Launching debloater in current terminal..." -ForegroundColor Green
        & $Launcher
    } else {
        Write-Host "[ERROR] Launcher script not found at bin\\debloat.bat or root." -ForegroundColor Red
    }
}
catch {
    Write-Host "[ERROR] $_" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path $TempDir) {
        Write-Host "[INFO] Cleaning up temporary files..." -ForegroundColor DarkGray
        Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    }
}
`;

export const GET: APIRoute = async () => {
  return new Response(scriptContent.trim(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-cache, no-store, must-revalidate'
    }
  });
};
