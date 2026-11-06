# AGENT.md — 智能体工作指南

本文件面向 **AI 编程智能体**。阅读顺序建议：本文件的「速览」→「代码地图」→ 你要改的部分。

> 人类读者请看 [README.md](README.md)；发行包的使用说明在发行版附件里。

---

## 速览

| 项 | 值 |
| --- | --- |
| 这是什么 | [ClassIsland/ManagementServer](https://github.com/ClassIsland/ManagementServer) 的 **Python 重写实现** |
| 语言/框架 | Python 3.12 · FastAPI · SQLAlchemy 2 · grpcio · PyJWT · bcrypt · PGPy |
| 端口 | REST/WebUI `7878`（HTTP/1.1）· gRPC `7879`（HTTP/2） |
| 数据库 | 默认 SQLite（`data/management.db`），可选 MySQL |
| 打包 | Nuitka `--standalone` → `out/main.dist/ManagementServer.exe` |
| 测试 | 六个套件（4 个 Python + 2 个 C#/PowerShell），见「测试矩阵」 |
| 许可证 | **AGPL-3.0**（沿用上游），见 [LICENSE](LICENSE) |

## 一句话架构

一个进程里同时跑两个服务：**uvicorn 托管的 FastAPI**（REST + WebUI 静态托管）和
**grpcio 的 aio/threaded server**（ClassIsland 客户端的握手与命令流）。
两者共享同一个 `CyreneMspConnectionService`（会话表），所以 REST 端点能把命令
推给 gRPC 长连接上的客户端。

---

## 代码地图

```
main.py                     进程入口（顶层异常兜底 + startup_error.log）
app/
  launcher.py               组装 FastAPI + 挂 static + 起 gRPC；--setup/--migrate 分支
  config.py                 appsettings.json 解析、命令行、路径解析（源码 vs 冻结）
  db.py                     SQLAlchemy 引擎/迁移/种子 + 7 个内置角色
  models.py                 全部实体 + to_json()（输出 camelCase）+ ci_get() 大小写不敏感读取
  pagination.py             PaginatedList 语义（pageIndex<=0 抛错）
  deps.py                   paginate / error / build_profile_service
  security.py               bcrypt 哈希 + PyJWT + require_roles 依赖
  middleware.py             SessionMiddleware（每请求一个 session）+ 全局错误处理
  services.py               业务核心：分发、缓存、PGP 会话、命令队列、档案实体 CRUD
  grpc_services.py          5 个 gRPC 服务 + 协议/会话拦截器
  setup_wizard.py           交互式安装向导（6 步）
  routers/
    core.py                 auth / settings / policies / default-settings / assignees
    clients.py              clients_registry / manifest / 档案分发
    client_groups.py        client_groups
    profiles.py             profiles（subjects / timeLayouts / classPlans / groups / upload）
    users.py                users 全套
    commands.py             client-commands（show-notification / restart-app）
  static/                   WebUI 构建产物（来自 webui-src）
protos/Protobuf/            由上游 .proto 生成的 pb2（按消息拆分的模块）
tests/                      六个套件 + 辅助脚本 + 截图
build_exe.bat               Nuitka 构建
```

### 三个必须理解的机制

**1. `SessionMiddleware`（`app/middleware.py`）**
每个请求开一个 SQLAlchemy session，`status < 400` 时 `commit()`。
⚠️ `commit()` **必须**包在 `try/except` 里：`BaseHTTPMiddleware` 此时已把响应交给
ASGI，再抛异常会撞坏 anyio 的 TaskGroup，uvicorn 报
`TypeError: expected a function, exception type or tuple of exception types`
且该请求变成 500 空响应。当前实现是失败就 `rollback()` 并返回 500 JSON。

**2. `ObjectsUpdateNotifyService`（`app/services.py`）**
客户端靠 `manifest` 里的版本号判断是否需要重新拉取。版本号 +1 的唯一途径是
`object_updates` 表里有对应行：
- `notify_object_updating(object_id, object_type)` — 精确类型（编辑/删除某个科目等）
- `notify_client_updating(cuid, id, group)` — 写 `ObjectType=0` 的通配行，命中时
  manifest 会把**五个版本号全部 +1**（分配关系变化走这条）

⚠️ **每个修改对象的端点都必须在提交前调用其中之一**，否则客户端永远看不到变更。
这是历史上真实踩过的坑（Subjects/Policies/AppSettings 的 CRUD 曾漏调）。

**3. 双写的时间字段（`get_time_layout_entity` / `set_time_layout_entity`）**
`TimeLayoutItem` 必须同时输出：
- `startSecond` / `endSecond`：ISO datetime 字符串 —— **WebUI 编辑器读这个**
- `startTime` / `endTime`：`HH:mm:ss` 的 TimeSpan 字符串 —— **ClassIsland 2.1 客户端读这个**

回写时两者都要接受（先试 `startSecond`，再试 `startTime`）。

---

## 与上游的差异（改代码前务必读）

这些是**有意为之**的偏离，不要在"对齐上游"时改回去：

1. **`ClientRegister` 豁免会话校验。** 上游拦截器只豁免 Handshake 服务，但真实 2.x
   客户端是「先注册后握手」（`RegisterAsync` 用 `GetMetadata(true)`，`session` 头为空）。
   照抄上游会让真实客户端永远注册失败。见 `OUT_OF_SESSION_SERVICE_PREFIXES`。
2. **`ListenCommand` 流式方法也做协议/会话校验。** C# 拦截器只覆盖一元方法。
3. **Audit / ConfigUpload 返回 `Retcode.Success`。** 上游是 `// todo` 的默认对象（`0`）。
4. **manifest 补 2.1 字段**：`coreVersion: "2.0.0.0"`、`componentsSource`、`credentialSource`。
   缺 `coreVersion` 或主版本 ≠ 2 时，2.1 客户端直接弹「集控核心版本不兼容」中止加入。
5. **`ClassPlan.associatedGroup` 固定为 `acaf4ef0-e261-4262-b941-34ea93cb4369`**。
   客户端用它与 `SelectedClassPlanGroupId` 比对筛选可见课表；返回服务端的档案分组 id
   会导致客户端**看不到任何课表**。`groupId` 字段另存，供 WebUI 编辑用。
6. **`ci_get()` 大小写不敏感读取。** ClassIsland 导出的档案是 PascalCase，WebUI 发
   camelCase；上游 ASP.NET Core `[FromBody]` 默认大小写不敏感，Python 侧必须显式处理。
7. **`client_configure` 输出 PascalCase。** 客户端用 `ConfigureFileHelper.LoadConfig<T>`
   读该文件，其 `JsonSerializerOptions` 是**默认选项（大小写敏感）**。输出 camelCase
   会被静默丢弃成默认值。
8. **对象 CRUD 补通知。** 上游 Subjects/Policies/AppSettings 控制器不发通知，导致客户端
   永远拿不到更新。这里补齐了。

---

## 环境搭建（从零）

工作区自带 `setup/miniconda.exe`（Miniconda 安装包，走官方渠道下载亦可）。

```powershell
# 1. 静默安装到工作区（不写 PATH、不注册 Python）
Start-Process -FilePath ".\setup\miniconda.exe" -Wait -ArgumentList `
  "/InstallationType=JustMe","/RegisterPython=0","/AddToPath=0","/S","/D=$PWD\miniconda3"

# 2. Anaconda 默认源需要先接受 ToS，否则 create 直接报 CondaToSNonInteractiveError
$conda = "$PWD\miniconda3\Scripts\conda.exe"
& $conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
& $conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
& $conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2

# 3. 建环境
& $conda create -y -n man python=3.12

# 4. 装依赖（国内网络可先设代理）
$env:HTTP_PROXY = "http://127.0.0.1:7890"; $env:HTTPS_PROXY = $env:HTTP_PROXY
.\miniconda3\envs\man\python.exe -m pip install `
  fastapi uvicorn sqlalchemy pydantic pyjwt bcrypt grpcio grpcio-tools `
  aiofiles httpx python-multipart pgpy cryptography pymysql nuitka

# 5. 自检
.\miniconda3\envs\man\python.exe -c "import grpc, pgpy, httpx, fastapi, sqlalchemy, nuitka; print('deps OK')"
```

> ⚠️ 系统上**不需要** `python` 在 PATH 里；所有命令都用环境内的绝对路径。

## 从源码运行

```powershell
$env:PYTHONPATH = "$PWD\protos"          # 必需，否则 import Protobuf 失败
.\miniconda3\envs\man\python.exe main.py --development
```

⚠️ **不要让服务端进程随调用结束而退出**：用后台作业（`run_in_background`）或
`Start-Process`。用 pwsh 的 `Start-Job` 会随 pwsh 结束被杀。

⚠️ **重启前先确认端口释放**：`Get-NetTCPConnection -State Listen -LocalPort 7878,7879`
→ `Stop-Process -Id <pid> -Force`，等 2–3 秒。否则 7879 报
`RuntimeError: Failed to bind to address` / gRPC `WSA Error 10048`。

## 编译（Nuitka）

```powershell
# 1) 先停掉正在运行的 exe，否则 Nuitka 收尾会 PermissionError: [Errno 13]
Get-Process ManagementServer -ErrorAction SilentlyContinue | Stop-Process -Force
# 2) 清掉所有 __pycache__，否则 Nuitka 会崩在 AssertionError（见下）
Get-ChildItem app,tests,protos -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force out -ErrorAction SilentlyContinue
cd $PWD; cmd /c build_exe.bat
```

⚠️ **`AssertionError: ...\out\main.build\module.Protobuf.c`**（`nuitka\tree\SourceHandling.py`
`assert not os.path.isfile(filename)`）几乎总是 `protos\__pycache__` 之类的旧缓存导致的
模块重复注册，清掉所有 `__pycache__` 与 `out\` 后重跑即可。

产物：`out\main.dist\ManagementServer.exe`（约 112 MB，整目录约 162 MB）。

`build_exe.bat` 已经在做两件容易忘的事：
- `set PYTHONPATH=%~dp0protos` —— 否则 `FATAL: Error, failed to locate package 'Protobuf'`
- 编译后从 `miniconda3\envs\man\Library\bin` 复制 **10 个 DLL** 到产物目录

### ⚠️ 缺 DLL 的症状（排障速查）

| 缺失 | 症状 |
| --- | --- |
| `ffi-8.dll` / `ffi-7.dll` / `ffi.dll` | **静默 exit 3，无任何输出**。`import ctypes` 失败 → `click` 失败 → `uvicorn.server` 连带失败 |
| `libssl-3-x64.dll` / `libcrypto-3-x64.dll` | exit 1 + `ImportError` (ssl) |
| `sqlite3.dll` | exit 1 + `ImportError` (sqlite3) |

排查手段：`[System.Diagnostics.ProcessStartInfo]` + `RedirectStandardOutput/Error`
才能拿到输出（`& exe *>&1` 和 `cmd /c` 都拿不到）。

### 制作发行包

```powershell
robocopy out\main.dist release /E /XD data      # 排除 data，首次启动自动建库
# 再把自包含的 setup.ps1 / setup.sh / start.ps1 / start.sh / README.md 放进 release\
```

发行包里的脚本用**自身所在目录**定位 exe（`Split-Path -Parent $MyInvocation.MyCommand.Path`、
`$(dirname "${BASH_SOURCE[0]}")`），所以整个文件夹可以任意移动。

---

## 测试矩阵

服务端必须先启动（源码或编译产物均可）。全部套件都能在**全新空数据库**上直接跑，
不需要任何手工前置——它们会自己注册客户端、自己播种组织名和演示档案。

想一条命令跑完全部验收，用 `pwsh -File tests/verify_release.ps1`：它自己冷启动
`release\ManagementServer.exe`（先清 `data\`）、检查 WebUI 静态托管与 `root/root`
登录，再依次调用下表六套测试，最后打印 PASS/FAIL 汇总并以退出码反映结果。
已经有实例在跑时加 `-SkipStart` 复用。**这是发布前唯一需要手动执行的命令。**

| 套件 | 命令 | 断言数 | 需要 |
| --- | --- | --- | --- |
| REST e2e | `python tests/rest_e2e.py` | ~60 | — |
| gRPC e2e | `python tests/grpc_e2e.py` | 14 | — |
| 客户端模拟 | `python tests/client_sim.py` | 39 | — |
| 真实契约 | `pwsh -File tests/contract_test.ps1` | 24 | 真实 `ClassIsland.Shared.dll` |
| C# gRPC 互通 | `tests/grpc_interop/bin/Release/net8.0/GrpcClientInterop.exe --grpc http://127.0.0.1:7879 --http http://127.0.0.1:7878` | 22 | dotnet SDK + 客户端程序集 |
| 路由一致性 | `python tests/route_diff.py` | 74 | `webui-src/src/api/apiDefinitions.ts` |

**关键设计**：
- `contract_test.ps1` 用**反射加载真实 `ClassIsland.Shared.dll`**，按客户端完全相同的
  `JsonSerializerDefaults.Web` 反序列化服务端响应。字段名/类型/枚举值有任何偏差都会抛异常。
  这比"看起来像 JSON"强得多。
- `GrpcClientInterop` 同样引用客户端自带的 `Google.Protobuf` / `Grpc.Net.Client` / `PgpCore`，
  所以 PGP 握手是真的加解密（不是打桩）。
- 两个 C# 项目都用 `ClientBin` 定位客户端产物，可用
  `dotnet build -p:ClientBin=<path>` 或环境变量 `CLASSISLAND_CLIENT_BIN` 覆盖。

⚠️ **本机有系统代理时测试会全线失败**：Windows「Internet 选项」里配了代理而
`ProxyOverride` 不含 `127.0.0.1` 时，`Invoke-WebRequest`、`httpx`、
`urllib.request`、`GrpcChannel` 都会把 loopback 请求发给代理，拿回**空 body 的 404**，
表现为「所有接口都 404」这种假故障。各套件已内置绕过：

- `tests/rest_e2e.py` → `urllib.request.build_opener(urllib.request.ProxyHandler({}))`
- `tests/client_sim.py` → `httpx.Client(..., trust_env=False)`
- `tests/contract_test.ps1`、`tests/seed_demo_profile.ps1` → `-NoProxy`
- `tests/grpc_interop/Program.cs` → `SocketsHttpHandler { UseProxy = false }`

新写脚本时照抄对应做法，否则会在装了代理的机器上得到无法解释的 404。

### WebUI 浏览器验证

```powershell
pwsh -NoProfile -File tests\ui_sweep.ps1 -Session <bsk session>
```

用 browser-skill（bsk）驱动真实 Edge 逐页巡检 14 个页面：渲染、控制台错误、
4xx/5xx 请求、截图（`tests/screenshots/`）。

**bsk 使用要点**：`bsk_*` 内置工具在动作后会要求 cooperate context 且无法传参，
脚本化请走 CLI —— `bsk cooperate sync` 取 `context_id`，`bsk step --context` 执行，
返回的 `post.context_id` 可直接给下一个动作。`ui_sweep.ps1`、`bsk.ps1`、`bskchain.ps1`
已封装这套流程，bsk 不在默认位置时用 `-BskPath` 或 `BSK_PATH` 指定。

---

## 真实客户端联调

客户端产物在 `C:\ClassIsland-debug\ClassIsland.Desktop\bin\Debug\net8.0-windows10.0.19041.0`
（可用 `CLASSISLAND_CLIENT_BIN` 覆盖）。三个必踩的坑：

1. **客户端启动即崩**（`FileNotFoundException: The corresponding XAML file could not be found`
   → `App.axaml.cs`）。原因是 HotAvalonia 会检查 `C:\MoreSplashScreen-<hash>\ClassIsland-<ver>\`
   下是否存在源文件路径。**修复：把 `ClassIsland\App.axaml.cs` 和
   `ClassIsland.Desktop\Program.cs` 按相同相对路径复制过去**（它只检查存在性）。
2. **`ServerKey.asc` 不会自动生成。** 客户端只在 UI「加入集控」流程里写这个文件；
   手工注册后必须跑 `python tests/export_server_key.py --db <db>`，否则 `ListenCommand`
   抛 `FileNotFoundException`。
3. **MAC 地址取自首个「非 Loopback + Up + 有 IPv4」的网卡**，实际可能命中
   `vEthernet (Default Switch)` 而不是 WLAN。注册时 MAC 必须与客户端自算的一致，
   否则 `BeginHandshake` 返回 `HandshakeClientRejected`。

**日志**：`<客户端 bin>\Logs\log-YYYY-M-D-HH-mm-ss-1.log`（日期不补零，量极大）。
**只筛选不整读**：`Select-String -Path $log -Pattern "握手成功|成功拉取集控档案|接受指令"`
取 `.Line`。关键行形如：
`与 http://127.0.0.1:7879 握手成功，SessionId：...`、`成功拉取集控档案！`、
`注册提醒提供方：...（集控提醒）`、`接受指令：[SendNotification]`。

**通知有约 30–50 秒延迟**：命令排在客户端下一次流读取周期，不是缺陷。
**重启验证**：发 `restart-app` 前记 PID，25 秒后对比，变了才算通过。

---

## 修改代码时的检查清单

- [ ] 改了对象 CRUD？→ 确认调用了 `notify_object_updating` / `notify_client_updating`
- [ ] 改了实体字段？→ 确认 `to_json()` 输出 camelCase，且不破坏真实客户端的反序列化
- [ ] 改了时间表字段？→ 保持 `startSecond`+`startTime` 双写
- [ ] 改了 REST 路由？→ 跑 `tests/route_diff.py`（74 条 WebUI 路由必须全部命中）
- [ ] 改了 manifest / policy / 档案分发？→ 跑 `tests/contract_test.ps1`
- [ ] 改了 gRPC？→ 跑 `tests/grpc_e2e.py` + `GrpcClientInterop`
- [ ] 要发布？→ 停掉 exe → `build_exe.bat` → 对产物重跑全部套件 → 重新 `release\`

**提交前务必确认不要带入**（`.gitignore` 已覆盖）：`data/`（含 `management.db` 与
`appsettings.json`，可能有数据库口令与 PGP 私钥）、`out/`、`release/`、`miniconda3/`、
`vendor/`、`webui-src/node_modules/`、任何 `*.log` / `_*.py` 临时脚本。

---

## 上游参考代码

C# 参考实现不在本仓库（体积与许可考虑）。需要对照时克隆到 `vendor/`：

```powershell
git clone https://github.com/ClassIsland/ManagementServer.git vendor/ManagementServer
```

`vendor/` 已在 `.gitignore` 中。读代码的入口：
- `ClassIsland.ManagementServer.Server/Services/ProfileEntitiesService.cs` — 档案实体 CRUD 的权威语义
- `.../Services/ObjectsCacheService.cs`、`.../Services/ObjectsUpdateNotifyService.cs` — 缓存与版本通知
- `.../Services/ObjectsAssigneeService.cs` — 分发目标的匹配规则
- `.../Services/Grpc/HandshakeService.cs`、`.../Services/GrpcInterceptors/CyreneMspFrontedInterceptor.cs` — gRPC 契约
- `.../Controllers/Clients/ManifestController.cs` — 版本号递增逻辑
- `.../Controllers/Clients/ObjectsDeliveryController.cs` — 档案/策略/设置分发的输出形状
- `classisland.managementserver.client/` — WebUI 前端源码（`src/api/apiDefinitions.ts` 是路由契约）

真实客户端的权威契约在 [ClassIsland/ClassIsland](https://github.com/ClassIsland/ClassIsland)：
`ClassIsland/Services/Management/ManagementService.cs`（版本号消费与加入流程）、
`ClassIsland/Services/ProfileService.cs`（档案合并）、
`ClassIsland.Shared/Models/Management/*`（manifest / policy / ReVersionString）、
`ClassIsland.Shared/Models/Profile/TimeLayoutItem.cs`（时间字段双轨）。
