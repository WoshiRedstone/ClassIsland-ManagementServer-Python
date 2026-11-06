<#
.SYNOPSIS
    对 release 目录里的编译产物做一次完整验收：冷启动 + 六套测试 + WebUI 静态托管。

.DESCRIPTION
    本脚本自己负责启动/停止服务端（用 Start-Process 拉起，**不重定向标准输出**，
    因为重定向会让子进程挂在本进程的管道上，本进程一退出子进程就收到 SIGPIPE/写失败而死）。

    已经跑起来的服务端也可以用 -SkipStart 跳过启动，直接对着现有实例跑测试。

.EXAMPLE
    pwsh -NoProfile -File tests\verify_release.ps1 -SkipStart
#>
[CmdletBinding()]
param(
    [string]$ReleaseDir = "",
    [string]$BaseUrl = 'http://127.0.0.1:7878',
    [string]$GrpcTarget = '127.0.0.1:7879',
    [string]$Python = '',
    [int]$StartupTimeoutSec = 60,
    [switch]$SkipStart
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $ReleaseDir) { $ReleaseDir = Join-Path $repoRoot 'release' }
if (-not $Python) { $Python = Join-Path $repoRoot 'miniconda3\envs\man\python.exe' }

# 本机装有系统代理，Python/PS 都会读 WinINET 配置，必须绕开 loopback。
$env:NO_PROXY = '127.0.0.1,localhost,::1'
$env:no_proxy = '127.0.0.1,localhost,::1'

$results = [ordered]@{}
$serverProc = $null

function Get-ListenerCount {
    return (Get-NetTCPConnection -State Listen -LocalPort 7878, 7879 -ErrorAction SilentlyContinue | Measure-Object).Count
}

function Stop-Server {
    if ($script:serverProc -and -not $script:serverProc.HasExited) {
        Write-Host "    停止 pid=$($script:serverProc.Id)"
        Stop-Process -Id $script:serverProc.Id -Force -ErrorAction SilentlyContinue
    }
    Get-Process ManagementServer -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 30; $i++) {
        if ((Get-ListenerCount) -eq 0) { return }
        Start-Sleep -Milliseconds 200
    }
}

function Invoke-Suite {
    param([string]$Name, [scriptblock]$Body)
    Write-Host "=== $Name ==="
    $global:LASTEXITCODE = 0
    try {
        & $Body
        if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        $script:results[$Name] = 'PASS'
    }
    catch {
        Write-Host "    FAILED: $_"
        $script:results[$Name] = 'FAIL'
    }
}

try {
    if (-not $SkipStart) {
        Write-Host '=== 0. 冷启动 ==='
        Stop-Server
        $dataDir = Join-Path $ReleaseDir 'data'
        if (Test-Path $dataDir) { Remove-Item -Recurse -Force $dataDir }
        $exe = Join-Path $ReleaseDir 'ManagementServer.exe'
        if (-not (Test-Path $exe)) { throw "缺少产物 $exe" }
        # 关键：不重定向标准输出/错误，否则子进程会挂在本进程的管道上。
        $serverProc = Start-Process -FilePath $exe -WorkingDirectory $ReleaseDir -PassThru
        Write-Host "    启动 pid=$($serverProc.Id)"
        $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
        while ((Get-Date) -lt $deadline) {
            if ((Get-ListenerCount) -eq 2) { break }
            Start-Sleep -Milliseconds 500
        }
        if ((Get-ListenerCount) -ne 2) { throw "服务端未在 ${StartupTimeoutSec}s 内监听 7878/7879" }
    }
    else {
        Write-Host '=== 0. 复用已有服务端 ==='
        if ((Get-ListenerCount) -ne 2) { throw '7878/7879 未就绪，去掉 -SkipStart 让脚本自己启动' }
    }

    Write-Host '    7878/7879 已监听'
    $probe = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -NoProxy
    Write-Host "    GET / -> $($probe.StatusCode) ($($probe.RawContentLength) bytes)"
    $results['webui /'] = if ($probe.StatusCode -eq 200 -and $probe.RawContentLength -gt 500) { 'PASS' } else { 'FAIL' }

    $appConfig = Invoke-WebRequest -Uri "$BaseUrl/app.config.js" -UseBasicParsing -NoProxy
    Write-Host "    GET /app.config.js -> $($appConfig.StatusCode) ($($appConfig.RawContentLength) bytes)"
    $results['webui app.config.js'] = if ($appConfig.StatusCode -eq 200) { 'PASS' } else { 'FAIL' }

    $spa = Invoke-WebRequest -Uri "$BaseUrl/clients/list" -UseBasicParsing -NoProxy
    Write-Host "    GET /clients/list (SPA 回落) -> $($spa.StatusCode)"
    $results['webui spa fallback'] = if ($spa.StatusCode -eq 200) { 'PASS' } else { 'FAIL' }

    $login = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" -Method POST -ContentType 'application/json' -NoProxy `
        -Body '{"username":"root","password":"root"}'
    Write-Host "    root/root 登录 token=$($login.accessToken.Length) 字符 expiresIn=$($login.expiresIn)"
    $results['login root/root'] = if ($login.accessToken.Length -gt 100) { 'PASS' } else { 'FAIL' }

    Invoke-Suite 'rest_e2e.py' {
        & $Python (Join-Path $repoRoot 'tests\rest_e2e.py') 2>&1 | Select-Object -Last 3
    }

    Invoke-Suite 'grpc_e2e.py' {
        & $Python (Join-Path $repoRoot 'tests\grpc_e2e.py') 2>&1 | Select-Object -Last 3
    }

    Invoke-Suite 'client_sim.py' {
        & $Python (Join-Path $repoRoot 'tests\client_sim.py') 2>&1 | Select-Object -Last 3
    }

    Invoke-Suite 'route_diff.py' {
        & $Python (Join-Path $repoRoot 'tests\route_diff.py') 2>&1 | Select-Object -Last 3
    }

    Invoke-Suite 'contract_test.ps1' {
        & pwsh -NoProfile -File (Join-Path $repoRoot 'tests\contract_test.ps1') -BaseUrl $BaseUrl -GrpcTarget $GrpcTarget 2>&1 | Select-Object -Last 3
    }

    Invoke-Suite 'grpc_interop (C#)' {
        $interop = Join-Path $repoRoot 'tests\grpc_interop\bin\Release\net8.0\GrpcClientInterop.exe'
        if (-not (Test-Path $interop)) { throw 'C# 互通测试未编译，先跑 dotnet build tests\grpc_interop\GrpcClientInterop.csproj -c Release' }
        & $interop --grpc "http://$GrpcTarget" --http $BaseUrl 2>&1 | Select-Object -Last 3
    }
}
finally {
    if (-not $SkipStart) { Write-Host '=== 停止服务端 ==='; Stop-Server }
}

Write-Host ''
Write-Host '=== 汇总 ==='
$fail = 0
foreach ($k in $results.Keys) {
    Write-Host ("  {0,-24} {1}" -f $k, $results[$k])
    if ($results[$k] -ne 'PASS') { $fail++ }
}
if ($fail -eq 0) { Write-Host 'ALL RELEASE CHECKS PASSED'; exit 0 }
Write-Host "RELEASE CHECKS FAILED: $fail"; exit 1
