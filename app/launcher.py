"""Application assembly and process entry point.

Mirrors ``Program.cs``: build the FastAPI application, register every router,
serve the built WebUI from ``app/static`` (falling back to ``index.html``) and
start the gRPC server next to it.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig, resolve_root
from .db import ALL_ROLES, ROLE_ADMIN, Database, User, UserRole, get_database
from .deps import build_profile_service, error
from .grpc_services import create_server
from .middleware import SessionMiddleware, install_error_handlers
from .models import new_guid, now
from .routers.client_groups import client_groups_router
from .routers.clients import delivery_router, manifest_router, registry_router
from .routers.commands import commands_router
from .routers.core import (
    assignees_router,
    auth_router,
    default_settings_router,
    policies_router,
    settings_router,
)
from .routers.profiles import profiles_router
from .routers.users import users_router
from .services import (
    CyreneMspConnectionService,
    ObjectsCacheService,
)

PROJECT_ROOT = resolve_root()


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or AppConfig.load(PROJECT_ROOT)
    database = get_database(config)

    app = FastAPI(title="ClassIsland ManagementServer", version="1.0.0")
    app.state.config = config
    app.state.database = database
    app.state.cache = ObjectsCacheService(config.cache_capacity)
    app.state.connections = CyreneMspConnectionService()

    app.add_middleware(SessionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    for router in (
        auth_router,
        settings_router,
        default_settings_router,
        policies_router,
        assignees_router,
        profiles_router,
        registry_router,
        client_groups_router,
        manifest_router,
        delivery_router,
        commands_router,
        users_router,
    ):
        app.include_router(router)

    _mount_static(app, config)
    return app


def _mount_static(app: FastAPI, config: AppConfig) -> None:
    static_dir = config.static_directory
    index_file = os.path.join(static_dir, "index.html")

    if os.path.isdir(static_dir):
        assets = os.path.join(static_dir, "assets")
        if os.path.isdir(assets):
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):  # noqa: ANN202 - FastAPI handler
            candidate = os.path.join(static_dir, full_path.replace("/", os.sep))
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            if os.path.isfile(index_file):
                return FileResponse(index_file)
            return JSONResponse(status_code=404, content=error("找不到请求的对象"))


def prepare_database(database: Database) -> None:
    """Create the schema, seed default rows and register the known roles."""
    from sqlalchemy.exc import OperationalError, SQLAlchemyError

    try:
        database.migrate()
        database.setup_database()
    except (OperationalError, SQLAlchemyError) as exc:
        # A bare SQLAlchemy traceback tells an end user nothing.  Upstream just
        # crashes; here the failure mode and the fix are spelled out.
        raise DatabaseUnavailable(database.url, exc) from exc


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured database cannot be reached."""

    def __init__(self, url: str, cause: BaseException) -> None:
        self.url = url
        self.cause = cause
        super().__init__(self.describe())

    def describe(self) -> str:
        safe_url = self.url
        if "@" in safe_url:
            head, tail = safe_url.rsplit("@", 1)
            if "://" in head:
                safe_url = head.split("://", 1)[0] + "://***@" + tail
        if safe_url.startswith("mysql"):
            hint = (
                "配置要求使用 MySQL，但无法连接到数据库服务器。\n"
                "  如果你没有 MySQL，请把 data/appsettings.json 的 "
                '"DatabaseType" 改成 "sqlite"（或删除 data 目录后重新运行 --setup=true 并选择 sqlite）。'
            )
        else:
            hint = "无法打开 SQLite 数据库文件，请检查 data 目录的写入权限。"
        detail = str(self.cause).strip().splitlines()[0] if str(self.cause).strip() else ""
        return f"{hint}\n  数据库：{safe_url}\n  原始错误：{detail}"


def ensure_admin_line(database: Database) -> None:
    """Create the ``root`` account with every role, like ``Setup.Phase2``."""
    with database.open() as session:
        if session.query(User).count() > 0:
            return

        password = os.environ.get("MANAGEMENT_ROOT_PASSWORD") or "root"
        from .security import hash_password

        user = User(
            Id=new_guid(),
            UserName="root",
            NormalizedUserName="ROOT",
            Name="root",
            PasswordHash=hash_password(password),
            SecurityStamp=new_guid().replace("-", ""),
            AllowChangePassword=1,
            CreatedTime=now(),
            UpdatedTime=now(),
        )
        session.add(user)
        session.flush()
        for role in ALL_ROLES:
            session.add(UserRole(UserId=user.Id, RoleId=role))
        session.flush()


def run(argv: list[str] | None = None) -> int:
    import uvicorn

    config = AppConfig.load(PROJECT_ROOT, argv)

    # ``--setup=true`` writes the configuration before anything else, exactly
    # like ``Setup.SetupPhase1(builder)`` in ``Program.cs``.
    if config.setup_mode:
        from .setup_wizard import setup_phase1

        if not setup_phase1(config):
            return 0
        config = AppConfig.load(PROJECT_ROOT, argv)

    database = get_database(config)
    prepare_database(database)

    if config.migrate_mode:
        print("已完成数据库迁移，应用即将退出。", flush=True)
        return 0

    connections = CyreneMspConnectionService()
    with database.open() as session:
        connections.init_server_key(session)

    if config.setup_mode:
        from .setup_wizard import setup_phase2

        with database.open() as session:
            has_users = session.query(User).count() > 0
        if not has_users:
            setup_phase2(database)
    else:
        ensure_admin_line(database)

    app = create_app(config)
    app.state.connections.server_public_key_armored = connections.server_public_key_armored
    app.state.connections.server_key = connections.server_key

    grpc_port = config.grpc_host_port[1]
    server = create_server(database, app.state.connections, grpc_port)
    server.start()
    print(f"[grpc] listening on 0.0.0.0:{grpc_port}", flush=True)

    host, port = config.api_host_port
    print(f"[api ] listening on http://{host}:{port}", flush=True)
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    finally:
        server.stop(grace=0)
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":  # pragma: no cover - manual entry
    sys.exit(main())
