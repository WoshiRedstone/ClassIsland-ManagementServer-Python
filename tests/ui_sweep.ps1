# WebUI 全页面巡检：逐页导航 + 抓 console 错误 / 失败请求 + 截图。
# 用法：pwsh -File tests\ui_sweep.ps1 -Session dbzf
param(
    [string]$Session = "dbzf",
    [string]$Base = "http://127.0.0.1:7878",
    [string]$OutDir = (Join-Path $PSScriptRoot "screenshots"),
    [string]$BskPath = (Join-Path $env:LOCALAPPDATA "..\.local\bin\bsk.exe")
)
$bsk = if (Test-Path $BskPath) { $BskPath } else { "bsk" }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }

function Sync { (& $bsk cooperate sync --session $Session --json 2>&1 | ConvertFrom-Json).context_id }
function Step($ctx, $action, $params) {
    $out = & $bsk step --session $Session --context $ctx --action $action --params ($params | ConvertTo-Json -Compress) --json 2>&1 | Out-String
    try { return ($out | ConvertFrom-Json) } catch { return $null }
}

$pages = @(
    @{ n = "console";     p = "/dashboard/console" },
    @{ n = "clients";     p = "/clients/list" },
    @{ n = "clientgroups";p = "/clients/groups" },
    @{ n = "classplans";  p = "/profiles/classplans" },
    @{ n = "timelayouts"; p = "/profiles/time_layouts" },
    @{ n = "subjects";    p = "/profiles/subjects" },
    @{ n = "upload";      p = "/profiles/upload" },
    @{ n = "policies";    p = "/policies" },
    @{ n = "objgroups";   p = "/groups/list" },
    @{ n = "broadcast";   p = "/commands/broadcast" },
    @{ n = "reboot";      p = "/commands/reboot" },
    @{ n = "account";     p = "/setting/account" },
    @{ n = "system";      p = "/setting/system" },
    @{ n = "users";       p = "/setting/users" }
)

$results = @()
foreach ($pg in $pages) {
    $ctx = Sync
    $nav = Step $ctx "navigate" @{ url = "$Base$($pg.p)" }
    if ($nav -and $nav.post.context_id) { $ctx = $nav.post.context_id }
    Start-Sleep -Milliseconds 1800
    $ctx = Sync
    $obs = & $bsk observe --session $Session --max-tokens 900 --json 2>&1 | Out-String
    $text = ""
    try { $text = ($obs | ConvertFrom-Json).text } catch { $text = $obs }
    $has404 = $text -match "你访问的页面不存在"

    $ctx = Sync
    $con = & $bsk console --session $Session --context $ctx --json 2>&1 | Out-String
    $errors = @()
    try {
        $cj = $con | ConvertFrom-Json
        $errors = @($cj.entries | Where-Object { $_.level -in @("error", "warning") -and $_.text -match "error|Error|失败|401|403|500" } | Select-Object -First 3)
    } catch { }

    $ctx = Sync
    $net = & $bsk network --session $Session --context $ctx --json 2>&1 | Out-String
    $failed = @()
    try {
        $nj = $net | ConvertFrom-Json
        $failed = @($nj.entries | Where-Object { $_.status -ge 400 } | Select-Object -First 5)
    } catch { }

    $ctx = Sync
    $shot = Join-Path $OutDir "ui_$($pg.n).png"
    & $bsk screenshot --session $Session --context $ctx --out $shot --json 2>&1 | Out-Null

    $results += [pscustomobject]@{
        page = $pg.n; path = $pg.p; is404 = $has404
        jsErrors = $errors.Count; failedRequests = $failed.Count
        failed = ($failed | ForEach-Object { "$($_.status) $($_.url)" }) -join "; "
    }
    Write-Host "== $($pg.n) $($pg.p) 404=$has404 err=$($errors.Count) failedNet=$($failed.Count)"
    foreach ($f in $failed) { Write-Host "   NET $($f.status) $($f.url)" }
    foreach ($e in $errors) { Write-Host "   JS  $($e.text.Substring(0,[Math]::Min(140,$e.text.Length)))" }
}
$results | Format-Table -AutoSize
