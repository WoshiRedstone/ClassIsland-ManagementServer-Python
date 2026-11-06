# 链式执行 bsk 动作：每个动作前 cooperate sync 拿新 context，执行后把 post.context_id 交给下一个动作。
# 用法：pwsh -File tests\bskchain.ps1 -Session dbzf -Steps 'click:@e1','fill:@e2:root','click:@e3'
param(
    [string]$Session = "dbzf",
    [string[]]$Steps = @(),
    [string]$Json = "0",
    [string]$BskPath = $env:BSK_PATH
)
$bsk = if ($BskPath -and (Test-Path $BskPath)) { $BskPath } else { "bsk" }
$ctx = (& $bsk cooperate sync --session $Session --json 2>&1 | ConvertFrom-Json).context_id
foreach ($s in $Steps) {
    $parts = $s.Split(":", 3)
    $action = $parts[0]
    $params = @{}
    switch ($action) {
        "click" { $params = @{ ref = $parts[1] } }
        "fill"  { $params = @{ ref = $parts[1]; value = $parts[2] } }
        "press" { $params = @{ key = $parts[1] } }
        "goto"  { $params = @{ url = $parts[1] } }
        default { $params = @{ ref = $parts[1] } }
    }
    $pjson = $params | ConvertTo-Json -Compress
    $out = & $bsk step --session $Session --context $ctx --action $action --params $pjson --json 2>&1 | Out-String
    $obj = $null
    try { $obj = $out | ConvertFrom-Json } catch { }
    if ($obj -and $obj.ok -eq $true -and $obj.post.context_id) {
        $ctx = $obj.post.context_id
        Write-Host "ok $action $($parts[1])"
    } elseif ($obj -and $obj.post.context_id) {
        $ctx = $obj.post.context_id
        Write-Host "done-with-changes $action $($parts[1])"
    } else {
        Write-Host "FAILED $action $($parts[1])"
        if ($Json -eq "1") { Write-Host $out }
        # 尝试重新 sync 继续
        $ctx = (& $bsk cooperate sync --session $Session --json 2>&1 | ConvertFrom-Json).context_id
    }
}
Write-Host "final_ctx=$ctx"
