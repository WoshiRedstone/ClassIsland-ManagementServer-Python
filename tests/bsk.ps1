# Helper for driving bsk CLI on the shared (cooperate) tab.
# Every action needs a fresh context from `cooperate sync`, so wrap that here.
#
# bsk 路径优先取 -BskPath，其次环境变量 BSK_PATH，最后回落到 PATH 上的 bsk。
param(
    [Parameter(Mandatory = $true)][string]$Action,
    [string]$Ref,
    [string]$Selector,
    [string]$Value,
    [string]$Url,
    [string]$Key,
    [string]$Session = "suwn",
    [string]$BskPath = $env:BSK_PATH,
    [int]$TimeoutMs = 60000
)

$bsk = if ($BskPath -and (Test-Path $BskPath)) { $BskPath } else { "bsk" }
$ctx = (& $bsk cooperate sync --session $Session --json 2>&1 | ConvertFrom-Json).context_id

$common = @("--session", $Session, "--context", $ctx, "--json")
switch ($Action) {
    "navigate"  { & $bsk navigate $Url @common --wait-until load }
    "click"     { if ($Ref) { & $bsk click --ref $Ref @common } else { & $bsk click --selector $Selector @common } }
    "fill"      { if ($Ref) { & $bsk fill --ref $Ref --value $Value @common } else { & $bsk fill --selector $Selector --value $Value @common } }
    "press"     { if ($Ref) { & $bsk press --ref $Ref --key $Key @common } else { & $bsk press --key $Key @common } }
    "scroll-to" { if ($Ref) { & $bsk scroll-to --ref $Ref @common } else { & $bsk scroll-to --selector $Selector @common } }
    "select"    { if ($Ref) { & $bsk select --ref $Ref --values $Value @common } else { & $bsk select --selector $Selector --values $Value @common } }
    "reload"    { & $bsk reload @common }
    default     { throw "unsupported action: $Action" }
}
