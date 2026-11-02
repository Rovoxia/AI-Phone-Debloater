import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `
$ErrorActionPreference = 'Stop'

$RepoUrl   = "https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
$Subfolder = "cli"
$InstallDir  = "$HOME\\.ai-phone-debloater"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  AI-Phone-Debloater Zero-Git Runner (Windows)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

$TempDir  = Join-Path $env:TEMP ([Guid]::NewGuid().ToString())
$ZipFile  = Join-Path $TempDir "repo.zip"

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

try {
    Write-Host "[INFO] Fetching latest repository files..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $RepoUrl -OutFile $ZipFile

    Write-Host "[INFO] Extracting archive..." -ForegroundColor Yellow
    Expand-Archive -Path $ZipFile -DestinationPath $TempDir -Force

    $ExtractedRoot = Get-ChildItem -Path $TempDir -Directory | Select-Object -First 1
    $SourceSubfolder = Join-Path $ExtractedRoot.FullName $Subfolder

    if (-not (Test-Path $SourceSubfolder)) {
        throw "Subfolder '$Subfolder' not found in the repository archive."
    }

    # Version comparison
    $InstalledVersionFile = Join-Path $InstallDir "VERSION"
    $InstalledVersion = ""
    if (Test-Path $InstalledVersionFile) {
        $InstalledVersion = (Get-Content $InstalledVersionFile -Raw).Trim()
    }

    $NewVersionFile = Join-Path $ExtractedRoot.FullName "VERSION"
    $NewVersion = "1.0.0"
    if (Test-Path $NewVersionFile) {
        $NewVersion = (Get-Content $NewVersionFile -Raw).Trim()
    }

    $VersionChanged = ($InstalledVersion -ne $NewVersion) -or (-not (Test-Path $InstallDir))

    Write-Host "[INFO] Syncing CLI to $InstallDir (Version: $NewVersion)..." -ForegroundColor Yellow

    # Ensure permanent external backups directory exists safely in User's home
    $SafeBackupsDir = Join-Path $HOME "AiPhoneDebloater\\backups"
    New-Item -ItemType Directory -Force -Path $SafeBackupsDir | Out-Null

    # Migrate any legacy backups from install dir or accidental cli folder into safe external home folder
    $LegacyDirs = @(
        (Join-Path $InstallDir "backups"),
        (Join-Path $HOME "cli\\backups")
    )
    foreach ($ld in $LegacyDirs) {
        if (Test-Path $ld) {
            Copy-Item -Force "$ld\\*" $SafeBackupsDir -ErrorAction SilentlyContinue
            Remove-Item -Recurse -Force $ld -ErrorAction SilentlyContinue
        }
    }

    # If version changed, purge old tools so fresh ADB binaries are downloaded
    if ($VersionChanged) {
        if ($InstalledVersion -ne "") {
            Write-Host "[INFO] Version update detected ($InstalledVersion -> $NewVersion). Refreshing binaries and ADB tools..." -ForegroundColor Yellow
        }
        $ToolsDir = Join-Path $InstallDir "tools"
        if (Test-Path $ToolsDir) {
            Remove-Item -Recurse -Force $ToolsDir -ErrorAction SilentlyContinue
        }
    }

    # Clean existing install directory completely (backups live safely outside in ~/AiPhoneDebloater/backups)
    if (Test-Path $InstallDir) {
        Get-ChildItem -Path $InstallDir | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    }

    # Copy updated CLI files (excluding any backups folder)
    Get-ChildItem -Path $SourceSubfolder | Where-Object { $_.Name -ne "backups" } | Copy-Item -Destination $InstallDir -Recurse -Force

    # Ensure no backups folder ever exists in install dir
    $InstallBackups = Join-Path $InstallDir "backups"
    if (Test-Path $InstallBackups) {
        Remove-Item -Recurse -Force $InstallBackups -ErrorAction SilentlyContinue
    }

    # Copy VERSION file
    if (Test-Path $NewVersionFile) {
        Copy-Item -Force $NewVersionFile $InstallDir
    }

    Write-Host "[SUCCESS] Ready!" -ForegroundColor Green

    $Launcher = Join-Path $InstallDir "bin\\debloat.bat"
    if (-not (Test-Path $Launcher)) {
        $Launcher = Join-Path $InstallDir "debloat.bat"
    }

    if (Test-Path $Launcher) {
        Write-Host "[INFO] Launching debloater interactive engine..." -ForegroundColor Green
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
