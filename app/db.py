"""Database engine, session factory, identity tables and seeding."""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .models import (
    DEFAULT_GROUP_ID,
    DEFAULT_PROFILE_GROUP_ID,
    GLOBAL_GROUP_ID,
    Base,
    ClientGroup,
    OrganizationSettings,
    ProfileGroup,
    new_guid,
    now,
)

# ---------------------------------------------------------------------------
# roles: identical set and ordering to the original Roles.AllRoles
# ---------------------------------------------------------------------------

ROLE_ADMIN = "Admin"
ROLE_OBJECTS_WRITE = "ObjectsWrite"
ROLE_OBJECTS_DELETE = "ObjectsDelete"
ROLE_CLIENTS_WRITE = "ClientsWrite"
ROLE_CLIENTS_DELETE = "ClientsDelete"
ROLE_COMMANDS_USER = "CommandsUser"
ROLE_USERS_MANAGER = "UsersManager"

ALL_ROLES = [
    ROLE_ADMIN,
    ROLE_OBJECTS_WRITE,
    ROLE_OBJECTS_DELETE,
    ROLE_CLIENTS_WRITE,
    ROLE_CLIENTS_DELETE,
    ROLE_COMMANDS_USER,
    ROLE_USERS_MANAGER,
]


class Role(Base):
    __tablename__ = "roles"

    Id: Mapped[str] = mapped_column(String(64), primary_key=True)
    Name: Mapped[str] = mapped_column(String(64), default="")

    def to_json(self) -> dict[str, Any]:
        return {"id": self.Id, "name": self.Name}


class User(Base):
    __tablename__ = "users"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    Name: Mapped[str] = mapped_column(String(255), default="")
    UserName: Mapped[str] = mapped_column(String(256), unique=True, default="")
    NormalizedUserName: Mapped[str] = mapped_column(String(256), default="")
    PasswordHash: Mapped[str | None] = mapped_column(Text, nullable=True)
    SecurityStamp: Mapped[str] = mapped_column(String(64), default=new_guid)
    Email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    PhoneNumber: Mapped[str | None] = mapped_column(String(64), nullable=True)
    AllowChangePassword: Mapped[bool] = mapped_column(Integer, default=1)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Roles: Mapped[list["UserRole"]] = relationship(back_populates="User", cascade="all, delete-orphan")

    @property
    def role_names(self) -> list[str]:
        return [item.RoleId for item in self.Roles]


class UserRole(Base):
    __tablename__ = "user_roles"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserId: Mapped[str] = mapped_column(String(36), ForeignKey("users.Id"))
    RoleId: Mapped[str] = mapped_column(String(64), ForeignKey("roles.Id"))

    User: Mapped["User"] = relationship(back_populates="Roles")


class Database:
    """Owns the SQLAlchemy engine and a scoped session factory."""

    def __init__(self, url: str) -> None:
        self.url = url
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            path = url.split("sqlite:///", 1)[-1]
            if path and path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
            json_serializer=lambda obj: __import__("json").dumps(obj, ensure_ascii=False),
        )
        if url.startswith("sqlite"):
            self._enable_sqlite_foreign_keys()
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def _enable_sqlite_foreign_keys(self) -> None:
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    # ------------------------------------------------------------------ schema
    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    def session(self) -> Session:
        return self.SessionLocal()

    @contextmanager
    def open(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------ seeding
    def setup_database(self) -> None:
        """Equivalent of ``ManagementServerContext.SetupDatabase()``.

        The original only inserts the two client groups and the default profile
        group when they are missing; the name/colour of an existing row is
        refreshed here so an old local database converges on the same values.
        """
        with self.open() as db:
            default_group = db.get(ClientGroup, DEFAULT_GROUP_ID)
            if default_group is None:
                db.add(ClientGroup(Id=DEFAULT_GROUP_ID, Name="默认", ColorHex="#00f1f1"))
            else:
                default_group.Name = "默认"
                default_group.ColorHex = "#00f1f1"

            global_group = db.get(ClientGroup, GLOBAL_GROUP_ID)
            if global_group is None:
                db.add(ClientGroup(Id=GLOBAL_GROUP_ID, Name="全局", ColorHex="#ff8500"))
            else:
                global_group.Name = "全局"
                global_group.ColorHex = "#ff8500"

            profile_group = db.get(ProfileGroup, DEFAULT_PROFILE_GROUP_ID)
            if profile_group is None:
                db.add(
                    ProfileGroup(
                        Id=DEFAULT_PROFILE_GROUP_ID,
                        Name="默认",
                        Description="",
                        ColorHex="#00f1f1",
                    )
                )
            else:
                profile_group.Name = "默认"
                profile_group.Description = ""
                profile_group.ColorHex = "#00f1f1"

            for name in ALL_ROLES:
                if db.get(Role, name) is None:
                    db.add(Role(Id=name, Name=name))
            db.commit()

    # ---------------------------------------------------------- settings helper
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self.open() as db:
            item = db.get(OrganizationSettings, key)
            return item.Value if item is not None else default

    def set_setting(self, key: str, category: str, value: str | None) -> None:
        with self.open() as db:
            item = db.get(OrganizationSettings, key)
            if item is None:
                db.add(OrganizationSettings(Key=key, Value=value, Category=category))
            else:
                item.Value = value
                item.Category = category
            db.commit()

    def get_settings_by_category(self, category: str) -> dict[str, str | None]:
        with self.open() as db:
            rows = db.scalars(
                select(OrganizationSettings).where(OrganizationSettings.Category == category)
            ).all()
            return {row.Key: row.Value for row in rows}


def get_database(config) -> Database:  # noqa: ANN001 - config is app.config.AppConfig
    return Database(config.database_url)
