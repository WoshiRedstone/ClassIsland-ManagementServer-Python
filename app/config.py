"""Configuration handling.

Mirrors the configuration surface of the original ASP.NET Core application:

* ``./data/appsettings.json`` is the single configuration file (created by the
  setup wizard, see :mod:`app.setup`).
* Command line arguments ``--setup=true`` and ``--migrate=true`` behave like the
  original ``ConfigurationBuilder().AddCommandLine(args)``.
* ``Kestrel:Endpoints:api:Url`` is the Web/API/WebUI endpoint and
  ``Kestrel:Endpoints:grpc:Url`` the gRPC endpoint.

The WebUI endpoint defaults to port **7878** as required by the project brief.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

DEFAULT_API_URL = "http://localhost:7878"
DEFAULT_GRPC_URL = "http://localhost:7879"

APP_CONFIG_RELATIVE_PATH = os.path.join("data", "appsettings.json")


def is_compiled() -> bool:
    """True when running from a Nuitka compiled binary."""
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def resolve_root() -> str:
    """Directory that holds ``data/`` and the WebUI static files.

    In a Nuitka standalone build that is the directory containing the
    executable; when running from source it is the repository root (the parent
    of the ``app`` package).
    """
    if is_compiled():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_APPSETTINGS: dict[str, Any] = {
    "ConnectionStrings": {
        "Production": "Host=localhost;Uid=root;Password=;Database=classisland_management;Port=3306",
    },
    "Kestrel": {
        "Endpoints": {
            "api": {"Url": DEFAULT_API_URL, "Protocols": "Http1"},
            "grpc": {"Url": DEFAULT_GRPC_URL, "Protocols": "Http2"},
        }
    },
    "DatabaseType": "sqlite",
    "CacheCapacity": 1024,
}


def parse_command_line(argv: list[str]) -> dict[str, str]:
    """Parse ``--key=value`` style arguments the way .NET's command line
    configuration provider does (case-insensitive keys)."""
    result: dict[str, str] = {}
    for arg in argv:
        if not arg.startswith("--"):
            continue
        body = arg[2:]
        if "=" in body:
            key, value = body.split("=", 1)
        else:
            key, value = body, "true"
        result[key.strip().lower()] = value
    return result


def parse_url(value: str) -> tuple[str, int]:
    """Split ``http://host:port`` into ``(host, port)``."""
    value = (value or "").strip()
    if not value:
        return "0.0.0.0", 7878
    schemes = ("http://", "https://")
    for scheme in schemes:
        if value.lower().startswith(scheme):
            value = value[len(scheme):]
            break
    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" in value:
        host, port = value.rsplit(":", 1)
        try:
            return (host or "0.0.0.0"), int(port)
        except ValueError:
            return (host or "0.0.0.0"), 7878
    return value or "0.0.0.0", 7878


@dataclass
class AppConfig:
    """Runtime configuration."""

    root: str = ""
    command_line: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ setup
    @property
    def setup_mode(self) -> bool:
        return self.command_line.get("setup", "").lower() == "true"

    @property
    def migrate_mode(self) -> bool:
        return self.command_line.get("migrate", "").lower() == "true"

    @property
    def development(self) -> bool:
        return os.environ.get("ASPNETCORE_ENVIRONMENT", "").lower() == "development"

    # ------------------------------------------------------------------ paths
    @property
    def config_path(self) -> str:
        return os.path.join(self.root, APP_CONFIG_RELATIVE_PATH)

    @property
    def data_directory(self) -> str:
        return os.path.join(self.root, "data")

    # ------------------------------------------------------------- appsettings
    def section(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for key in keys:
            if not isinstance(node, dict):
                return default
            # .NET configuration keys are case-insensitive.
            found = None
            for k, v in node.items():
                if k.lower() == key.lower():
                    found = v
                    break
            if found is None:
                return default
            node = found
        return node

    def get(self, key: str, default: str | None = None) -> str | None:
        """Configuration indexer equivalent: ``Configuration["CacheCapacity"]``."""
        value = self.section(*key.split(":"), default=None)
        if value is None:
            return default
        return str(value)

    # ---------------------------------------------------------------- endpoints
    @property
    def api_url(self) -> str:
        return str(self.section("Kestrel", "Endpoints", "api", "Url", default=DEFAULT_API_URL))

    @property
    def grpc_url(self) -> str:
        return str(self.section("Kestrel", "Endpoints", "grpc", "Url", default=DEFAULT_GRPC_URL))

    @property
    def api_host_port(self) -> tuple[str, int]:
        return parse_url(self.api_url)

    @property
    def grpc_host_port(self) -> tuple[str, int]:
        return parse_url(self.grpc_url)

    # ---------------------------------------------------------------- database
    @property
    def database_type(self) -> str:
        value = self.section("DatabaseType", default="sqlite")
        return str(value or "sqlite").lower()

    @property
    def connection_string(self) -> str:
        key = "Development" if self.development else "Production"
        value = self.section("ConnectionStrings", key)
        if value is None:
            value = self.section("ConnectionStrings", "Production", default="")
        return str(value or "")

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the configured database."""
        if self.database_type == "mysql":
            return _mysql_url_from_connection_string(self.connection_string)
        if self.database_type == "sqlite":
            return "sqlite:///" + os.path.join(self.data_directory, "management.db").replace("\\", "/")
        raise ValueError(f"Unsupported database type: {self.database_type}")

    @property
    def cache_capacity(self) -> int:
        value = self.get("CacheCapacity")
        try:
            return int(value) if value is not None else 1024
        except ValueError:
            return 1024

    @property
    def static_directory(self) -> str:
        if is_compiled():
            # Bundled by ``--include-data-dir=app/static=static``.
            return os.path.join(self.root, "static")
        return os.path.join(self.root, "app", "static")

    # ------------------------------------------------------------------- load
    @classmethod
    def load(cls, root: str, argv: list[str] | None = None) -> "AppConfig":
        argv = list(sys.argv[1:] if argv is None else argv)
        config = cls(root=root, command_line=parse_command_line(argv))
        path = config.config_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as fp:
                    config.raw = json.load(fp)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"读取配置文件失败：{exc}")
                config.raw = {}
        else:
            config.raw = json.loads(json.dumps(DEFAULT_APPSETTINGS))
            if config.database_type == "mysql" and not config.connection_string:
                config.raw["DatabaseType"] = "sqlite"
        if config.database_type not in ("mysql", "sqlite"):
            raise ValueError(f"Unsupported database type: {config.database_type}")
        return config

    def save(self) -> None:
        os.makedirs(self.data_directory, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as fp:
            json.dump(self.raw, fp, ensure_ascii=False, indent=2)


def _mysql_url_from_connection_string(connection_string: str) -> str:
    """Convert an ADO.NET MySQL connection string into a SQLAlchemy URL."""
    parts: dict[str, str] = {}
    for chunk in (connection_string or "").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip().lower()] = value.strip()

    host = parts.get("host") or parts.get("server") or "localhost"
    port = parts.get("port") or "3306"
    database = parts.get("database") or parts.get("initial catalog") or ""
    user = parts.get("uid") or parts.get("user id") or parts.get("user") or "root"
    password = parts.get("password") or parts.get("pwd") or ""

    from urllib.parse import quote_plus

    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )
