"""Routers for the ClassIsland ManagementServer REST API.

Every route mirrors the ASP.NET Core controller of the same name; JSON payloads
use camelCase keys identical to ``System.Text.Json``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from ..db import ROLE_ADMIN, ROLE_OBJECTS_DELETE, ROLE_OBJECTS_WRITE, Role, User, UserRole
from ..deps import build_command_service, build_profile_service, error, paginate
from ..models import (
    DEFAULT_GROUP_ID,
    DEFAULT_PROFILE_GROUP_ID,
    EMPTY_GUID,
    GLOBAL_GROUP_ID,
    AbstractClient,
    AssigneeTypes,
    Client,
    ClientGroup,
    ObjectTypes,
    ObjectsAssignee,
    OrganizationSettings,
    Policy,
    ProfileClassplan,
    ProfileGroup,
    ProfileSubject,
    ProfileTimeLayout,
    Setting,
    fmt_datetime,
    new_guid,
    now,
    parse_bool,
    parse_guid,
    parse_guid_or_empty,
)
from ..security import current_user, hash_password, require_roles, token_response, verify_password
from ..services import (
    ClientCommandDeliverService,
    ObjectsAssigneeService,
    ObjectsUpdateNotifyService,
    OrganizationSettingsService,
    ProfileEntitiesService,
)

NOT_FOUND = "找不到请求的对象"


def sessions(request: Request):
    return request.state.session


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=error(NOT_FOUND))


def _guid(value: Any) -> str:
    parsed = parse_guid(value)
    if parsed is None:
        raise _not_found()
    return parsed


def _user_info(user: User, is_admin: bool, settings: OrganizationSettingsService) -> dict[str, Any]:
    oobe = settings.get_settings("IsOobeCompleted")
    return {
        "userName": user.UserName or "",
        "name": user.Name or "",
        "emailAddress": user.Email or "",
        "phoneNumber": user.PhoneNumber or "",
        "id": user.Id,
        "allowChangePassword": bool(user.AllowChangePassword),
        "roles": list(user.role_names),
        "redirectToOobe": (oobe != "true") and is_admin,
        "createdTime": fmt_datetime(user.CreatedTime),
        "updatedTime": fmt_datetime(user.UpdatedTime),
    }


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@auth_router.post("/login")
async def login(request: Request, body: dict[str, Any] = Body(default_factory=dict)):
    session = sessions(request)
    username = str(body.get("username") or "")
    password = str(body.get("password") or "")
    user = session.scalars(select(User).where(User.UserName == username)).first()
    if user is None:
        raise HTTPException(status_code=404, detail=error(f"找不到用户 {username}"))
    if not password:
        raise HTTPException(status_code=400, detail=error("密码不可为空"))
    if not verify_password(user.PasswordHash, password):
        raise HTTPException(status_code=401, detail=error("密码错误"))
    response = JSONResponse(content=token_response(request.app.state.database, user))
    response.delete_cookie(".AspNetCore.Identity.Application")
    return response


@auth_router.post("/refresh")
async def refresh(request: Request, body: dict[str, Any] = Body(default_factory=dict)):
    from ..security import create_access_token, create_refresh_token, decode_token

    session = sessions(request)
    token = str(body.get("refreshToken") or "")
    payload = decode_token(request.app.state.database, token, "refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail=error("刷新令牌无效或已过期"))
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail=error("刷新令牌无效或已过期"))
    return {
        "tokenType": "Bearer",
        "accessToken": create_access_token(request.app.state.database, user),
        "expiresIn": 3600,
        "refreshToken": create_refresh_token(request.app.state.database, user),
    }


@auth_router.post("/logout")
async def logout():
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# organization settings / brand / basic
# ---------------------------------------------------------------------------

settings_router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@settings_router.get("/brand")
async def get_brand(request: Request):
    service = OrganizationSettingsService(sessions(request))
    values = service.get_settings_by_category("Brand")
    return {
        "organizationName": values.get("OrganizationName") or "",
        "logoUrl": values.get("LogoUrl"),
        "customLoginBanner": values.get("CustomLoginBanner"),
        "loginFormPlacement": values.get("LoginFormPlacement") or "left",
    }


@settings_router.post("/brand")
async def set_brand(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_ADMIN)),
):
    service = OrganizationSettingsService(sessions(request))
    service.set_organization_settings("OrganizationName", "Brand", str(body.get("organizationName") or ""))
    logo = body.get("logoUrl")
    service.set_organization_settings("LogoUrl", "Brand", None if logo is None else str(logo))
    banner = body.get("customLoginBanner")
    service.set_organization_settings("CustomLoginBanner", "Brand", None if banner is None else str(banner))
    service.set_organization_settings(
        "LoginFormPlacement", "Brand", str(body.get("loginFormPlacement") or "left")
    )
    sessions(request).commit()
    return Response(status_code=200)


@settings_router.get("/basic")
async def get_basic(request: Request, _user: User = Depends(require_roles(ROLE_ADMIN))):
    service = OrganizationSettingsService(sessions(request))
    values = service.get_settings_by_category("Basic")

    def flag(key: str, default: bool) -> bool:
        raw = values.get(key)
        if raw is None:
            return default
        lowered = str(raw).strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        return default

    return {
        "allowUnregisteredClients": flag("AllowUnregisteredClients", True),
        "customPublicRootUrl": values.get("CustomPublicRootUrl") or "",
        "customPublicApiUrl": values.get("CustomPublicApiUrl") or "",
        "customPublicGrpcUrl": values.get("CustomPublicGrpcUrl") or "",
        "allowPublicRegister": flag("AllowPublicRegister", False),
    }


@settings_router.post("/basic")
async def set_basic(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_ADMIN)),
):
    service = OrganizationSettingsService(sessions(request))
    allow_unregistered = parse_bool(body.get("allowUnregisteredClients"), True)
    allow_public = parse_bool(body.get("allowPublicRegister"), False)
    service.set_organization_settings(
        "AllowUnregisteredClients", "Basic", "True" if allow_unregistered else "False"
    )
    service.set_organization_settings("AllowPublicRegister", "Basic", "True" if allow_public else "False")
    service.set_organization_settings(
        "CustomPublicRootUrl", "Basic", str(body.get("customPublicRootUrl") or "")
    )
    service.set_organization_settings(
        "CustomPublicApiUrl", "Basic", str(body.get("customPublicApiUrl") or "")
    )
    service.set_organization_settings(
        "CustomPublicGrpcUrl", "Basic", str(body.get("customPublicGrpcUrl") or "")
    )
    sessions(request).commit()
    return Response(status_code=200)


@settings_router.post("/complete-oobe")
async def complete_oobe(
    request: Request,
    _user: User = Depends(require_roles(ROLE_ADMIN)),
):
    service = OrganizationSettingsService(sessions(request))
    service.set_organization_settings("IsOobeCompleted", "Oobe", "true")
    sessions(request).commit()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# default settings
# ---------------------------------------------------------------------------

default_settings_router = APIRouter(prefix="/api/v1/default-settings", tags=["default-settings"])


@default_settings_router.get("")
async def list_settings(request: Request, _user: User = Depends(current_user)):
    rows = sessions(request).scalars(select(Setting)).all()
    return [row.to_json() for row in rows]


@default_settings_router.get("/{setting_id}")
async def get_setting(request: Request, setting_id: str, _user: User = Depends(current_user)):
    item = sessions(request).get(Setting, _guid(setting_id))
    if item is None:
        raise _not_found()
    return item.to_json()


@default_settings_router.post("/{setting_id}")
async def update_setting(
    request: Request,
    setting_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(setting_id)
    item = session.get(Setting, payload_id)
    if item is None:
        item = Setting(
            Id=payload_id,
            Name=str(body.get("name") or ""),
            Description=str(body.get("description") or ""),
            Settings=str(body.get("settings") or "{}"),
        )
        session.add(item)
    else:
        item.Name = str(body.get("name") or "")
        item.Description = str(body.get("description") or "")
        item.Settings = str(body.get("settings") or "{}")
    session.flush()
    ObjectsUpdateNotifyService(session).notify_object_updating(payload_id, ObjectTypes.AppSettings)
    session.flush()
    return item.to_json()


@default_settings_router.post("")
async def add_setting(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    item = Setting(
        Id=new_guid(),
        Name=str(body.get("name") or ""),
        Description=str(body.get("description") or ""),
        Settings=str(body.get("settings") or "{}"),
    )
    session.add(item)
    session.flush()
    return item.to_json()


@default_settings_router.delete("/{setting_id}")
async def delete_setting(
    request: Request,
    setting_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    item = session.get(Setting, _guid(setting_id))
    if item is None:
        raise _not_found()
    payload = item.to_json()
    session.delete(item)
    session.flush()
    ObjectsUpdateNotifyService(session).notify_object_updating(_guid(setting_id), ObjectTypes.AppSettings)
    session.flush()
    return payload


# ---------------------------------------------------------------------------
# policies
# ---------------------------------------------------------------------------

policies_router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


@policies_router.get("")
async def list_policies(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), Policy, pageIndex, pageSize, lambda row: row.to_json())


@policies_router.get("/{policy_id}")
async def get_policy(request: Request, policy_id: str, _user: User = Depends(current_user)):
    item = sessions(request).get(Policy, _guid(policy_id))
    if item is None:
        raise _not_found()
    return item.to_json()


def _apply_policy(item: Policy, body: dict[str, Any]) -> None:
    item.Name = str(body.get("name") or "")
    item.IsEnabled = parse_bool(body.get("isEnabled"), True)
    content = body.get("content")
    item.Content = content if isinstance(content, dict) else {}
    group = parse_guid(body.get("groupId"))
    item.GroupId = group or DEFAULT_PROFILE_GROUP_ID


@policies_router.post("/{policy_id}")
async def update_policy(
    request: Request,
    policy_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(policy_id)
    item = session.get(Policy, payload_id)
    if item is None:
        item = Policy(Id=payload_id)
        _apply_policy(item, body)
        session.add(item)
    else:
        _apply_policy(item, body)
    session.flush()
    # Bump PolicyVersion for every client this setting is assigned to. Upstream
    # never notifies on policy edits, so clients would keep serving the old
    # policy until somebody touches the assignment; this closes that gap.
    ObjectsUpdateNotifyService(session).notify_object_updating(payload_id, ObjectTypes.Policy)
    session.flush()
    return item.to_json()


@policies_router.post("")
async def add_policy(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    item = Policy(Id=new_guid())
    _apply_policy(item, body)
    session.add(item)
    session.flush()
    return item.to_json()


@policies_router.delete("/{policy_id}")
async def delete_policy(
    request: Request,
    policy_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    item = session.get(Policy, _guid(policy_id))
    if item is None:
        raise _not_found()
    payload = item.to_json()
    session.delete(item)
    session.flush()
    ObjectsUpdateNotifyService(session).notify_object_updating(_guid(policy_id), ObjectTypes.Policy)
    session.flush()
    return payload


# ---------------------------------------------------------------------------
# assignees
# ---------------------------------------------------------------------------

assignees_router = APIRouter(prefix="/api/v1/assignees", tags=["assignees"])


@assignees_router.get("/all/{assignee_id}")
async def get_assignee(request: Request, assignee_id: int, _user: User = Depends(current_user)):
    item = sessions(request).get(ObjectsAssignee, assignee_id)
    if item is None:
        raise _not_found()
    return item.to_json()


@assignees_router.post("/all/{assignee_id}")
async def update_assignee(
    request: Request,
    assignee_id: int,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    notify = ObjectsUpdateNotifyService(session)
    item = session.get(ObjectsAssignee, assignee_id)
    if item is not None:
        _apply_assignee(item, body)
        item.Id = assignee_id
    else:
        item = ObjectsAssignee(Id=assignee_id)
        _apply_assignee(item, body)
        session.add(item)
    session.flush()
    notify.notify_client_updating(item.TargetClientCuid, item.TargetClientId, item.TargetGroupId)
    return item.to_json()


@assignees_router.post("/all")
async def add_assignee(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    notify = ObjectsUpdateNotifyService(session)
    item = ObjectsAssignee()
    _apply_assignee(item, body)
    item.Id = None  # autoincrement
    session.add(item)
    session.flush()
    notify.notify_client_updating(item.TargetClientCuid, item.TargetClientId, item.TargetGroupId)
    return item.to_json()


@assignees_router.delete("/all/{assignee_id}")
async def delete_assignee(
    request: Request,
    assignee_id: int,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    notify = ObjectsUpdateNotifyService(session)
    item = session.get(ObjectsAssignee, assignee_id)
    if item is None:
        raise _not_found()
    notify.notify_client_updating(item.TargetClientCuid, item.TargetClientId, item.TargetGroupId)
    session.delete(item)
    session.flush()
    return Response(status_code=200)


def _apply_assignee(item: ObjectsAssignee, body: dict[str, Any]) -> None:
    item.ObjectId = parse_guid_or_empty(body.get("objectId"))
    item.ObjectType = int(body.get("objectType") or 0)
    target_client_id = body.get("targetClientId")
    item.TargetClientId = None if target_client_id in (None, "") else str(target_client_id)
    item.TargetClientCuid = parse_guid(body.get("targetClientCuid"))
    target_group_id = body.get("targetGroupId")
    item.TargetGroupId = None if target_group_id in (None, "") else int(target_group_id)
    item.AssigneeType = int(body.get("assigneeType") or 0)


@assignees_router.get("/by-object/assignees/{object_type}/{object_id}")
async def by_object_assignees(
    request: Request,
    object_type: int,
    object_id: str,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    object_id = _guid(object_id)
    return paginate(
        sessions(request),
        ObjectsAssignee,
        pageIndex,
        pageSize,
        lambda row: row.to_json(),
        filters=[
            ObjectsAssignee.ObjectType == object_type,
            ObjectsAssignee.ObjectId == object_id,
        ],
    )


def _state(
    assignee_type: int,
    obj: dict[str, Any],
    assignee: ObjectsAssignee | None,
    created: dt.datetime,
    updated: dt.datetime,
) -> dict[str, Any]:
    return {
        "assigneeType": assignee_type,
        "clientObject": obj,
        "assignee": assignee.to_json() if assignee is not None else None,
        "hasAssignee": assignee is not None,
        "createdTime": fmt_datetime(created),
        "updatedTime": fmt_datetime(updated),
    }


@assignees_router.get("/by-object/clients/{object_type}/{object_id}")
async def by_object_clients(
    request: Request,
    object_type: int,
    object_id: str,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    session = sessions(request)
    object_id = _guid(object_id)
    clients = session.scalars(select(Client).order_by(Client.CreatedTime.asc())).all()
    assignees = session.scalars(
        select(ObjectsAssignee).where(
            ObjectsAssignee.ObjectType == object_type,
            ObjectsAssignee.ObjectId == object_id,
            ObjectsAssignee.AssigneeType == AssigneeTypes.ClientUid,
        )
    ).all()
    index = {item.TargetClientCuid: item for item in assignees if item.TargetClientCuid}
    states = [
        _state(
            AssigneeTypes.ClientUid,
            client.to_json(),
            index.get(client.Cuid),
            client.CreatedTime,
            client.UpdatedTime,
        )
        for client in clients
    ]
    page_index = max(1, pageIndex)
    page_size = pageSize if pageSize > 0 else 20
    start = (page_index - 1) * page_size
    total_pages = -(-len(states) // page_size)
    return {
        "pageIndex": page_index,
        "totalPages": total_pages,
        "pageSize": page_size,
        "itemCount": len(states),
        "items": states[start:start + page_size],
        "hasPreviousPage": page_index > 1,
        "hasNextPage": page_index < total_pages,
    }


@assignees_router.get("/by-object/clients-abstract/{object_type}/{object_id}")
async def by_object_clients_abstract(
    request: Request,
    object_type: int,
    object_id: str,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    session = sessions(request)
    object_id = _guid(object_id)
    clients = session.scalars(select(AbstractClient).order_by(AbstractClient.CreatedTime.asc())).all()
    assignees = session.scalars(
        select(ObjectsAssignee).where(
            ObjectsAssignee.ObjectType == object_type,
            ObjectsAssignee.ObjectId == object_id,
            ObjectsAssignee.AssigneeType == AssigneeTypes.Id,
        )
    ).all()
    index = {item.TargetClientId: item for item in assignees if item.TargetClientId}
    states = [
        _state(
            AssigneeTypes.ClientUid,
            client.to_json(),
            index.get(client.Id),
            client.CreatedTime,
            client.UpdatedTime,
        )
        for client in clients
    ]
    page_index = max(1, pageIndex)
    page_size = pageSize if pageSize > 0 else 20
    start = (page_index - 1) * page_size
    total_pages = -(-len(states) // page_size)
    return {
        "pageIndex": page_index,
        "totalPages": total_pages,
        "pageSize": page_size,
        "itemCount": len(states),
        "items": states[start:start + page_size],
        "hasPreviousPage": page_index > 1,
        "hasNextPage": page_index < total_pages,
    }


@assignees_router.get("/by-object/client-groups/{object_type}/{object_id}")
async def by_object_client_groups(
    request: Request,
    object_type: int,
    object_id: str,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    session = sessions(request)
    object_id = _guid(object_id)
    groups = session.scalars(select(ClientGroup).order_by(ClientGroup.CreatedTime.asc())).all()
    assignees = session.scalars(
        select(ObjectsAssignee).where(
            ObjectsAssignee.ObjectType == object_type,
            ObjectsAssignee.ObjectId == object_id,
            ObjectsAssignee.AssigneeType == AssigneeTypes.Group,
        )
    ).all()
    index = {item.TargetGroupId: item for item in assignees if item.TargetGroupId is not None}
    states = [
        _state(
            AssigneeTypes.ClientUid,
            group.to_json(),
            index.get(group.Id),
            group.CreatedTime,
            group.UpdatedTime,
        )
        for group in groups
    ]
    page_index = max(1, pageIndex)
    page_size = pageSize if pageSize > 0 else 20
    start = (page_index - 1) * page_size
    total_pages = -(-len(states) // page_size)
    return {
        "pageIndex": page_index,
        "totalPages": total_pages,
        "pageSize": page_size,
        "itemCount": len(states),
        "items": states[start:start + page_size],
        "hasPreviousPage": page_index > 1,
        "hasNextPage": page_index < total_pages,
    }
