# ClassIsland 集控服务器（Python 重写版）

[ClassIsland/ManagementServer](https://github.com/ClassIsland/ManagementServer) 的 Python 重写实现。
原项目是 ASP.NET Core 8 + MySQL + EF Core；本实现使用 **FastAPI + SQLAlchemy + grpcio**，行为与
原版逐一对齐（含 gRPC 协议、PGP 握手、分页语义、错误消息），并额外兼容 **ClassIsland 2.1** 的
新版 JSON 契约（`coreVersion`、`startTime/endTime`、`credentialSource` 等）。

- WebUI / REST：**http://localhost:7878**
- gRPC：**http://localhost:7879**
- 数据库：默认 SQLite（`data/management.db`），也支持 MySQL（`databaseType: "mysql"`）

---

## 功能对照（对照上游 README.md）

### 管理后端

- [x] 实例注册与获取 —— gRPC `ClientRegister.Register/UnRegister`，REST `/api/v1/clients_registry/*`
- [x] 实例分组 —— `/api/v1/client_groups/*`（默认组 `1`、全局组 `-1` 不可删除）
- [x] 上传档案 —— `POST /api/v1/profiles/upload`

### 数据分发

- [x] 按实例与分组拼接数据 —— `ObjectsAssigneeService.get_assigned_clients()`
  （`targetGroupId == -1` 直接命中全部客户端；否则按 ClientUid / Id / Group 匹配）
- [x] 分发策略 —— `GET /api/v1/client/{cuid}/policy`
- [x] 分发设置信息 —— `GET /api/v1/client/{cuid}/default-settings`
- [x] 分发档案信息 —— `GET /api/v1/client/{cuid}/{subjects,timelayouts,classplans}`
- [x] 使用 grpc 向客户端发送命令 —— `ListenCommand` 双向流 + `/api/v1/client-commands/*`
  - [x] 向客户端发送提醒 —— `POST /api/v1/client-commands/show-notification`
  - [x] 通知客户端更新数据 —— `POST /api/v1/client-commands/restart-app`（已用真实客户端验证进程重启）

> 上游 README 中这两个子项原本未勾选，此处已实现并用真实客户端联调通过。

### API

- [x] API 返回分页 —— `PaginatedList<T>`：`pageIndex` / `totalPages` / `pageSize` / `itemCount`
      / `items` / `hasPreviousPage` / `hasNextPage`；`pageIndex <= 0` 抛 `Page index should larger than 0`

### WebUI

- [x] 批量创建对象
- [x] 管理并分组实例
- [x] 管理并分组档案（课表、时间表、科目）信息
- [x] 上传档案信息
- [x] 管理并分组策略
- [x] 管理并分组默认设置

> 前端静态资源（`C:\man\webui-src` 构建产物）内嵌在 `app/static/`，随 exe 一起分发，
> 访问 `/` 即进入 WebUI，SPA 路由自动回落到 `index.html`。

### 用户

- [x] 用户创建与管理 —— `/api/v1/users/*`
- [x] 用户鉴权 —— `POST /api/v1/auth/login|refresh|logout`（JWT，`Authorization: Bearer`）
- [x] 用户角色（管理员、教师、访客等）—— 7 个内置角色，`require_roles()` 依赖注入

未实现项（上游本身也标为未完成）：从表格导入课表。

> **导入外部档案的兼容性**：ClassIsland 客户端导出的档案是 **PascalCase**
> （`{"Subjects": {... "Name": ...}}`），而 WebUI 自身发送 camelCase。服务端读取
> 档案字段时统一走 `app/models.py` 的 `ci_get()`（大小写不敏感），与上游
> ASP.NET Core `[FromBody]` 的 `PropertyNameCaseInsensitive = true` 行为一致，
> 因此两种命名都能正确导入。`tests/sample_ui_profile.json` 是一份最小 PascalCase
> 样本，可用于回归该行为。

---

## 快速开始

### 1. 安装向导

```powershell
.\setup.ps1      # Windows
./setup.sh       # Linux / macOS
```

向导会交互式写入 `data/appsettings.json`，并创建管理员账号与 7 个角色。

提问顺序：**① 数据库类型（默认 `sqlite`）→ ② 仅 mysql 时填连接信息并试连 → ③ WebUI/API 地址 →
④ gRPC 地址 → ⑤ root 密码（两次）**。选了 mysql 但连不上时，向导会显示原因并询问是否重新填写，
不会写出一个连不上的配置。

也可以非交互运行（已有配置文件时直接跳过向导）：

```powershell
.\out\main.dist\ManagementServer.exe --setup=true
```

### 2. 启动

```powershell
.\start.ps1
```

或直接运行编译产物：

```powershell
cd out\main.dist
.\ManagementServer.exe
```

首次启动会自动建库、建表、播种默认数据（默认分组 `#00f1f1`、全局分组 `#ff8500`、
默认档案组 `00000000-0000-0000-0000-000000000001`）并创建 `root/root`。

浏览器打开 <http://localhost:7878>，用 `root/root` 登录。

### 3. 客户端接入

在 ClassIsland 2.x 的「集控」设置里填写：

| 项目 | 值 |
| --- | --- |
| 服务地址（HTTP） | `http://<服务器地址>:7878` |
| 服务地址（gRPC） | `http://<服务器地址>:7879` |

客户端会先 gRPC `Register`，再用 PGP 完成 `BeginHandshake`/`CompleteHandshake` 建立会话，
随后拉取 manifest 并按版本号增量拉取科目 / 时间表 / 课表 / 策略 / 默认设置。

---

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--setup=true` | 运行安装向导（无配置文件时自动触发） |
| `--migrate=true` | 只做数据库迁移后退出 |
| `--development` | 开发模式（`ASPNETCORE_ENVIRONMENT=development`） |

配置文件 `data/appsettings.json`：

```json
{
  "ConnectionStrings": { "Production": "Host=localhost;Uid=root;Password=;Database=classisland_management;Port=3306" },
  "Kestrel": {
    "Endpoints": {
      "api":  { "Url": "http://localhost:7878", "Protocols": "Http1" },
      "grpc": { "Url": "http://localhost:7879", "Protocols": "Http2" }
    }
  },
  "DatabaseType": "sqlite",
  "CacheCapacity": 1024
}
```

改为 MySQL 只需把 `DatabaseType` 设为 `"mysql"` 并填写 `ConnectionStrings.Production`。

---

## 构建（Nuitka）

```powershell
.\build_exe.bat
```

- 需要 `miniconda3\envs\man` 环境（重建方式见 [AGENT.md](AGENT.md)）；脚本会设置
  `PYTHONPATH=%~dp0protos`（否则找不到 `Protobuf` 包）
- 产物：`out\main.dist\ManagementServer.exe`（约 110 MB，整目录约 160 MB）
- 脚本会自动从 conda 的 `Library\bin` 复制 **libffi / libssl / sqlite3 / zlib** 等 10 个 DLL 到产物目录。
  缺少 `ffi-*.dll` 时 exe 会**静默 exit 3**（`import ctypes` 失败 → `click` 失败 → `uvicorn` 连带失败），
  这是 standalone 模式最容易踩的坑

---

## 发行包（release\）

`release\` 是可直接分发给最终用户的自包含目录（108 个文件 / 约 162 MB）。
发布到 GitHub Release 时打包成 `ClassIsland-ManagementServer-Python-win64.zip`（约 57 MB）。

```
ManagementServer.exe    服务端主程序（含全部 Python 运行时）
static\                 WebUI 前端静态资源（54 个文件）
*.dll / *.pyd           Python 运行时与扩展模块（含 ffi-8/ffi-7/ffi、libssl、libcrypto、sqlite3 等）
README.md               面向最终用户的说明（含向导提问顺序）
setup.ps1 / setup.sh    首次安装向导（内部自动加 --setup=true）
start.ps1 / start.sh    服务启动器（参数原样透传）
```

- 脚本用自身所在目录定位 `ManagementServer.exe`，因此**整个文件夹可以任意移动**。
- 不含 `data\`：首次启动自动创建 `data\management.db` 并播种默认账号 `root/root`。
- `release\ManagementServer.exe` 与 `out\main.dist\ManagementServer.exe` 的 SHA256 一致
  （`EB968DF94D28A0A52AA43D9D0C7BD98085419E865CD8172EB1BFE07BC5E321C3`，112,467,968 B），
  因此六套测试对 `out` 产物跑通即对 release 有效。
- 已验证：`.\start.ps1` 冷启动 → `root/root` 登录 200、WebUI `/` 200；
  在纯净副本上 `ManagementServer.exe --setup=true` 一路回车走完向导（默认 sqlite）→
  写入的 `DatabaseType` 为 `"sqlite"`，向导输入的密码可登录、`root/root` 被拒（证明向导生效）。

---

## 测试

全部测试都可以直接对编译产物运行（先启动服务端）。

| 测试 | 命令 | 覆盖 |
| --- | --- | --- |
| REST e2e | `python tests/rest_e2e.py` | 约 60 项：全部 REST 路由、鉴权、分页、CRUD |
| gRPC e2e | `python tests/grpc_e2e.py` | 14 项：协议头校验、注册、握手、会话、命令流、注销 |
| 客户端模拟 | `python tests/client_sim.py` | 39 项：模拟 ClassIsland 的拉取流程与错误分支 |
| 真实契约 | `pwsh -File tests/contract_test.ps1` | 24 项：加载**真实** `ClassIsland.Shared.dll` 反序列化 |
| C# gRPC 互通 | `tests/grpc_interop/bin/Release/net8.0/GrpcClientInterop.exe --grpc http://127.0.0.1:7879 --http http://127.0.0.1:7878` | 22 项：用客户端自带程序集验证 PGP 握手与命令投递 |
| 路由一致性 | `python tests/route_diff.py` | 74 条 WebUI 路由与服务端 OpenAPI 逐一比对 |

### WebUI 浏览器验证（browser-skill / bsk）

```powershell
# 14 个页面逐个巡检：渲染 / 控制台错误 / 4xx·5xx 网络请求 / 截图
pwsh -NoProfile -File tests\ui_sweep.ps1
```

已用真实浏览器（Edge + browser-skill）验证：14 个页面全部正常渲染且无控制台错误；
「档案 → 上传」页选择文件 → 「上传成功」→ 科目/时间表/课表均落库；
科目的新建 / 编辑 / 删除、策略创建、广播提醒投递、远程重启实例均端到端可用。
界面截图见 `tests/screenshots/`。

> bsk 的 `bsk_*` 内置工具在动作后会要求 cooperate context，脚本化操作请走 CLI：
> `bsk cooperate sync` 取 context → `bsk step --context` 执行并复用返回的 `post.context_id`。

两个辅助脚本：

```powershell
# 契约测试需要一个已注册的客户端（gRPC 注册，可重复调用）
.\miniconda3\envs\man\python.exe tests\register_client.py

# 手工注册真实客户端后，把它缺少的服务器公钥写进客户端管理目录
.\miniconda3\envs\man\python.exe tests\export_server_key.py
```

`tests/contract_test.ps1`、`tests/rest_e2e.py` 等会**自己注册**所需客户端并写入组织名，
因此可以在全新的空数据库上直接运行，无需任何前置手工操作。`tests/seed_demo_profile.ps1`
则用于给真实客户端播种一套演示档案（科目 / 时间表 / 课表并分配到指定 CUID）。

重建 C# 互通测试：

```powershell
cd tests\grpc_interop
& 'C:\Program Files\dotnet\dotnet.exe' build -c Release
# 客户端产物不在默认位置时：
# dotnet build -c Release -p:ClientBin=D:\path\to\ClassIsland\bin\Debug\net8.0-windows10.0.19041.0
```

### 真实 ClassIsland 2.1 客户端联调

用 `C:\ClassIsland-debug` 里的客户端做过完整验证（注册 → PGP 握手 → 拉取档案
→ 接收通知 → 远程重启）。目录不同时用 `-SharedDll` 参数或 `CLASSISLAND_CLIENT_BIN`
环境变量指定客户端产物目录。手工联调步骤：

1. 服务端启动后注册客户端（CUID 取自客户端 `%LOCALAPPDATA%\ClassIsland\Management\Persist.json`
   的 `ClientUniqueId`，MAC 取客户端首个非回环网卡）：

   ```powershell
   .\miniconda3\envs\man\python.exe tests\register_client.py --cuid <CUID> --id <设备ID> --mac <MAC>
   .\miniconda3\envs\man\python.exe tests\export_server_key.py
   ```

2. 客户端 `%LOCALAPPDATA%\ClassIsland\Management\Settings.json` 填入：

   ```json
   {"IsManagementEnabled":true,"ManagementServerKind":1,
    "ManagementServer":"http://127.0.0.1:7878","ManagementServerGrpc":"http://127.0.0.1:7879",
    "ManifestUrlTemplate":"","ClassIdentity":"test-class","IsActive":false}
   ```

3. 播种档案并分配：`pwsh -File tests/seed_demo_profile.ps1`

4. 启动客户端，约 35 秒后检查
   `%LOCALAPPDATA%\ClassIsland\Management\Versions.json` 的版本号是否被服务端推高。

> `ServerKey.asc` 只在客户端 UI「加入集控」流程里自动写入；手工注册必须跑
> `tests/export_server_key.py`，否则客户端 `ListenCommand` 会因找不到公钥而崩溃。

---

## 与上游的差异（有意为之）

1. **`ClientRegister` 豁免会话校验。** 上游的 `CyreneMspFrontedInterceptor` 只豁免 Handshake
   服务，但真实 2.x 客户端是**先注册后握手**（`ManagementServerConnection.RegisterAsync` 用
   `GetMetadata(true)`，session 头为空），照抄上游会让真实客户端永远注册失败。这里把
   `ClientRegister` 一并加入 `OUT_OF_SESSION_SERVICE_PREFIXES`。
2. **`ListenCommand` 流式方法也做协议与会话校验。** C# 拦截器只覆盖一元方法，流式方法实际上
   没有保护；这里补上了。
3. **Audit / ConfigUpload 返回 `Retcode.Success`。** 上游是 `// todo` 的默认对象
   （`Unspecified = 0`）。
4. **manifest 增加 2.1 字段**：`coreVersion: "2.0.0.0"`、`componentsSource`、`credentialSource`。
   缺少 `coreVersion` 或主版本号不是 2 时，2.1 客户端会直接弹「集控核心版本不兼容」并中止加入。
5. **`TimeLayoutItem` 同时输出新旧两套字段**：`startSecond`/`endSecond`（ISO 字符串，WebUI 用）
   与 `startTime`/`endTime`（`HH:mm:ss` TimeSpan 字符串，2.1 客户端用）。
6. **`ClassPlan.associatedGroup` 固定指向默认课表组** `acaf4ef0-e261-4262-b941-34ea93cb4369`，
   客户端 `LessonsService` 用它和 `SelectedClassPlanGroupId` 比对来筛选可见课表；若返回服务端
   的档案分组 id，客户端会看不到任何课表。同组的 `groupId` 字段仍保留供 WebUI 编辑。

---

## 目录结构

```
<repo>
├── app\                    服务端源码
│   ├── config.py           配置解析（appsettings.json / 命令行）
│   ├── db.py               SQLAlchemy 引擎、迁移、建库种子
│   ├── models.py           全部实体（输出 camelCase）
│   ├── services.py         业务逻辑（分发、缓存、PGP 会话、命令队列）
│   ├── grpc_services.py    gRPC 五个服务 + 协议/会话拦截器
│   ├── security.py         bcrypt + JWT + 角色校验
│   ├── setup_wizard.py     安装向导
│   ├── launcher.py         uvicorn + gRPC 双端口启动
│   ├── static\             WebUI 静态资源（构建产物）
│   └── routers\            REST 路由（clients / profiles / users / commands / ...）
├── protos\Protobuf\        由上游 .proto 生成的 pb2 模块
├── tests\                  六套测试 + 辅助脚本 + 演示档案播种 + WebUI 巡检脚本
├── webui-src\              WebUI 前端源码（构建到 app\static）
├── build_exe.bat           Nuitka 构建脚本
├── main.py                 进程入口
├── setup.ps1 / setup.sh    安装向导启动器
├── start.ps1 / start.sh    服务启动器
├── AGENT.md                面向 AI 智能体的代码思路与编译教程
├── NOTICE                  归属与第三方组件声明
└── LICENSE                 AGPL-3.0 全文

# 以下目录不入库（.gitignore 已覆盖）
├── out\main.dist\          Nuitka 编译产物
├── release\                发行包
├── miniconda3\             项目自带的 conda 环境
├── data\                   运行时生成（appsettings.json / management.db）
└── vendor\                 上游 C# 参考实现（按需克隆）
```

---

## 许可证与出处

本项目以 **GNU Affero General Public License v3.0（AGPL-3.0）** 发布，全文见
[LICENSE](LICENSE)，归属与第三方组件声明见 [NOTICE](NOTICE)。

### 基于 ClassIsland.ManagementServer 修改

本仓库是 [**ClassIsland/ManagementServer**](https://github.com/ClassIsland/ManagementServer)
的**修改版本**（Python 重写实现），并非原创项目：

- 上游项目：<https://github.com/ClassIsland/ManagementServer>
- 上游版权：Copyright (C) ClassIsland and contributors
- 上游许可证：AGPL-3.0（与本项目相同）
- 参照的上游提交：`66aebd26b7c5131acc115b59d58b64b19d7c1311`（2026-01-27）

数据模型、gRPC 协议、错误语义与大量业务逻辑均移植自上游 C# 实现。由于 AGPL-3.0
具有传染性，本衍生作品同样以 AGPL-3.0 授权——如果你修改并部署本项目对外提供服务，
同样需要以 AGPL-3.0 开放你的修改。

WebUI 前端来自上游内嵌的 [`jekip/naive-ui-admin`](https://github.com/jekip/naive-ui-admin)
（MIT，见 `webui-src/LICENSE`），此处仅重新分发其构建产物。

### 代码由 AI 生成

**本仓库的绝大部分源代码由 AI 编程智能体（大语言模型）生成**，依据上游 C# 源码、
ClassIsland 客户端源码与公开文档完成，随后用真实 ClassIsland 2.1 客户端和
[README 中的测试套件](#测试)做了验证。

请注意：

- 代码**未经人工逐行审阅**，也**未做过安全审计**；
- 上游自身的可用性 / 向后兼容保证**不适用于**本移植版；
- 生产环境部署前请自行审阅并评估。

仓库内还带有面向智能体的工作指南 [AGENT.md](AGENT.md)，记录代码架构、关键机制、
与上游的有意差异、环境搭建与 Nuitka 编译教程。

