#!/usr/bin/env pwsh
# Run the first-time setup wizard (writes data/appsettings.json).
# Equivalent to the reference implementation's setup.ps1.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root 'out\main.dist\ManagementServer.exe'
if (-not (Test-Path $exe)) {
    Write-Host "[ERROR] Executable not found: $exe"
    Write-Host "        Build it first with build_exe.bat"
    exit 1
}
& $exe --setup=true
exit $LASTEXITCODE
