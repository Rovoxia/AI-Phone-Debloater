import type { APIRoute } from 'astro';

export const prerender = true;

const scriptContent = `
$ErrorActionPreference = 'Stop'

$RepoUrl   = "https://github.com/Rovoxia/AI-Phone-Debloater/archive/refs/heads/main.zip"
$Subfolder = "cli"
$InstallDir  = "$HOME\\.ai-phone-debloater"
$BridgePort  = "53123"
$AppUrl      = "https://debloater.rovoxia.com/app?bridge=1"
$BridgeScript = Join-Path $InstallDir "src\\bridge_server.py"
$EngineScript = Join-Path $InstallDir "debloat_engine.py"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  AI-Phone-Debloater WebApp Local ADB Bridge (Windows)" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

# --- Version sync (mirrors run.ps1.ts behaviour) ---
$TempDir  = Join-Path $env:TEMP ([Guid]::NewGuid().ToString())
$ZipFile  = Join-Path $TempDir "repo.zip"

try {
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
    Write-Host "[INFO] Fetching latest repository files..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $RepoUrl -OutFile $ZipFile

    Write-Host "[INFO] Extracting archive..." -ForegroundColor Yellow
    Expand-Archive -Path $ZipFile -DestinationPath $TempDir -Force

    $ExtractedRoot = Get-ChildItem -Path $TempDir -Directory | Select-Object -First 1
    $SourceSubfolder = Join-Path $ExtractedRoot.FullName $Subfolder

    if (-not (Test-Path $SourceSubfolder)) {
        throw "Subfolder '$Subfolder' not found in the repository archive."
    }

    $InstalledVersionFile = Join-Path $InstallDir "VERSION"
    $InstalledVersion = ""
    if (Test-Path $InstalledVersionFile) {
        $InstalledVersion = (Get-Content $InstalledVersionFile -Raw).Trim()
    }

    $NewVersionFile = Join-Path $ExtractedRoot.FullName "VERSION"
    $NewVersion = ""
    if (Test-Path $NewVersionFile) {
        $NewVersion = (Get-Content $NewVersionFile -Raw).Trim()
    } else {
        throw "VERSION file not found in repository archive."
    }

    $VersionChanged = ($InstalledVersion -ne $NewVersion) -or (-not (Test-Path $InstallDir))

    Write-Host "[INFO] Syncing CLI to $InstallDir (Version: $NewVersion)..." -ForegroundColor Yellow

    if ($VersionChanged) {
        if ($InstalledVersion -ne "") {
            Write-Host "[INFO] Version update detected ($InstalledVersion -> $NewVersion). Refreshing binaries and ADB tools..." -ForegroundColor Yellow
        }
        $ToolsDir = Join-Path $InstallDir "tools"
        if (Test-Path $ToolsDir) {
            Remove-Item -Recurse -Force $ToolsDir -ErrorAction SilentlyContinue
        }
    }

    # Clean existing install directory except tools (tools only purged if version changed)
    if (Test-Path $InstallDir) {
        Get-ChildItem -Path $InstallDir | Where-Object { $_.Name -ne "tools" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    }

    # Copy updated CLI files
    Copy-Item -Recurse -Force "$SourceSubfolder\\*" $InstallDir

    # Copy VERSION file
    if (Test-Path $NewVersionFile) {
        Copy-Item -Force $NewVersionFile $InstallDir
    }

    # Ensure required subdirectory exists for bridge script
    if (-not (Test-Path (Join-Path $InstallDir "src"))) {
        New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "src") | Out-Null
    }

    Write-Host "[SUCCESS] Ready!" -ForegroundColor Green

    # --- Launch bridge server ---
    $Launcher = ""
    if (Test-Path $BridgeScript) {
        $Launcher = $BridgeScript
    } else {
        $Launcher = $EngineScript
    }

    Write-Host "[INFO] Opening WebApp workspace in default browser..." -ForegroundColor Green
    Start-Process $AppUrl

    Write-Host "[INFO] Starting Python bridge server on port $BridgePort ..." -ForegroundColor Green
    Write-Host "[INFO] Bridge server active on http://127.0.0.1:$BridgePort" -ForegroundColor DarkGray

    $BridgeProc = Start-Process -FilePath "python" -ArgumentList @("$Launcher", "--port", $BridgePort) -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $env:TEMP "bridge_out.log") -RedirectStandardError (Join-Path $env:TEMP "bridge_err.log")

    Write-Host "[INFO] Press Ctrl+C in this terminal to stop the bridge when done." -ForegroundColor DarkGray
    while (-not $BridgeProc.HasExited) {
        Start-Sleep -Seconds 1
    }
}
catch {
    Write-Host "[ERROR] $_" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path $TempDir) {
        Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    }
    Remove-Item -Force $BridgeProc.LogFileName -ErrorAction SilentlyContinue
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
