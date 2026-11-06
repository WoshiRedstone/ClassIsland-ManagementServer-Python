<#
.SYNOPSIS
   真实客户端契约测试：把服务端响应反序列化成 ClassIsland 2.1 的**真实**模型类型。

.DESCRIPTION
    直接加载 C:\ClassIsland-debug 里编译好的 ClassIsland.Shared.dll（2.1.0.0），
    用与客户端完全相同的序列化配置（JsonSerializerDefaults.Web）反序列化服务端返回的
    manifest / policy / default-settings / subjects / timelayouts / classplans。

    这比"看起来像 JSON"强得多：只要字段名、类型、枚举值有任何偏差，反序列化就会抛异常，
    与真实客户端加入集控时的行为一致。

.PARAMETER BaseUrl
    服务端根地址，默认 http://127.0.0.1:7878。

.PARAMETER ClientUid
    已注册的客户端 CUID，默认 99999999-8888-7777-6666-555555555555（测试会先自行注册）。

.PARAMETER GrpcTarget
    gRPC 地址，默认 127.0.0.1:7879，用于把上面的 CUID 注册到服务端。

.PARAMETER SharedDll
    真实客户端的 ClassIsland.Shared.dll 路径。不传时依次尝试环境变量
    CLASSISLAND_CLIENT_BIN 与默认的 C:\ClassIsland-debug 调试产物目录。

.EXAMPLE
    pwsh -File tests\contract_test.ps1
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:7878",
    [string]$ClientUid = "99999999-8888-7777-6666-555555555555",
    [string]$GrpcTarget = "127.0.0.1:7879",
    [string]$SharedDll = ""
)

$ErrorActionPreference = "Stop"

$script:Failures = 0
$script:Checks = 0

function Check([string]$Name, [scriptblock]$Body) {
    $script:Checks++
    try {
        $result = & $Body
        if ($result -eq $false) {
            $script:Failures++
            Write-Host "  [FAIL] $Name" -ForegroundColor Red
        } else {
            Write-Host "  [ok]   $Name" -ForegroundColor Green
        }
    } catch {
        $script:Failures++
        Write-Host "  [FAIL] $Name -> $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Assert-Equal($Actual, $Expected, [string]$What) {
    if ("$Actual" -ne "$Expected") {
        throw "$What expected '$Expected' but got '$Actual'"
    }
    return $true
}

Write-Host "==> 加载真实客户端程序集" -ForegroundColor Cyan
if (-not $SharedDll) {
    $clientBin = $env:CLASSISLAND_CLIENT_BIN
    if (-not $clientBin) {
        $clientBin = "C:\ClassIsland-debug\ClassIsland.Desktop\bin\Debug\net8.0-windows10.0.19041.0"
    }
    $SharedDll = Join-Path $clientBin "ClassIsland.Shared.dll"
}
if (-not (Test-Path $SharedDll)) {
    Write-Host "找不到 ClassIsland.Shared.dll：$SharedDll" -ForegroundColor Red
    Write-Host "请用 -SharedDll <路径> 指定，或设置环境变量 CLASSISLAND_CLIENT_BIN。" -ForegroundColor Yellow
    exit 2
}
$asm = [System.Reflection.Assembly]::LoadFrom($SharedDll)
Write-Host "    ClassIsland.Shared $($asm.GetName().Version)" -ForegroundColor DarkGray

# 与客户端 WebRequestHelper 完全一致的选项（JsonSerializerDefaults.Web：
# camelCase、大小写不敏感、不接受注释与尾随逗号）。
$jsonOptions = [System.Text.Json.JsonSerializerOptions]::new([System.Text.Json.JsonSerializerDefaults]::Web)

function Get-TypeOf([string]$Name) {
    $t = $asm.GetType($Name, $false)
    if ($null -eq $t) { throw "类型不存在：$Name" }
    return $t
}

function Invoke-Json([string]$Url) {
    $r = Invoke-WebRequest -Uri "$BaseUrl$Url" -UseBasicParsing -TimeoutSec 30 -NoProxy
    if ($r.StatusCode -ne 200) { throw "$Url -> HTTP $($r.StatusCode)" }
    return $r.Content
}

# --- 造数据：确保该客户端被分发到科目/时间表/课表 -----------------------------
# 服务端只在 objects_assignees 里有记录时才向客户端分发对象，所以契约测试必须
# 自己保证有内容可分发，否则「没有分发」会被误判成契约错误。
function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        $Body,
        [string]$Token
    )
    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $params = @{
        Uri             = "$BaseUrl$Path"
        Method          = $Method
        Headers         = $headers
        UseBasicParsing = $true
        TimeoutSec      = 30
        # Windows 上若配置了系统代理而 ProxyOverride 未包含 127.0.0.1，
        # Invoke-WebRequest 会把本地请求也发给代理并收到 404。
        NoProxy         = $true
    }
    if ($null -ne $Body) {
        $params["ContentType"] = "application/json; charset=utf-8"
        $params["Body"] = [System.Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 12))
    }
    try {
        $r = Invoke-WebRequest @params
        return @{ Status = [int]$r.StatusCode; Content = $r.Content }
    } catch {
        $resp = $_.Exception.Response
        if ($null -eq $resp) { throw }
        return @{ Status = [int]$resp.StatusCode; Content = "" }
    }
}

function Initialize-TestData {
    # 服务端只向通过 gRPC 注册过的客户端分发数据，干净数据库里默认 CUID 并不存在，
    # 因此先自己注册一次（重复调用安全：已注册会返回 Retcode.Registered）。
    $python = Join-Path (Split-Path -Parent $PSScriptRoot) "miniconda3\envs\man\python.exe"
    $register = Join-Path $PSScriptRoot "register_client.py"
    if ((Test-Path $python) -and (Test-Path $register)) {
        & $python $register --grpc $GrpcTarget --cuid $ClientUid | Out-Null
    }

    $login = Invoke-Api -Method POST -Path "/api/v1/auth/login" -Body @{ username = "root"; password = "root" }
    if ($login.Status -ne 200) { throw "登录失败：HTTP $($login.Status)（需要先运行过一次服务端以创建 root/root）" }
    $token = ($login.Content | ConvertFrom-Json).accessToken

    $groups = (Invoke-Api -Method GET -Path "/api/v1/profiles/groups" -Token $token).Content | ConvertFrom-Json
    $defaultGroup = $groups.items[0].id

    # 组织名称：干净数据库里没有 Brand 记录，manifest 的 organizationName 会是空串，
    # 而真实客户端会把它显示在标题上，所以测试自己写入一个。
    $brand = (Invoke-Api -Method GET -Path "/api/v1/settings/brand").Content | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($brand.organizationName)) {
        Invoke-Api -Method POST -Path "/api/v1/settings/brand" -Token $token -Body @{
            organizationName = "契约组织"; loginFormPlacement = "left"
        } | Out-Null
    }

    # 科目
    $subjects = (Invoke-Api -Method GET -Path "/api/v1/profiles/subjects?pageSize=200" -Token $token).Content | ConvertFrom-Json
    $subject = $subjects.items | Where-Object { $_.name -eq "契约科目" } | Select-Object -First 1
    if ($null -eq $subject) {
        Invoke-Api -Method PUT -Path "/api/v1/profiles/subjects" -Token $token -Body @{
            name = "契约科目"; initial = "契"; isOutDoor = $false; attachedObjects = @{}; groupId = $defaultGroup
        } | Out-Null
        $subjects = (Invoke-Api -Method GET -Path "/api/v1/profiles/subjects?pageSize=200" -Token $token).Content | ConvertFrom-Json
        $subject = $subjects.items | Where-Object { $_.name -eq "契约科目" } | Select-Object -First 1
    }

    # 时间表
    $layouts = (Invoke-Api -Method GET -Path "/api/v1/profiles/timeLayouts?pageSize=200" -Token $token).Content | ConvertFrom-Json
    $layout = $layouts.items | Where-Object { $_.name -eq "契约时间表" } | Select-Object -First 1
    if ($null -eq $layout) {
        Invoke-Api -Method PUT -Path "/api/v1/profiles/timeLayouts" -Token $token -Body @{
            name    = "契约时间表"
            layouts = @(
                @{ startSecond = "2026-10-30T08:00:00"; endSecond = "2026-10-30T08:45:00"; timeType = 0; isHideDefault = $false; defaultClassId = ""; attachedObjects = @{} },
                @{ startSecond = "2026-10-30T08:45:00"; endSecond = "2026-10-30T09:00:00"; timeType = 1; isHideDefault = $true; defaultClassId = ""; attachedObjects = @{} }
            )
            attachedObjects = @{}
            groupId = $defaultGroup
        } | Out-Null
        $layouts = (Invoke-Api -Method GET -Path "/api/v1/profiles/timeLayouts?pageSize=200" -Token $token).Content | ConvertFrom-Json
        $layout = $layouts.items | Where-Object { $_.name -eq "契约时间表" } | Select-Object -First 1
    }

    # 课表
    $plans = (Invoke-Api -Method GET -Path "/api/v1/profiles/classPlans?pageSize=200" -Token $token).Content | ConvertFrom-Json
    $plan = $plans.items | Where-Object { $_.name -eq "契约课表" } | Select-Object -First 1
    if ($null -eq $plan -and $layout -and $subject) {
        Invoke-Api -Method PUT -Path "/api/v1/profiles/classPlans" -Token $token -Body @{
            name         = "契约课表"
            timeRule     = @{ weekDay = 1; weekCountDiv = 0; weekCountDivTotal = 2 }
            timeLayoutId = $layout.id
            classes      = @(@{ subjectId = $subject.id }, @{ subjectId = $subject.id })
            attachedObjects = @{}
            isEnabled    = $true
            groupId      = $defaultGroup
        } | Out-Null
        # 新建端点返回空 body，必须重新拉列表才能拿到 id。
        $plans = (Invoke-Api -Method GET -Path "/api/v1/profiles/classPlans?pageSize=200" -Token $token).Content | ConvertFrom-Json
        $plan = $plans.items | Where-Object { $_.name -eq "契约课表" } | Select-Object -First 1
    }

    # 把三个对象都分发给全局分组（-1），保证任何客户端都能收到
    $assignees = (Invoke-Api -Method GET -Path "/api/v1/assignees/by-object/assignees/3/$($subject.id)" -Token $token)
    $existing = @()
    if ($assignees.Status -eq 200) { $existing = ($assignees.Content | ConvertFrom-Json).items }
    $hasGlobal = $existing | Where-Object { $_.assigneeType -eq 3 -and "$($_.targetGroupId)" -eq "-1" }
    if (-not $hasGlobal) {
        Invoke-Api -Method POST -Path "/api/v1/assignees/all" -Token $token -Body @{
            objectId = $subject.id; objectType = 3; assigneeType = 3
            targetClientId = $null; targetClientCuid = $null; targetGroupId = -1
        } | Out-Null
    }
    foreach ($pair in @(@{ id = $layout.id; type = 2 }, @{ id = $plan.id; type = 1 })) {
        if (-not $pair.id) { continue }
        $cur = Invoke-Api -Method GET -Path "/api/v1/assignees/by-object/assignees/$($pair.type)/$($pair.id)" -Token $token
        $items = @()
        if ($cur.Status -eq 200) { $items = ($cur.Content | ConvertFrom-Json).items }
        if (-not ($items | Where-Object { $_.assigneeType -eq 3 -and "$($_.targetGroupId)" -eq "-1" })) {
            Invoke-Api -Method POST -Path "/api/v1/assignees/all" -Token $token -Body @{
                objectId = $pair.id; objectType = $pair.type; assigneeType = 3
                targetClientId = $null; targetClientCuid = $null; targetGroupId = -1
            } | Out-Null
        }
    }

    Write-Host "    已准备：科目 $($subject.id) / 时间表 $($layout.id) / 课表 $($plan.id)，均分发给全局分组" -ForegroundColor DarkGray
}

function Convert-FromJson([string]$Json, [string]$TypeName) {
    $t = Get-TypeOf $TypeName
    return [System.Text.Json.JsonSerializer]::Deserialize($Json, $t, $jsonOptions)
}

Write-Host "==> 造测试数据" -ForegroundColor Cyan
Initialize-TestData

Write-Host "==> manifest（客户端 Managementservice.cs:179 的硬校验点）" -ForegroundColor Cyan
$manifestJson = Invoke-Json "/api/v1/client/$ClientUid/manifest"
$manifest = Convert-FromJson $manifestJson "ClassIsland.Shared.Models.Management.ManagementManifest"

Check "manifest 可被真实类型反序列化" { $null -ne $manifest }
Check "coreVersion 主版本号 == IAppHost.CoreVersion(2.0.0.0)" {
    Assert-Equal $manifest.CoreVersion.Major 2 "CoreVersion.Major"
}
Check "serverKind == ManagementServer(1)" {
    Assert-Equal ([int]$manifest.ServerKind) 1 "ServerKind"
}
Check "classPlanSource 有值（否则客户端永不拉取课表）" {
    if ([string]::IsNullOrWhiteSpace($manifest.ClassPlanSource.Value)) { throw "classPlanSource.Value 为空" }
    return $true
}
Check "timeLayoutSource 有值" {
    if ([string]::IsNullOrWhiteSpace($manifest.TimeLayoutSource.Value)) { throw "timeLayoutSource.Value 为空" }
    return $true
}
Check "subjectsSource 有值" {
    if ([string]::IsNullOrWhiteSpace($manifest.SubjectsSource.Value)) { throw "subjectsSource.Value 为空" }
    return $true
}
Check "policySource 有值" {
    if ([string]::IsNullOrWhiteSpace($manifest.PolicySource.Value)) { throw "policySource.Value 为空" }
    return $true
}
Check "defaultSettingsSource 有值" {
    if ([string]::IsNullOrWhiteSpace($manifest.DefaultSettingsSource.Value)) { throw "defaultSettingsSource.Value 为空" }
    return $true
}
Check "organizationName 非空" {
    if ([string]::IsNullOrWhiteSpace($manifest.OrganizationName)) { throw "organizationName 为空" }
    return $true
}
Check "credentialSource / componentsSource 字段存在（2.1 新增）" {
    if ($null -eq $manifest.CredentialSource) { throw "CredentialSource 反序列化为 null" }
    if ($null -eq $manifest.ComponentsSource) { throw "ComponentsSource 反序列化为 null" }
    return $true
}

Write-Host "==> policy" -ForegroundColor Cyan
$policyJson = Invoke-Json "/api/v1/client/$ClientUid/policy"
$policy = Convert-FromJson $policyJson "ClassIsland.Shared.Models.Management.ManagementPolicy"
Check "policy 可被真实类型反序列化" { $null -ne $policy }
Check "policy.allowExitManagement 默认 true" { Assert-Equal $policy.AllowExitManagement $true "AllowExitManagement" }
Check "policy 含 2.1 新增 disableEasterEggs 字段（可序列化回）" {
    $back = [System.Text.Json.JsonSerializer]::Serialize($policy, $jsonOptions)
    if ($back -notmatch '"disableEasterEggs"') { throw "重新序列化后缺少 disableEasterEggs：$back" }
    return $true
}

Write-Host "==> default-settings" -ForegroundColor Cyan
$settingsJson = Invoke-Json "/api/v1/client/$ClientUid/default-settings"
$settings = Convert-FromJson $settingsJson "ClassIsland.Shared.Models.Management.ManagementPolicy"
Check "default-settings 可被真实类型反序列化" { $null -ne $settings }

Write-Host "==> subjects" -ForegroundColor Cyan
$subjectsJson = Invoke-Json "/api/v1/client/$ClientUid/subjects"
$subjectsProfile = Convert-FromJson $subjectsJson "ClassIsland.Shared.Models.Profile.Profile"
Check "subjects 载荷是合法 Profile" { $null -ne $subjectsProfile }
Check "subjects 载荷含课表群（客户端按 Guid 合并）" { $subjectsProfile.ClassPlanGroups.Count -ge 1 }
Check "selectedClassPlanGroupId 非空" {
    if ($subjectsProfile.SelectedClassPlanGroupId -eq [Guid]::Empty) { throw "SelectedClassPlanGroupId 为 Guid.Empty" }
    return $true
}

Write-Host "==> timelayouts" -ForegroundColor Cyan
$tlJson = Invoke-Json "/api/v1/client/$ClientUid/timelayouts"
$tlProfile = Convert-FromJson $tlJson "ClassIsland.Shared.Models.Profile.Profile"
Check "timelayouts 载荷是合法 Profile" { $null -ne $tlProfile }
if ($tlProfile.TimeLayouts.Count -gt 0) {
    $tl = $tlProfile.TimeLayouts.Values | Select-Object -First 1
    Check "TimeLayoutItem.StartTime 是 TimeSpan 类型（2.1 新字段）" {
        $item = $tl.Layouts | Select-Object -First 1
        if ($null -eq $item) { return $true }
        if ($item.StartTime -isnot [TimeSpan]) { throw "StartTime 类型是 $($item.StartTime.GetType().FullName)" }
        return $true
    }
    Check "TimeLayoutItem.StartTime 取值合理（00:00 < t < 23:59）" {
        $item = $tl.Layouts | Select-Object -First 1
        if ($null -eq $item) { return $true }
        if ($item.StartTime -le [TimeSpan]::Zero -or $item.StartTime -ge [TimeSpan]::FromHours(24)) {
            throw "StartTime 越界：$($item.StartTime)"
        }
        return $true
    }
    Check "TimeLayoutItem.EndTime > StartTime" {
        $item = $tl.Layouts | Select-Object -First 1
        if ($null -eq $item) { return $true }
        if ($item.EndTime -le $item.StartTime) { throw "EndTime($($item.EndTime)) <= StartTime($($item.StartTime))" }
        return $true
    }
} else {
    Check "至少分发一个时间表" { throw "服务端没有向该客户端分发任何时间表" }
}

Write-Host "==> classplans" -ForegroundColor Cyan
$cpJson = Invoke-Json "/api/v1/client/$ClientUid/classplans"
$cpProfile = Convert-FromJson $cpJson "ClassIsland.Shared.Models.Profile.Profile"
Check "classplans 载荷是合法 Profile" { $null -ne $cpProfile }
if ($cpProfile.ClassPlans.Count -gt 0) {
    $cp = $cpProfile.ClassPlans.Values | Select-Object -First 1
    Check "ClassPlan.AssociatedGroup 指向已存在的课表群（否则客户端看不到课表）" {
        if ($cp.AssociatedGroup -eq [Guid]::Empty) { return $true }   # 全局课表群也算合法
        if (-not $cpProfile.ClassPlanGroups.ContainsKey($cp.AssociatedGroup) -and
            -not $subjectsProfile.ClassPlanGroups.ContainsKey($cp.AssociatedGroup)) {
            throw "AssociatedGroup $($cp.AssociatedGroup) 不在课表群字典中"
        }
        return $true
    }
    Check "ClassPlan.classes 的 SubjectId 都能在 subjects 里找到" {
        foreach ($c in $cp.Classes) {
            if ($c.SubjectId -eq [Guid]::Empty) { continue }
            if (-not $subjectsProfile.Subjects.ContainsKey($c.SubjectId)) {
                throw "课表引用了不存在的科目 $($c.SubjectId)"
            }
        }
        return $true
    }
} else {
    Check "至少分发一个课表" { throw "服务端没有向该客户端分发任何课表" }
}

Write-Host ""
if ($script:Failures -eq 0) {
    Write-Host "ALL CONTRACT CHECKS PASSED ($($script:Checks) checks)" -ForegroundColor Green
    exit 0
} else {
    Write-Host "CONTRACT CHECKS FAILED: $($script:Failures)/$($script:Checks)" -ForegroundColor Red
    exit 1
}
