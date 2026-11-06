"""SQLAlchemy models mirroring the Entity Framework Core entities of the
original ClassIsland.ManagementServer.

Serialization uses camelCase names identical to the JSON produced by
``System.Text.Json`` in the original ASP.NET Core implementation.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, foreign, mapped_column, relationship

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

DEFAULT_GROUP_ID = 1
GLOBAL_GROUP_ID = -1
DEFAULT_PROFILE_GROUP_ID = "00000000-0000-0000-0000-000000000001"
EMPTY_GUID = "00000000-0000-0000-0000-000000000000"
# ``ClassPlanGroup.DefaultGroupGuid`` on the client side.
CLASS_PLAN_DEFAULT_GROUP_ID = "acaf4ef0-e261-4262-b941-34ea93cb4369"
# ``ClassPlanGroup.GlobalGroupGuid`` on the client side.
CLASS_PLAN_GLOBAL_GROUP_ID = EMPTY_GUID


class ObjectTypes:
    Default = 0
    ProfileClassPlan = 1
    ProfileTimeLayout = 2
    ProfileSubject = 3
    AppSettings = 4
    Policy = 5
    Group = 6


class AssigneeTypes:
    Default = 0
    ClientUid = 1
    Id = 2
    Group = 3


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def now() -> dt.datetime:
    """``DateTime.Now`` of the original server (local time)."""
    return dt.datetime.now()


def new_guid() -> str:
    return str(uuid.uuid4())


def empty_guid() -> str:
    return EMPTY_GUID


def default_profile_group_id() -> str:
    return DEFAULT_PROFILE_GROUP_ID


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------------------
# clients
# ---------------------------------------------------------------------------


class ClientGroup(Base):
    __tablename__ = "client_groups"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Name: Mapped[str] = mapped_column(String(255), default="")
    ColorHex: Mapped[str] = mapped_column(String(7), default="#66CCFF")
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    AbstractClients: Mapped[list["AbstractClient"]] = relationship(back_populates="Group")
    ObjectsAssignees: Mapped[list["ObjectsAssignee"]] = relationship(back_populates="Group")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "colorHex": self.ColorHex,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class AbstractClient(Base):
    __tablename__ = "abstract_clients"

    InternalId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Id: Mapped[str] = mapped_column(String(255), default="", index=True)
    GroupId: Mapped[int] = mapped_column(Integer, ForeignKey("client_groups.Id"), default=DEFAULT_GROUP_ID)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ClientGroup | None"] = relationship(back_populates="AbstractClients", lazy="joined")
    Clients: Mapped[list["Client"]] = relationship(
        primaryjoin="foreign(Client.Id) == AbstractClient.Id",
        viewonly=True,
        lazy="select",
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "internalId": self.InternalId,
            "id": self.Id,
            "groupId": self.GroupId,
            "group": self.Group.to_json() if self.Group is not None else None,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class Client(Base):
    __tablename__ = "clients"

    Cuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=empty_guid)
    Id: Mapped[str] = mapped_column(String(255), default="")
    RegisterTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    PolicyVersion: Mapped[int] = mapped_column(Integer, default=0)
    TimeLayoutVersion: Mapped[int] = mapped_column(Integer, default=0)
    SubjectsVersion: Mapped[int] = mapped_column(Integer, default=0)
    DefaultSettingsVersion: Mapped[int] = mapped_column(Integer, default=0)
    ClassPlanVersion: Mapped[int] = mapped_column(Integer, default=0)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)
    Mac: Mapped[str] = mapped_column(String(16), default="")

    AbstractClient: Mapped["AbstractClient | None"] = relationship(
        primaryjoin="foreign(Client.Id) == AbstractClient.Id",
        uselist=False,
        lazy="joined",
    )

    @property
    def GroupId(self) -> int:
        if self.AbstractClient is not None:
            return self.AbstractClient.GroupId
        return DEFAULT_GROUP_ID

    def to_json(self) -> dict[str, Any]:
        return {
            "cuid": self.Cuid,
            "id": self.Id,
            "registerTime": fmt_datetime(self.RegisterTime),
            "policyVersion": self.PolicyVersion,
            "timeLayoutVersion": self.TimeLayoutVersion,
            "subjectsVersion": self.SubjectsVersion,
            "defaultSettingsVersion": self.DefaultSettingsVersion,
            "classPlanVersion": self.ClassPlanVersion,
            "mac": self.Mac,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
            "abstractClient": self.AbstractClient.to_json() if self.AbstractClient is not None else None,
        }


class ObjectsAssignee(Base):
    __tablename__ = "objects_assignees"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ObjectId: Mapped[str] = mapped_column(String(36), default=empty_guid)
    ObjectType: Mapped[int] = mapped_column(Integer, default=0)
    TargetClientId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    TargetClientCuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    TargetGroupId: Mapped[int | None] = mapped_column(Integer, ForeignKey("client_groups.Id"), nullable=True)
    AssigneeType: Mapped[int] = mapped_column(Integer, default=0)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ClientGroup | None"] = relationship(back_populates="ObjectsAssignees")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "objectId": self.ObjectId,
            "objectType": self.ObjectType,
            "targetClientId": self.TargetClientId,
            "targetClientCuid": self.TargetClientCuid,
            "targetGroupId": self.TargetGroupId,
            "assigneeType": self.AssigneeType,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ObjectUpdate(Base):
    __tablename__ = "object_updates"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ObjectId: Mapped[str] = mapped_column(String(36), default=empty_guid)
    ObjectType: Mapped[int] = mapped_column(Integer, default=0)
    TargetCuid: Mapped[str] = mapped_column(String(36), default=empty_guid)
    UpdateTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)


class OrganizationSettings(Base):
    __tablename__ = "organization_settings"

    Key: Mapped[str] = mapped_column(String(32), primary_key=True)
    Value: Mapped[str | None] = mapped_column(Text, nullable=True)
    Category: Mapped[str] = mapped_column(String(32), default="")


# ---------------------------------------------------------------------------
# content
# ---------------------------------------------------------------------------


class Setting(Base):
    __tablename__ = "settings"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    Name: Mapped[str] = mapped_column(String(255), default="")
    Description: Mapped[str] = mapped_column(Text, default="")
    Settings: Mapped[str] = mapped_column(Text, default="{}")
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "description": self.Description,
            "settings": self.Settings,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class Policy(Base):
    __tablename__ = "policies"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    Name: Mapped[str] = mapped_column(String(255), default="")
    IsEnabled: Mapped[bool] = mapped_column(Boolean, default=True)
    Content: Mapped[dict] = mapped_column(JSON, default=dict)
    GroupId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_groups.Id"), default=default_profile_group_id)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ProfileGroup | None"] = relationship(lazy="joined")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "isEnabled": self.IsEnabled,
            "content": self.Content if self.Content is not None else {},
            "groupId": self.GroupId,
            "group": self.Group.to_json() if self.Group is not None else None,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileGroup(Base):
    __tablename__ = "profile_groups"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=default_profile_group_id)
    Name: Mapped[str] = mapped_column(String(255), default="")
    Description: Mapped[str] = mapped_column(Text, default="")
    ColorHex: Mapped[str] = mapped_column(String(7), default="#66CCFF")
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "description": self.Description,
            "colorHex": self.ColorHex,
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileSubject(Base):
    __tablename__ = "profile_subjects"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    GroupId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_groups.Id"), default=default_profile_group_id)
    Name: Mapped[str] = mapped_column(String(255), default="")
    Initials: Mapped[str] = mapped_column(String(255), default="")
    IsOutDoor: Mapped[bool] = mapped_column(Boolean, default=False)
    AttachedObjects: Mapped[dict] = mapped_column(JSON, default=dict)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ProfileGroup | None"] = relationship(lazy="joined")

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "groupId": self.GroupId,
            "group": self.Group.to_json() if self.Group is not None else None,
            "name": self.Name,
            "initials": self.Initials,
            "isOutDoor": self.IsOutDoor,
            "attachedObjects": self.AttachedObjects if self.AttachedObjects is not None else {},
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileTimeLayout(Base):
    __tablename__ = "profile_timelayouts"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    Name: Mapped[str] = mapped_column(String(255), default="")
    GroupId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_groups.Id"), default=default_profile_group_id)
    AttachedObjects: Mapped[dict] = mapped_column(JSON, default=dict)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ProfileGroup | None"] = relationship(lazy="joined")
    TimePoints: Mapped[list["ProfileTimeLayoutTimePoint"]] = relationship(
        back_populates="Parent",
        cascade="all, delete-orphan",
        order_by="ProfileTimeLayoutTimePoint.Index",
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "groupId": self.GroupId,
            "group": self.Group.to_json() if self.Group is not None else None,
            "profileTimelayoutTimepoints": [
                point.to_json() for point in sorted(self.TimePoints, key=lambda p: p.Index)
            ],
            "attachedObjects": self.AttachedObjects if self.AttachedObjects is not None else {},
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileTimeLayoutTimePoint(Base):
    __tablename__ = "profile_timelayout_timepoint"

    InternalId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ParentId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_timelayouts.Id"))
    Index: Mapped[int] = mapped_column(Integer, default=0)
    Start: Mapped[dt.time] = mapped_column(Time)
    End: Mapped[dt.time] = mapped_column(Time)
    TimeType: Mapped[int] = mapped_column(Integer, default=0)
    DefaultSubjectId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    IsHideDefault: Mapped[bool] = mapped_column(Boolean, default=False)
    AttachedObjects: Mapped[dict] = mapped_column(JSON, default=dict)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Parent: Mapped["ProfileTimeLayout"] = relationship(back_populates="TimePoints")

    def to_json(self) -> dict[str, Any]:
        return {
            "internalId": self.InternalId,
            "parentId": self.ParentId,
            "index": self.Index,
            "start": fmt_time(self.Start),
            "end": fmt_time(self.End),
            "timeType": self.TimeType,
            "defaultSubjectId": self.DefaultSubjectId,
            "isHideDefault": self.IsHideDefault,
            "attachedObjects": self.AttachedObjects if self.AttachedObjects is not None else {},
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileClassplan(Base):
    __tablename__ = "profile_classplans"

    Id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_guid)
    Name: Mapped[str] = mapped_column(String(255), default="")
    GroupId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_groups.Id"), default=default_profile_group_id)
    WeekDay: Mapped[int] = mapped_column(Integer, default=0)
    WeekDiv: Mapped[int] = mapped_column(Integer, default=0)
    WeekCountDivTotal: Mapped[int] = mapped_column(Integer, default=2)
    TimeLayoutId: Mapped[str] = mapped_column(String(36), default=empty_guid)
    IsEnabled: Mapped[bool] = mapped_column(Boolean, default=True)
    AttachedObjects: Mapped[dict] = mapped_column(JSON, default=dict)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Group: Mapped["ProfileGroup | None"] = relationship(lazy="joined")
    Classes: Mapped[list["ProfileClassPlanClass"]] = relationship(
        back_populates="Parent",
        cascade="all, delete-orphan",
        order_by="ProfileClassPlanClass.Index",
    )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.Id,
            "name": self.Name,
            "groupId": self.GroupId,
            "group": self.Group.to_json() if self.Group is not None else None,
            "weekDay": self.WeekDay,
            "weekDiv": self.WeekDiv,
            "weekCountDivTotal": self.WeekCountDivTotal,
            "timeLayoutId": self.TimeLayoutId,
            "isEnabled": self.IsEnabled,
            "profileClassPlanClasses": [
                item.to_json() for item in sorted(self.Classes, key=lambda c: c.Index)
            ],
            "attachedObjects": self.AttachedObjects if self.AttachedObjects is not None else {},
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


class ProfileClassPlanClass(Base):
    __tablename__ = "profile_classplan_classes"

    InternalId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Index: Mapped[int] = mapped_column(Integer, default=0)
    ParentId: Mapped[str] = mapped_column(String(36), ForeignKey("profile_classplans.Id"))
    SubjectId: Mapped[str] = mapped_column(String(36), default=empty_guid)
    AttachedObjects: Mapped[dict] = mapped_column(JSON, default=dict)
    CreatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now)
    UpdatedTime: Mapped[dt.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    Parent: Mapped["ProfileClassplan"] = relationship(back_populates="Classes")

    def to_json(self) -> dict[str, Any]:
        return {
            "internalId": self.InternalId,
            "index": self.Index,
            "parentId": self.ParentId,
            "subjectId": self.SubjectId,
            "attachedObjects": self.AttachedObjects if self.AttachedObjects is not None else {},
            "createdTime": fmt_datetime(self.CreatedTime),
            "updatedTime": fmt_datetime(self.UpdatedTime),
        }


# ---------------------------------------------------------------------------
# serialization helpers
# ---------------------------------------------------------------------------


def fmt_datetime(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.microsecond:
        return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def fmt_time(value: dt.time | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.microsecond:
        return value.strftime("%H:%M:%S.%f")[:-3]
    return value.strftime("%H:%M:%S")


def fmt_date_time_only(value: dt.time | None) -> str | None:
    """``ConvertTimeOnly``: today's date plus the time component."""
    if value is None:
        return None
    today = dt.date.today()
    combined = dt.datetime.combine(today, value)
    return combined.strftime("%Y-%m-%dT%H:%M:%S")


def fmt_time_span(value: dt.time | None) -> str:
    """Format a time as a ``System.TimeSpan`` JSON literal (``"HH:mm:ss"``).

    ``System.Text.Json`` writes ``TimeSpan`` in the constant ("c") format, which
    for a value below one day is ``hh\\:mm\\:ss``.
    """
    if value is None:
        return "00:00:00"
    return f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"


def parse_datetime(value: Any) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1]
    if "+" in text:
        text = text.split("+", 1)[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_time(value: Any) -> dt.time | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.time):
        return value
    if isinstance(value, dt.datetime):
        return value.time()
    text = str(value).strip()
    if "T" in text:
        parsed = parse_datetime(text)
        return parsed.time() if parsed else None
    if " " in text:
        text = text.split(" ")[-1]
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def ci_get(mapping: Any, key: str, default: Any = None) -> Any:
    """Case insensitive ``dict.get``.

    The original ASP.NET Core controllers bind request bodies with
    ``JsonSerializerDefaults.Web``, which sets
    ``PropertyNameCaseInsensitive = true``.  A profile file exported by
    ClassIsland is written in **PascalCase** (``Subjects``/``Layouts``/``Name``)
    while the Web UI emits camelCase, so every payload read has to accept both
    spellings exactly like the original server did.
    """
    if not isinstance(mapping, dict):
        return default
    if key in mapping:
        return mapping[key]
    lowered = key.lower()
    for candidate, value in mapping.items():
        if isinstance(candidate, str) and candidate.lower() == lowered:
            return value
    return default


def parse_guid(value: Any, default: str | None = None) -> str | None:
    """``GuidHelpers.TryParseGuidOrEmpty`` equivalent."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError):
        return default


def parse_guid_or_empty(value: Any) -> str:
    return parse_guid(value, EMPTY_GUID) or EMPTY_GUID


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    return default


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
