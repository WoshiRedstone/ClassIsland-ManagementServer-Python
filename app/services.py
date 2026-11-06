"""Service layer.

Direct ports of the original C# services.  All of them operate on an open
SQLAlchemy session; notifications are queued (not committed) exactly like the
original implementation, so callers control the transaction boundaries.
"""

from __future__ import annotations

import base64
import datetime as dt
import secrets
import threading
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    CLASS_PLAN_DEFAULT_GROUP_ID,
    DEFAULT_GROUP_ID,
    DEFAULT_PROFILE_GROUP_ID,
    EMPTY_GUID,
    GLOBAL_GROUP_ID,
    AssigneeTypes,
    AbstractClient,
    Client,
    ClientGroup,
    ObjectsAssignee,
    ObjectTypes,
    ObjectUpdate,
    OrganizationSettings,
    Policy,
    ProfileClassPlanClass,
    ProfileClassplan,
    ProfileGroup,
    ProfileSubject,
    ProfileTimeLayout,
    ProfileTimeLayoutTimePoint,
    Setting,
    fmt_date_time_only,
    fmt_time_span,
    ci_get,
    new_guid,
    now,
    parse_guid,
    parse_guid_or_empty,
    parse_time,
    json_dumps,
)

# ---------------------------------------------------------------------------
# ThreadSafeLruCache
# ---------------------------------------------------------------------------


class LruCache:
    """Port of ``ComponentModels.ThreadSafeLruCache``."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("容量必须大于 0")
        self._capacity = capacity
        self._lock = threading.Lock()
        self._items: dict[Any, Any] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def count(self) -> int:
        return len(self)

    def contains_key(self, key: Any) -> bool:
        with self._lock:
            return key in self._items

    def add(self, key: Any, value: Any) -> None:
        with self._lock:
            if key in self._items:
                self._items.pop(key)
            self._items[key] = value
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))

    def try_get(self, key: Any) -> Any:
        with self._lock:
            if key not in self._items:
                return None
            value = self._items.pop(key)
            self._items[key] = value
            return value

    def remove(self, key: Any) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


# ---------------------------------------------------------------------------
# ObjectsAssigneeService
# ---------------------------------------------------------------------------


class ObjectsAssigneeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_assigned_clients(self, assignee: ObjectsAssignee) -> list[Client]:
        if assignee.TargetGroupId == GLOBAL_GROUP_ID:
            return list(self.session.scalars(select(Client)).all())
        assignee_type = assignee.AssigneeType
        result: list[Client] = []
        for client in self.session.scalars(select(Client)).all():
            group_id = client.AbstractClient.GroupId if client.AbstractClient is not None else DEFAULT_GROUP_ID
            if assignee_type == AssigneeTypes.Group and assignee.TargetGroupId == group_id:
                result.append(client)
            elif assignee_type == AssigneeTypes.Id and assignee.TargetClientId == client.Id:
                result.append(client)
            elif assignee_type == AssigneeTypes.ClientUid and assignee.TargetClientCuid == client.Cuid:
                result.append(client)
        return result

    def get_object_assigned_clients(self, object_id: str) -> list[Client]:
        assignees = self.session.scalars(
            select(ObjectsAssignee).where(ObjectsAssignee.ObjectId == object_id)
        ).all()
        result: list[Client] = []
        seen: set[str] = set()
        for assignee in assignees:
            for client in self.get_assigned_clients(assignee):
                if client.Cuid not in seen:
                    seen.add(client.Cuid)
                    result.append(client)
        return result

    def _build_client_assignee_query(self, client: Client, object_type: int) -> list[ObjectsAssignee]:
        group_id = client.AbstractClient.GroupId if client.AbstractClient is not None else DEFAULT_GROUP_ID
        assignees = self.session.scalars(
            select(ObjectsAssignee).where(ObjectsAssignee.ObjectType == object_type)
        ).all()
        result: list[ObjectsAssignee] = []
        for item in assignees:
            if item.AssigneeType == AssigneeTypes.Group and item.TargetGroupId == GLOBAL_GROUP_ID:
                result.append(item)
            elif item.AssigneeType == AssigneeTypes.ClientUid and item.TargetClientCuid == client.Cuid:
                result.append(item)
            elif item.AssigneeType == AssigneeTypes.Id and item.TargetClientId == client.Id:
                result.append(item)
            elif item.AssigneeType == AssigneeTypes.Group and item.TargetGroupId == group_id:
                result.append(item)
        return result

    def get_client_assigning_objects(self, client: Client, object_type: int) -> list[ObjectsAssignee]:
        return self._build_client_assignee_query(client, object_type)

    def get_client_assigning_objects_leveled(self, client: Client, object_type: int) -> list[ObjectsAssignee]:
        items = self._build_client_assignee_query(client, object_type)
        items.sort(key=lambda x: x.AssigneeType)
        return items


# ---------------------------------------------------------------------------
# ObjectsUpdateNotifyService
# ---------------------------------------------------------------------------


class ObjectsUpdateNotifyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assignee_service = ObjectsAssigneeService(session)

    def notify_object_updating(self, object_id: str, object_type: int) -> None:
        for client in self.assignee_service.get_object_assigned_clients(object_id):
            self.session.add(
                ObjectUpdate(
                    ObjectId=object_id,
                    ObjectType=object_type,
                    TargetCuid=client.Cuid,
                    UpdateTime=now(),
                )
            )

    def notify_client_updating(
        self,
        cuid: str | None = None,
        client_id: str | None = None,
        group_id: int | None = None,
    ) -> None:
        for client in self.session.scalars(select(Client)).all():
            client_group = client.AbstractClient.GroupId if client.AbstractClient is not None else DEFAULT_GROUP_ID
            if cuid is not None and client.Cuid == cuid:
                matched = True
            elif client_id is not None and client.Id == client_id:
                matched = True
            elif group_id is not None and client_group == group_id:
                matched = True
            else:
                matched = False
            if matched:
                self.session.add(
                    ObjectUpdate(
                        ObjectId=EMPTY_GUID,
                        ObjectType=0,
                        TargetCuid=client.Cuid,
                        UpdateTime=now(),
                    )
                )

    def notify_client_updated(self) -> None:  # pragma: no cover - no-op in original
        return

    def is_object_updated(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def is_client_updated(self, *_args: Any, **_kwargs: Any) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ObjectsCacheService
# ---------------------------------------------------------------------------


class ObjectsCacheService:
    def __init__(self, capacity: int = 1024) -> None:
        self.class_plan_cache = LruCache(capacity)
        self.time_layout_cache = LruCache(capacity)
        self.subject_cache = LruCache(capacity)

    def invalidate_cache(self, object_type: int, object_id: str) -> None:
        if object_type == ObjectTypes.ProfileClassPlan:
            self.class_plan_cache.remove(object_id)
        elif object_type == ObjectTypes.ProfileTimeLayout:
            self.time_layout_cache.remove(object_id)
        elif object_type == ObjectTypes.ProfileSubject:
            self.subject_cache.remove(object_id)
        else:
            raise ValueError(f"不支持的对象类型：{object_type}")


# ---------------------------------------------------------------------------
# OrganizationSettingsService
# ---------------------------------------------------------------------------


class OrganizationSettingsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_settings(self, key: str) -> str | None:
        item = self.session.get(OrganizationSettings, key)
        return item.Value if item is not None else None

    def get_settings_by_category(self, category: str) -> dict[str, str | None]:
        rows = self.session.scalars(
            select(OrganizationSettings).where(OrganizationSettings.Category == category)
        ).all()
        return {row.Key: row.Value for row in rows}

    def set_organization_settings(self, key: str, category: str, value: str | None) -> None:
        item = self.session.get(OrganizationSettings, key)
        if item is None:
            self.session.add(OrganizationSettings(Key=key, Value=value, Category=category))
        else:
            item.Value = value
            item.Category = category


# ---------------------------------------------------------------------------
# ProfileEntitiesService
# ---------------------------------------------------------------------------


class ProfileEntitiesService:
    def __init__(
        self,
        session: Session,
        cache: ObjectsCacheService,
        notify: ObjectsUpdateNotifyService,
    ) -> None:
        self.session = session
        self.cache = cache
        self.notify = notify

    # ------------------------------------------------------------------ subjects
    def set_subject_entity(
        self,
        subject_id: str,
        subject: dict[str, Any],
        replace: bool,
        group_id: str | None = None,
    ) -> None:
        payload = ProfileSubject(
            Id=subject_id,
            Name=str(ci_get(subject, "name") or ""),
            Initials=str(ci_get(subject, "initial") or ci_get(subject, "initials") or ""),
            AttachedObjects=ci_get(subject, "attachedObjects") or {},
            IsOutDoor=bool(ci_get(subject, "isOutDoor") or False),
            GroupId=group_id or DEFAULT_PROFILE_GROUP_ID,
        )
        raw = self.session.get(ProfileSubject, subject_id)
        if raw is not None and not replace:
            return
        if raw is not None and group_id is None:
            payload.GroupId = raw.GroupId
        if raw is not None:
            self.session.expunge(raw)
            payload.CreatedTime = raw.CreatedTime
            self.session.merge(payload)
        else:
            self.session.add(payload)
        self.cache.invalidate_cache(ObjectTypes.ProfileSubject, subject_id)
        self.notify.notify_object_updating(subject_id, ObjectTypes.ProfileSubject)

    # -------------------------------------------------------------- timelayouts
    def set_time_layout_entity(
        self,
        time_layout_id: str,
        time_layout: dict[str, Any],
        replace: bool,
        group_id: str | None = None,
    ) -> None:
        raw_group = ci_get(time_layout, "groupId")
        payload = ProfileTimeLayout(
            Id=time_layout_id,
            Name=str(ci_get(time_layout, "name") or ""),
            AttachedObjects=ci_get(time_layout, "attachedObjects") or {},
            GroupId=parse_guid(raw_group) or group_id or DEFAULT_PROFILE_GROUP_ID,
        )
        raw = self.session.get(ProfileTimeLayout, time_layout_id)
        if raw is not None and not replace:
            return
        if raw is not None and group_id is None and parse_guid(raw_group) is None:
            payload.GroupId = raw.GroupId

        self.session.execute(
            delete(ProfileTimeLayoutTimePoint).where(ProfileTimeLayoutTimePoint.ParentId == time_layout_id)
        )
        if raw is not None:
            self.session.expunge(raw)
            payload.CreatedTime = raw.CreatedTime
            self.session.merge(payload)
        else:
            self.session.add(payload)
        self.session.flush()

        index = 0
        for item in ci_get(time_layout, "layouts") or []:
            # ``startSecond``/``endSecond`` (legacy DateTime) are written by the
            # Web UI; ClassIsland 2.1 clients write ``startTime``/``endTime``
            # (TimeSpan, "HH:mm:ss").  Accept both.
            start = parse_time(ci_get(item, "startSecond")) or parse_time(ci_get(item, "startTime"))
            end = parse_time(ci_get(item, "endSecond")) or parse_time(ci_get(item, "endTime"))
            self.session.add(
                ProfileTimeLayoutTimePoint(
                    ParentId=time_layout_id,
                    Index=index,
                    Start=start or dt.time(0, 0, 0),
                    End=end or dt.time(0, 0, 0),
                    TimeType=int(ci_get(item, "timeType") or 0),
                    DefaultSubjectId=parse_guid_or_empty(ci_get(item, "defaultClassId")),
                    IsHideDefault=bool(ci_get(item, "isHideDefault") or False),
                    AttachedObjects=ci_get(item, "attachedObjects") or {},
                    CreatedTime=raw.CreatedTime if raw is not None else now(),
                )
            )
            index += 1

        self.cache.invalidate_cache(ObjectTypes.ProfileTimeLayout, time_layout_id)
        self.notify.notify_object_updating(time_layout_id, ObjectTypes.ProfileTimeLayout)

    # ---------------------------------------------------------------- classplans
    def set_class_plan_entity(
        self,
        class_plan_id: str,
        class_plan: dict[str, Any],
        replace: bool,
        group_id: str | None = None,
    ) -> None:
        time_layout_id = parse_guid_or_empty(ci_get(class_plan, "timeLayoutId"))
        time_layout = self.session.get(ProfileTimeLayout, time_layout_id)
        if time_layout is None:
            return

        time_rule = ci_get(class_plan, "timeRule") or {}
        raw_group = ci_get(class_plan, "groupId")
        payload = ProfileClassplan(
            Id=class_plan_id,
            Name=str(ci_get(class_plan, "name") or ""),
            AttachedObjects=ci_get(class_plan, "attachedObjects") or {},
            WeekDay=int(ci_get(time_rule, "weekDay") or 0),
            WeekDiv=int(ci_get(time_rule, "weekCountDiv") or 0),
            WeekCountDivTotal=int(ci_get(time_rule, "weekCountDivTotal") or 2),
            TimeLayoutId=time_layout_id,
            IsEnabled=bool(ci_get(class_plan, "isEnabled", True)),
            GroupId=parse_guid(raw_group) or group_id or DEFAULT_PROFILE_GROUP_ID,
        )
        raw = self.session.get(ProfileClassplan, class_plan_id)
        if raw is not None and not replace:
            return
        if raw is not None and group_id is None and parse_guid(raw_group) is None:
            payload.GroupId = raw.GroupId

        self.session.execute(
            delete(ProfileClassPlanClass).where(ProfileClassPlanClass.ParentId == class_plan_id)
        )
        if raw is not None:
            self.session.expunge(raw)
            payload.CreatedTime = raw.CreatedTime
            self.session.merge(payload)
        else:
            self.session.add(payload)
        self.session.flush()

        index = 0
        for item in ci_get(class_plan, "classes") or []:
            subject_id = parse_guid_or_empty(ci_get(item, "subjectId"))
            subject = self.session.get(ProfileSubject, subject_id)
            if subject is None:
                continue
            self.session.add(
                ProfileClassPlanClass(
                    ParentId=class_plan_id,
                    Index=index,
                    SubjectId=subject_id,
                    AttachedObjects=ci_get(item, "attachedObjects") or {},
                    CreatedTime=raw.CreatedTime if raw is not None else now(),
                )
            )
            index += 1

        self.cache.invalidate_cache(ObjectTypes.ProfileClassPlan, class_plan_id)
        self.notify.notify_object_updating(class_plan_id, ObjectTypes.ProfileClassPlan)

    def get_class_plan_entity(self, class_plan_id: str) -> dict[str, Any] | None:
        cached = self.cache.class_plan_cache.try_get(class_plan_id)
        if cached is not None:
            return cached
        item = self.session.get(ProfileClassplan, class_plan_id)
        if item is None:
            return None
        classes = sorted(item.Classes, key=lambda c: c.Index)
        result = {
            "name": item.Name,
            "timeRule": {
                "weekDay": item.WeekDay,
                "weekCountDiv": item.WeekDiv,
                "weekCountDivTotal": item.WeekCountDivTotal,
            },
            "timeLayoutId": item.TimeLayoutId,
            "classes": [
                {
                    "subjectId": c.SubjectId,
                    "isChangedClass": False,
                    "isEnabled": True,
                    "attachedObjects": {},
                }
                for c in classes
            ],
            "attachedObjects": item.AttachedObjects or {},
            "isEnabled": item.IsEnabled,
            # ClassIsland 2.x resolves the active class plan through
            # ``ClassPlan.AssociatedGroup`` against ``Profile.SelectedClassPlanGroupId``
            # / ``TempClassPlanGroupId`` / ``ClassPlanGroup.GlobalGroupGuid``
            # (LessonsService.cs:170-190, :592).  Emitting the *profile* group here
            # would make every delivered class plan invisible to the client, so the
            # default class plan group is used instead.
            "associatedGroup": CLASS_PLAN_DEFAULT_GROUP_ID,
            # The Web UI edits the profile group through ``groupId``.
            "groupId": item.GroupId,
        }
        self.cache.class_plan_cache.add(class_plan_id, result)
        return result

    def get_time_layout_entity(self, time_layout_id: str) -> dict[str, Any] | None:
        cached = self.cache.time_layout_cache.try_get(time_layout_id)
        if cached is not None:
            return cached
        item = self.session.get(ProfileTimeLayout, time_layout_id)
        if item is None:
            return None
        points = sorted(item.TimePoints, key=lambda p: p.Index)
        result = {
            "name": item.Name,
            "layouts": [
                {
                    # ``startSecond``/``endSecond`` are the legacy DateTime shaped
                    # fields the original server emits (``ConvertTimeOnly``); the
                    # Web UI still edits those.
                    "startSecond": fmt_date_time_only(p.Start),
                    "endSecond": fmt_date_time_only(p.End),
                    # ClassIsland 2.1 added ``startTime``/``endTime`` as TimeSpan
                    # values, serialized as "HH:mm:ss".  Both sets are emitted so
                    # old and new clients understand the payload.
                    "startTime": fmt_time_span(p.Start),
                    "endTime": fmt_time_span(p.End),
                    "timeType": p.TimeType,
                    "defaultClassId": p.DefaultSubjectId or "",
                    "isHideDefault": p.IsHideDefault,
                    "breakName": "",
                    "actionSet": None,
                    "attachedObjects": p.AttachedObjects or {},
                }
                for p in points
            ],
            "attachedObjects": item.AttachedObjects or {},
            "groupId": item.GroupId,
        }
        self.cache.time_layout_cache.add(time_layout_id, result)
        return result

    def get_subject_entity(self, subject_id: str) -> dict[str, Any] | None:
        cached = self.cache.subject_cache.try_get(subject_id)
        if cached is not None:
            return cached
        item = self.session.get(ProfileSubject, subject_id)
        if item is None:
            return None
        result = {
            "name": item.Name,
            "initial": item.Initials,
            "isOutDoor": item.IsOutDoor,
            "teacherName": "",
            "attachedObjects": item.AttachedObjects or {},
        }
        self.cache.subject_cache.add(subject_id, result)
        return result


# ---------------------------------------------------------------------------
# ClientCommandDeliverService / connection registry
# ---------------------------------------------------------------------------


class ClientSession:
    def __init__(self, client_uid: str, session_id: str) -> None:
        self.client_uid = client_uid
        self.session_id = session_id
        self.is_activated = False
        self.invalidate_time = now()
        self.writer: Any = None
        self.queue: list[Any] = []
        self._lock = threading.Lock()

    def enqueue(self, command_type: int, payload: bytes) -> None:
        with self._lock:
            self.queue.append((command_type, payload))

    def drain(self) -> list[Any]:
        """Return and clear every queued command."""
        with self._lock:
            items = list(self.queue)
            self.queue.clear()
        return items


class CyreneMspConnectionService:
    """Singleton holding live gRPC command channels and the PGP server key."""

    INACTIVATE_SESSION_EXPIRATION = dt.timedelta(seconds=30)

    def __init__(self) -> None:
        self.sessions: dict[str, ClientSession] = {}
        self.server_public_key_armored: str = ""
        self.server_key: Any = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------- keys
    def init_server_key(self, session: Session) -> None:
        import warnings

        warnings.filterwarnings("ignore")
        import pgpy
        from pgpy.constants import CompressionAlgorithm, HashAlgorithm, SymmetricKeyAlgorithm

        public = session.get(OrganizationSettings, "CyreneMspPublicKey")
        private = session.get(OrganizationSettings, "CyreneMspPrivateKey")
        if private is None or public is None:
            key = pgpy.PGPKey.new(pgpy.constants.PubKeyAlgorithm.RSAEncryptOrSign, 2048)
            uid = pgpy.PGPUID.new("ClassIsland.ManagementServer")
            key.add_uid(
                uid,
                usage={pgpy.constants.KeyFlags.EncryptCommunications, pgpy.constants.KeyFlags.EncryptStorage},
                hashes=[HashAlgorithm.SHA256],
                ciphers=[SymmetricKeyAlgorithm.AES256],
                compression=[CompressionAlgorithm.ZLIB],
            )
            public_armored = str(key.pubkey)
            private_armored = str(key)
            if public is None:
                session.add(
                    OrganizationSettings(Key="CyreneMspPublicKey", Value=public_armored, Category="CyreneMsp")
                )
            else:
                public.Value = public_armored
            if private is None:
                session.add(
                    OrganizationSettings(Key="CyreneMspPrivateKey", Value=private_armored, Category="CyreneMsp")
                )
            else:
                private.Value = private_armored
            session.commit()
        else:
            public_armored = public.Value or ""
            private_armored = private.Value or ""

        self.server_public_key_armored = public_armored
        key, _ = pgpy.PGPKey.from_blob(private_armored)
        self.server_key = key

    def decrypt_challenge(self, payload: str) -> str:
        import pgpy

        message = pgpy.PGPMessage.from_blob(payload)
        plain = self.server_key.decrypt(message).message
        # ``PgpCore`` (used by both the C# server and the ClassIsland client) writes
        # the plaintext into a literal data packet that carries a file name, so pgpy
        # surfaces ``bytearray`` instead of ``str``. Protobuf string fields reject
        # ``bytearray`` ("bad argument type for built-in operation"), and the client
        # compares the decrypted challenge with its own base64 string, so decode it.
        if isinstance(plain, (bytes, bytearray)):
            return bytes(plain).decode("utf-8", errors="replace")
        return plain

    # --------------------------------------------------------------- sessions
    def establish_client_connection(self, client_uid: str) -> str | None:
        with self._lock:
            existing = self.sessions.get(client_uid)
            if existing is not None and not existing.is_activated:
                if existing.invalidate_time + self.INACTIVATE_SESSION_EXPIRATION > now():
                    return None
            session_id = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
            self.sessions[client_uid] = ClientSession(client_uid, session_id)
            return session_id

    def destroy_connection(self, client_uid: str) -> None:
        with self._lock:
            session = self.sessions.get(client_uid)
            if session is None:
                return
            session.is_activated = False
            self.sessions.pop(client_uid, None)

    def get_session(self, client_uid: str) -> ClientSession | None:
        return self.sessions.get(client_uid)


class ClientCommandDeliverService:
    def __init__(self, session: Session, connections: CyreneMspConnectionService) -> None:
        self.session = session
        self.connections = connections
        self.assignee_service = ObjectsAssigneeService(session)

    def deliver_command(self, command_type: int, payload: bytes, target: ObjectsAssignee) -> None:
        for client in self.assignee_service.get_assigned_clients(target):
            session = self.connections.get_session(client.Cuid)
            if session is None:
                continue
            if not session.is_activated or session.writer is None:
                return
            session.enqueue(command_type, payload)
