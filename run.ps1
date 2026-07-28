# ================================================================
#  Helix Core v3.0.0 — Quick Launch
#  Starts FastAPI backend + Electron frontend in dev mode.
#  Usage:  .\run.ps1
# ================================================================

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ---- Colours / helpers ---------------------------------------------------
function Write-Step([string]$msg) { Write-Host "  > $msg" -ForegroundColor Green }
function Write-Err([string]$msg)  { Write-Host "  X $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host "          HELIX CORE  v3.0.0           " -ForegroundColor Cyan
Write-Host "    Drug Discovery Desktop Suite         " -ForegroundColor DarkCyan
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host ""

# ---- Preflight -----------------------------------------------------------
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Err "Python not found. Install Python 3.12+."; exit 1 }
Write-Step "Python: $($python.Source)"

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) { Write-Err "npm not found. Install Node.js 20+."; exit 1 }
Write-Step "npm:    $($npm.Source)"

$backendDir  = Join-Path $Root "backend"
$frontendDir = Join-Path $Root "frontend"

if (-not (Test-Path (Join-Path $backendDir "main.py"))) {
    Write-Err "backend/main.py not found."; exit 1
}
if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Err "frontend/package.json not found."; exit 1
}

# ---- Kill stale processes on port 8299 -----------------------------------
Write-Step "Cleaning stale processes ..."
$stalePids = Get-NetTCPConnection -LocalPort 8299 -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty OwningProcess -Unique
foreach ($spid in $stalePids) {
    if ($spid -gt 0) {
        Write-Step "  Killing PID $spid on port 8299"
        Stop-Process -Id $spid -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 500

# ---- Install frontend deps if needed -------------------------------------
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Step "Installing frontend dependencies (first run) ..."
    Push-Location $frontendDir
    npm install --loglevel warn
    Pop-Location
}

# ---- NOTE: Backend is NOT started here. Electron's main process handles
#       backend lifecycle (spawn, health-check, restart). Starting it here
#       causes a port-8299 race condition because RDKit imports are slow. --

# ---- Start Frontend (foreground, blocking) -------------------------------
Write-Step "Launching Electron (dev mode) — backend will be started by Electron …"
Write-Host ""

Push-Location $frontendDir

try {
    # npm run dev is blocking — exits when Electron window closes
    npm run dev 2>&1 | ForEach-Object { Write-Host $_ }
}
finally {
    Write-Host ""
    Write-Step "Shutting down ..."

    # Electron kills its own backend, but clean up any stragglers on port 8299
    $procs = Get-NetTCPConnection -LocalPort 8299 -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $procs) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }

    Write-Step "Done. Goodbye!"
    Pop-Location
}
