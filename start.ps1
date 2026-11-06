#!/usr/bin/env pwsh
# Start the ManagementServer (WebUI on 7878, gRPC on 7879).
# Equivalent to the reference implementation's start.ps1.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root 'out\main.dist\ManagementServer.exe'
if (-not (Test-Path $exe)) {
    Write-Host "[ERROR] Executable not found: $exe"
    Write-Host "        Build it first with build_exe.bat"
    exit 1
}
Push-Location (Split-Path -Parent $exe)
try {
    & $exe @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
