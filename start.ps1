# Helix Core v3.0.0 development launcher.
# Electron owns the backend lifecycle; run.ps1 contains the single canonical
# implementation so the two entry points cannot drift to different ports.

$launcher = Join-Path $PSScriptRoot "run.ps1"
& $launcher
exit $LASTEXITCODE
