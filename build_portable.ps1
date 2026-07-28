# ============================================================
#  Helix Core v3.0.0 — Full Portable Build Pipeline
#
#  Compiles the entire app into a single portable exe:
#
#  1. PyInstaller backend        → dist/backend/
#  2. Vite frontend (production) → frontend/dist/
#  3. electron-builder dir       → frontend/release/win-unpacked/
#  4. NSIS smart launcher        → HelixCore-3.0.0-portable.exe
#
#  Usage:  .\build_portable.ps1
#          .\build_portable.ps1 -SkipBackend   # skip backend if unchanged
#          .\build_portable.ps1 -PythonExe C:\path\to\python.exe
# ============================================================

param(
    [switch]$SkipBackend,
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Resolve a manual NSIS installation first, then electron-builder's cache.
$makensisCommand = Get-Command makensis -ErrorAction SilentlyContinue
$makensis = if ($makensisCommand) { $makensisCommand.Source } else { "" }
if (-not $makensis) {
    $nsisDirs = Get-ChildItem "$env:LOCALAPPDATA\electron-builder\Cache\nsis" -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^nsis-\d' } |
        Sort-Object Name -Descending
    foreach ($nsisDir in $nsisDirs) {
        $candidates = @(
            (Join-Path $nsisDir.FullName "Bin\makensis.exe"),
            (Join-Path $nsisDir.FullName "makensis.exe")
        )
        $makensis = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($makensis) { break }
    }
}

$outExe   = "frontend\release\HelixCore-3.0.0-portable.exe"
$nsisOut  = "HelixCore-3.0.0-portable.exe"
$TOTAL_STEPS = 4

$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

function Write-Phase([int]$n, [int]$total, [string]$msg) {
    Write-Host "`n=== [$n/$total] $msg ===" -ForegroundColor Cyan
}

# ---- Preflight checks ---------------------------------------------------
$pythonPath = if ($PythonExe) {
    (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $pythonCommand.Source } else { "" }
}
if (-not $pythonPath) { throw "Python not found in PATH. Install Python 3.12.1 or newer in the 3.12 series." }

$pythonVersionText = (& $pythonPath -c "import platform; print(platform.python_version())").Trim()
$pythonVersion = [version]$pythonVersionText
if (-not $SkipBackend -and (
    $pythonVersion.Major -ne 3 -or
    $pythonVersion.Minor -ne 12 -or
    $pythonVersion.Build -lt 1
)) {
    throw "Backend packaging requires CPython 3.12.1–3.12.x. Python 3.12.0 has a confirmed bytecode bug that breaks frozen SciPy imports; other minor series do not match the pinned release environment. Found $pythonVersionText at $pythonPath."
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) { throw "npm not found in PATH. Install Node.js 20+." }

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { throw "Node.js not found in PATH. Install Node.js 20+." }

$pyinstallerVersion = ""
if (-not $SkipBackend) {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $pyinstallerVersion = (& $pythonPath -m PyInstaller --version 2>$null).Trim()
    $pyinstallerExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    if ($pyinstallerExit -ne 0 -or -not $pyinstallerVersion) {
        throw "PyInstaller is not installed for $pythonPath. Install it with: `"$pythonPath`" -m pip install pyinstaller"
    }
}

if (-not $makensis -or -not (Test-Path $makensis)) {
    throw "makensis not found in electron-builder cache.`nRun electron-builder once to cache NSIS, or install NSIS manually."
}

# Check frontend node_modules exist
if (-not (Test-Path "frontend\node_modules")) {
    throw "frontend\node_modules not found. Run: cd frontend && npm install"
}

# A missing tools/ directory is only a warning to electron-builder, but it
# produces a crippled release with no docking engine or format converter.
# Treat both absence and any hash mismatch as a hard preflight failure.
if (-not (Test-Path "tools")) {
    throw "tools\ not found. Restore the verified bundle first: python scripts\fetch_tools.py"
}
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$toolCheckOutput = & $pythonPath "scripts\fetch_tools.py" "--check" 2>&1
$toolCheckExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
foreach ($line in $toolCheckOutput) { Write-Host "  $line" -ForegroundColor DarkGray }
if ($toolCheckExit -ne 0) {
    throw "tools\ failed manifest verification; refusing to package unverified scientific binaries"
}

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host "   HELIX CORE v3.0.0 — Production Build   " -ForegroundColor Cyan
Write-Host "  =======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Python:     $pythonPath ($pythonVersionText)" -ForegroundColor DarkGray
Write-Host "  Node.js:    $($node.Source)" -ForegroundColor DarkGray
Write-Host "  npm:        $($npm.Source)" -ForegroundColor DarkGray
Write-Host "  makensis:   $makensis" -ForegroundColor DarkGray
if (-not $SkipBackend) {
    Write-Host "  PyInstaller: $pyinstallerVersion" -ForegroundColor DarkGray
}

# ---- Step 1: PyInstaller backend ----------------------------------------
if ($SkipBackend) {
    Write-Phase 1 $TOTAL_STEPS "Backend build SKIPPED (-SkipBackend)"
    if (-not (Test-Path "dist\backend\backend.exe")) {
        throw "dist\backend\backend.exe not found. Cannot skip backend build."
    }
    $backendSz = [math]::Round((Get-Item "dist\backend\backend.exe").Length / 1MB, 1)
    Write-Host "  Using existing backend.exe ($backendSz MB)" -ForegroundColor Yellow
} else {
    Write-Phase 1 $TOTAL_STEPS "Compiling backend (PyInstaller)"

    # Clean previous build artifacts
    Remove-Item -Recurse -Force "dist\backend" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "build\backend" -ErrorAction SilentlyContinue

    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $pyiOutput = & $pythonPath -m PyInstaller backend.spec --noconfirm 2>&1
    $pyiExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    foreach ($line in $pyiOutput) {
        $text = "$line"
        if ($text -match "error|ERROR|Error") {
            Write-Host "  $text" -ForegroundColor Red
        } elseif ($text -match "Building|Copying|INFO") {
            Write-Host "  $text" -ForegroundColor DarkGray
        }
    }
    if ($pyiExit -ne 0) { throw "PyInstaller build failed" }

    if (-not (Test-Path "dist\backend\backend.exe")) {
        throw "PyInstaller produced no output — dist\backend\backend.exe missing"
    }

    $backendSz = [math]::Round((Get-Item "dist\backend\backend.exe").Length / 1MB, 1)
    $internalSz = [math]::Round(((Get-ChildItem "dist\backend\_internal" -Recurse -File |
        Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host "  backend.exe: $backendSz MB | _internal/: $internalSz MB" -ForegroundColor Green
}

# ---- Step 2: Vite frontend build (production) ---------------------------
Write-Phase 2 $TOTAL_STEPS "Building frontend (Vite — production mode)"
Push-Location frontend
$env:NODE_ENV = "production"
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
npx vite build 2>&1 | ForEach-Object { "$_" }
$viteExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($viteExit -ne 0) { Pop-Location; throw "Vite build failed" }
Write-Host "  Frontend built (production)" -ForegroundColor Green
Pop-Location

# ---- Step 3: electron-builder dir target ---------------------------------
Write-Phase 3 $TOTAL_STEPS "Packaging with electron-builder (dir)"
Push-Location frontend
# Clean previous release
Remove-Item -Recurse -Force release -ErrorAction SilentlyContinue
Start-Sleep 1
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
npx electron-builder --win dir 2>&1 | ForEach-Object { "$_" }
$ebExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($ebExit -ne 0) { Pop-Location; throw "electron-builder failed" }
Pop-Location

# Verify win-unpacked was created
if (-not (Test-Path "frontend\release\win-unpacked\Helix Core.exe")) {
    throw "electron-builder did not produce win-unpacked\Helix Core.exe"
}
$unpackedSz = [math]::Round(((Get-ChildItem "frontend\release\win-unpacked" -Recurse -File |
    Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "  win-unpacked/: $unpackedSz MB total" -ForegroundColor Green

# ---- Step 4: NSIS smart launcher ----------------------------------------
Write-Phase 4 $TOTAL_STEPS "Compiling NSIS launcher"
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $makensis launcher.nsi 2>&1 | ForEach-Object { "$_" }
$nsisExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($nsisExit -ne 0) { throw "NSIS compilation failed" }

# Move from root to release/
Remove-Item $outExe -Force -ErrorAction SilentlyContinue
Move-Item $nsisOut $outExe

$launcherSz = [math]::Round((Get-Item $outExe).Length / 1MB, 1)
Write-Host "  Launcher: $launcherSz MB (LZMA compressed)" -ForegroundColor Green

# ---- Summary ------------------------------------------------------------
$stopwatch.Stop()
$elapsed = $stopwatch.Elapsed
$finalSz = [math]::Round((Get-Item $outExe).Length / 1MB, 1)

Write-Host ""
Write-Host "  =======================================" -ForegroundColor Green
Write-Host "         BUILD COMPLETE                  " -ForegroundColor Green
Write-Host "  =======================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output:       $outExe" -ForegroundColor White
Write-Host "  Size:         $finalSz MB" -ForegroundColor White
Write-Host "  Time:         $($elapsed.Minutes)m $($elapsed.Seconds)s" -ForegroundColor White
Write-Host ""
Write-Host "  First launch:  extracts to %APPDATA%\HelixCoreApp\" -ForegroundColor DarkGray
Write-Host "  Next launches: instant (cached)" -ForegroundColor DarkGray
Write-Host ""
