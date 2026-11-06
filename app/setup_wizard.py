"""Interactive setup wizard (port of ``Setup.cs``).

``--setup=true`` runs :func:`setup_phase1` before the host is built (it writes
``data/appsettings.json``) and :func:`setup_phase2` once the database is ready
(it creates the ``root`` account and grants it every role).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .config import DEFAULT_API_URL, DEFAULT_GRPC_URL, AppConfig

CONNECTION_DEFAULTS = {
    "Host": "localhost",
    "Port": "3306",
    "Uid": "classisland_management",
    "Password": "",
    "Database": "classisland_management",
}


def _ask(prompt: str, default: str = "") -> str:
    suffix = f"（默认 {default}）" if default else ""
    try:
        value = input(f"{prompt}{suffix}：").strip()
    except (EOFError, KeyboardInterrupt):  # pragma: no cover - interactive only
        return default
    return value or default


def _ask_bool(prompt: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    try:
        value = input(f"{prompt} [{marker}]：").strip().lower()
    except (EOFError, KeyboardInterrupt):  # pragma: no cover - interactive only
        return default
    if not value:
        return default
    return value in ("y", "yes", "true", "1")


def build_connection_string() -> str:
    """Collect a MySQL connection string, either by wizard or by hand."""
    print("请选择配置方式：")
    print("  w) 使用向导逐项填写")
    print("  s) 直接输入完整的连接字符串")
    mode = _ask("配置方式", "w").lower()
    if mode.startswith("s"):
        return _ask("连接字符串", _default_connection_string())
    values = dict(CONNECTION_DEFAULTS)
    for key in ("Host", "Port", "Uid", "Password", "Database"):
        values[key] = _ask(key, values[key])
    return (
        f"Host={values['Host']};Uid={values['Uid']};"
        f"Password={values['Password']};Database={values['Database']};"
        f"Port={values['Port']}"
    )


def probe_mysql(connection_string: str, timeout: int = 5) -> tuple[bool, str]:
    """Try to open a real MySQL connection.

    Returns ``(ok, message)``.  A failed probe never aborts the wizard — the
    database may legitimately not exist yet — but it is surfaced to the user so
    a typo or a missing MySQL server is caught before the service starts.
    """
    from urllib.parse import unquote, urlparse

    from .config import _mysql_url_from_connection_string

    try:
        from sqlalchemy import create_engine, text
    except Exception as exc:  # pragma: no cover - driver always packaged
        return False, f"无法加载数据库驱动：{exc}"

    url = _mysql_url_from_connection_string(connection_string)
    parsed = urlparse(url.replace("mysql+pymysql://", "mysql://", 1))
    target = f"{parsed.hostname or 'localhost'}:{parsed.port or 3306}"
    try:
        engine = create_engine(url, connect_args={"connect_timeout": timeout})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return False, f"无法连接到 MySQL（{target}）：{detail}"
    return True, f"已成功连接 MySQL（{target}，用户 {unquote(parsed.username or '')}）"


def _default_connection_string() -> str:
    return (
        f"Host={CONNECTION_DEFAULTS['Host']};Uid={CONNECTION_DEFAULTS['Uid']};"
        f"Password={CONNECTION_DEFAULTS['Password']};"
        f"Database={CONNECTION_DEFAULTS['Database']};Port={CONNECTION_DEFAULTS['Port']}"
    )


def setup_phase1(config: AppConfig) -> bool:
    """Write ``data/appsettings.json``.  Returns ``False`` when cancelled."""
    path = config.config_path
    if os.path.exists(path) and not _ask_bool(f"配置文件 {path} 已存在，是否覆盖？", False):
        print("已取消配置。")
        return False

    print("欢迎使用 ClassIsland.ManagementServer！")
    print("让我们通过几个简单的步骤完成设置。")

    # The database type decides which of the two following questions is asked,
    # so it must come first.  Upstream asks it last with a ``mysql`` default,
    # which silently produces an unusable configuration on machines without a
    # MySQL server (the connection details have already been collected by then).
    print("\n--- 数据库 ---")
    database_type = _ask("数据库类型（mysql/sqlite，默认 sqlite）", "sqlite").lower()
    if database_type not in ("mysql", "sqlite"):
        print(f"未知的数据库类型 {database_type!r}，已回退为 sqlite。")
        database_type = "sqlite"

    connection_string = ""
    if database_type == "mysql":
        while True:
            connection_string = build_connection_string()
            ok, message = probe_mysql(connection_string)
            print(f"{'[ok]' if ok else '[!] '} {message}")
            if ok:
                break
            # Keep asking so a typo does not leave an unrunnable config behind.
            if not _ask_bool("连接失败，是否重新填写数据库连接信息？", True):
                print("将按当前连接信息保存，服务端启动时可能依然无法连接。")
                break

    print("\n--- Web ---")
    api_url = _ask("应用（WebUI、API 等）监听 URL", DEFAULT_API_URL)
    grpc_url = _ask("gRPC 监听 URL", DEFAULT_GRPC_URL)

    config.raw = {
        "ConnectionStrings": {"Production": connection_string},
        "Kestrel": {
            "Endpoints": {
                "api": {"Url": api_url, "Protocols": "Http1"},
                "grpc": {"Url": grpc_url, "Protocols": "Http2"},
            }
        },
        "DatabaseType": database_type,
        "CacheCapacity": config.cache_capacity,
    }
    config.save()
    print(f"配置已写入 {path}（数据库：{database_type}）")
    return True


def setup_phase2(database: Any) -> None:
    """Ask for the ``root`` password and create the account with every role."""
    from .db import ALL_ROLES, ROLE_ADMIN  # noqa: F401 - role ids seeded by db
    from .db import User, UserRole
    from .models import new_guid, now
    from .security import hash_password

    password = ""
    while not password:
        first = _ask("请设置 root 用户的密码", "")
        if not first:
            print("密码不可为空，请重新输入。")
            continue
        second = _ask("请再次输入密码", "")
        if first != second:
            print("两次输入的密码不一致，请重新输入。")
            continue
        password = first

    with database.open() as session:
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
    print("已创建 root 用户。")


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
