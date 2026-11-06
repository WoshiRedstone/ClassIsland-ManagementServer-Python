param(
    [string]$BaseUrl = "http://127.0.0.1:7878",
    [string]$GrpcTarget = "127.0.0.1:7879",
    # 真实客户端的 CUID 来自 %LOCALAPPDATA%\ClassIsland\Management\Persist.json 的
    # ClientUniqueId；MAC 是客户端自算的首个非回环网卡地址。
    [string]$Cuid = "c72c3297-f0f2-48a3-9fd8-b571a3ca5079",
    [string]$ClientId = "test-class",
    [string]$ClientMac = "00155DB50F63",
    [string]$Username = "root",
    [string]$Password = "root"
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl
$grpcTarget = $GrpcTarget
$cuid = $Cuid
$clientId = $ClientId
$clientMac = $ClientMac

# 服务端只会向已通过 gRPC 注册的客户端分发数据：干净数据库里这个 CUID 不存在，
# 此时 manifest 会 404，后面的分配步骤也会报「找不到请求的对象」。
$python = Join-Path (Split-Path -Parent $PSScriptRoot) "miniconda3\envs\man\python.exe"
$register = Join-Path $PSScriptRoot "register_client.py"
if ((Test-Path $python) -and (Test-Path $register)) {
    & $python $register --grpc $grpcTarget --cuid $cuid --id $clientId --mac $clientMac | Out-Null
}

function Api($method, $path, $body) {
    $params = @{
        Uri         = "$base$path"
        Method      = $method
        Headers     = $script:headers
        ContentType = "application/json; charset=utf-8"
        UseBasicParsing = $true
        # 系统代理的 ProxyOverride 通常不含 127.0.0.1，本地请求必须直连。
        NoProxy     = $true
    }
    if ($null -ne $body) {
        $json = if ($body -is [string]) { $body } else { $body | ConvertTo-Json -Depth 10 }
        $params.Body = [System.Text.Encoding]::UTF8.GetBytes($json)
    }
    $resp = Invoke-WebRequest @params
    if ($resp.Content) { return ($resp.Content | ConvertFrom-Json) }
    return $null
}

$loginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "$base/api/v1/auth/login" -Method POST -ContentType "application/json" -Body $loginBody -NoProxy
$script:headers = @{ Authorization = "Bearer $($login.accessToken)" }

# --- subject ---
$subjectId = "11111111-1111-1111-1111-111111111111"
$body = @{ id = $subjectId; name = "语文"; initial = "语"; teacherName = "李老师"; isOutDoor = $false; attachedObjects = @{} }
Api PUT "/api/v1/profiles/subjects" $body | Out-Null
Write-Host "subject $subjectId written"

# --- time layout (note: the write field is `layouts`) ---
$tlId = "22222222-2222-2222-2222-222222222222"
$body = @{
    id       = $tlId
    name     = "集控时间表"
    groupId  = "00000000-0000-0000-0000-000000000001"
    layouts  = @(
        @{ index = 0; startSecond = "2026-10-31T08:00:00"; endSecond = "2026-10-31T08:45:00"; timeType = 0; isHideDefault = $false; defaultClassId = ""; breakName = "" }
    )
    attachedObjects = @{}
}
Api PUT "/api/v1/profiles/timeLayouts" $body | Out-Null
Write-Host "timeLayout $tlId written"

# --- class plan ---
$cpId = "33333333-3333-3333-3333-333333333333"
$body = @{
    id             = $cpId
    name           = "集控课表"
    groupId        = "00000000-0000-0000-0000-000000000001"
    associatedGroup = "acaf4ef0-e261-4262-b941-34ea93cb4369"
    timeLayoutId   = $tlId
    isEnabled      = $true
    timeRule       = @{ weekDay = 0; weekCountDiv = 0; weekCountDivTotal = 2 }
    classes        = @(@{ subjectId = $subjectId; isChangedClass = $false; isEnabled = $true })
    attachedObjects = @{}
}
Api PUT "/api/v1/profiles/classPlans" $body | Out-Null
Write-Host "classPlan $cpId written"

# --- assign all three to the real client ---
$items = @(
    @{ objectId = $subjectId; objectType = 3 },
    @{ objectId = $tlId;      objectType = 2 },
    @{ objectId = $cpId;      objectType = 1 }
)
foreach ($it in $items) {
    $asg = @{ objectId = $it.objectId; objectType = $it.objectType; assigneeType = 1; targetClientCuid = $cuid }
    Api POST "/api/v1/assignees/all" $asg | Out-Null
    Write-Host "assigned $($it.objectId) type=$($it.objectType) to $cuid"
}

$m = Api GET "/api/v1/client/$cuid/manifest" $null
Write-Host "manifest: subj=$($m.subjectsSource.version) tl=$($m.timeLayoutSource.version) cp=$($m.classPlanSource.version) policy=$($m.policySource.version) ds=$($m.defaultSettingsSource.version)"

