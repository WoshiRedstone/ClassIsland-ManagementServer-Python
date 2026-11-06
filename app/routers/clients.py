"""Client registry, manifest and object delivery controllers.

Ports of ``ClientRegistryController``, ``ManifestController`` and
``ObjectsDeliveryController`` from the original server.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import delete, select

from .core import _guid, _not_found, sessions
from ..db import ROLE_CLIENTS_DELETE, ROLE_CLIENTS_WRITE, User
from ..deps import build_profile_service, error, paginate
from ..models import (
    AbstractClient,
    Client,
    ClientGroup,
    ObjectTypes,
    ObjectUpdate,
    Policy,
    ProfileClassplan,
    ProfileSubject,
    ProfileTimeLayout,
    Setting,
    new_guid,
    now,
    parse_guid,
    parse_guid_or_empty,
)
from ..security import current_user, require_roles

registry_router = APIRouter(prefix="/api/v1/clients_registry", tags=["clients"])
manifest_router = APIRouter(prefix="/api/v1/client", tags=["clients"])
delivery_router = APIRouter(prefix="/api/v1/client", tags=["clients"])

# ``ManagementSettings`` defaults used by ``client_configure``.
MANAGEMENT_SERVER_KIND = 1


def _management_settings(request: Request) -> dict[str, Any]:
    from ..models import OrganizationSettings

    session = sessions(request)
    public_api = session.get(OrganizationSettings, "CustomPublicApiUrl")
    public_grpc = session.get(OrganizationSettings, "CustomPublicGrpcUrl")
    api_value = (public_api.Value or "") if public_api is not None else ""
    grpc_value = (public_grpc.Value or "") if public_grpc is not None else ""
    if not api_value.strip():
        api_value = str(request.app.state.config.api_url or "")
    if not grpc_value.strip():
        grpc_value = str(request.app.state.config.grpc_url or "")
    # 键名必须是 PascalCase：客户端用 ConfigureFileHelper.LoadConfig<T> 读取这个文件，
    # 它用的是默认 JsonSerializerOptions（大小写敏感、无 camelCase 策略）。上游
    # C# 侧 `JsonSerializer.Serialize(new ManagementSettings())` 走默认选项，产出
    # 的也是 PascalCase；写成 camelCase 会被静默忽略，得到一个全默认的对象。
    return {
        "IsManagementEnabled": False,
        "ManagementServerKind": MANAGEMENT_SERVER_KIND,
        "ManagementServer": api_value,
        "ManagementServerGrpc": grpc_value,
        "ManifestUrlTemplate": "",
        "ClassIdentity": "",
    }


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


@registry_router.get("/all")
async def list_clients(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), Client, pageIndex, pageSize, lambda row: row.to_json())


@registry_router.get("/abstract")
async def list_abstract_clients(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(
        sessions(request), AbstractClient, pageIndex, pageSize, lambda row: row.to_json()
    )


@registry_router.put("/abstract")
async def create_abstract_client(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_CLIENTS_WRITE)),
):
    session = sessions(request)
    item = AbstractClient(
        Id=str(body.get("id") or ""),
        GroupId=int(body.get("groupId") or 1),
    )
    if body.get("internalId"):
        item.InternalId = int(body["internalId"])
    session.add(item)
    session.flush()
    return item.to_json()


@registry_router.put("/abstract/{internal_id}")
async def update_abstract_client(
    request: Request,
    internal_id: int,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_CLIENTS_WRITE)),
):
    session = sessions(request)
    item = session.scalars(
        select(AbstractClient).where(AbstractClient.InternalId == internal_id)
    ).first()
    if item is None:
        raise _not_found()
    item.Id = str(body.get("id") or item.Id)
    item.GroupId = int(body.get("groupId") or item.GroupId)
    session.flush()
    return Response(status_code=200)


@registry_router.delete("/abstract/{internal_id}")
async def delete_abstract_client(
    request: Request,
    internal_id: int,
    _user: User = Depends(require_roles(ROLE_CLIENTS_DELETE)),
):
    session = sessions(request)
    item = session.scalars(
        select(AbstractClient).where(AbstractClient.InternalId == internal_id)
    ).first()
    if item is None:
        raise _not_found()
    session.delete(item)
    session.flush()
    return Response(status_code=200)


@registry_router.delete("/unregister")
async def unregister_client(
    request: Request,
    Cuid: str = Query(default=""),
    _user: User = Depends(require_roles(ROLE_CLIENTS_DELETE)),
):
    session = sessions(request)
    cuid = parse_guid(Cuid) or Cuid
    item = session.get(Client, cuid) if cuid else None
    if item is None:
        # The original returns a bare string here, not the Error record.
        return JSONResponse(status_code=400, content="实例还没有注册。")
    session.delete(item)
    session.flush()
    return Response(status_code=200)


@registry_router.get("/query/{cuid}")
async def query_client(request: Request, cuid: str, _user: User = Depends(current_user)):
    session = sessions(request)
    item = session.get(Client, _guid(cuid))
    if item is None:
        return JSONResponse(status_code=400, content="实例还没有注册。")
    return item.to_json()


@registry_router.get("/client_configure")
async def download_client_configure(request: Request):
    payload = _management_settings(request)
    body = json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":"))
    return Response(
        content=body.encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                "attachment; filename=ManagementPreset.json;"
                " filename*=UTF-8''ManagementPreset.json"
            )
        },
    )


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

_VERSION_COLUMNS = {
    ObjectTypes.ProfileClassPlan: "ClassPlanVersion",
    ObjectTypes.ProfileTimeLayout: "TimeLayoutVersion",
    ObjectTypes.ProfileSubject: "SubjectsVersion",
    ObjectTypes.Policy: "PolicyVersion",
    ObjectTypes.AppSettings: "DefaultSettingsVersion",
}


@manifest_router.get("/{cuid}/manifest")
async def get_manifest(request: Request, cuid: str):
    session = sessions(request)
    client = session.get(Client, _guid(cuid))
    if client is None:
        raise _not_found()

    for object_type, column in _VERSION_COLUMNS.items():
        rows = session.scalars(
            select(ObjectUpdate).where(
                ObjectUpdate.TargetCuid == client.Cuid,
                ObjectUpdate.ObjectType == object_type,
            )
        ).all()
        if rows:
            setattr(client, column, getattr(client, column) + 1)
            session.execute(
                delete(ObjectUpdate).where(
                    ObjectUpdate.TargetCuid == client.Cuid,
                    ObjectUpdate.ObjectType == object_type,
                )
            )

    remaining = session.scalars(
        select(ObjectUpdate).where(ObjectUpdate.TargetCuid == client.Cuid)
    ).all()
    if remaining:
        for column in _VERSION_COLUMNS.values():
            setattr(client, column, getattr(client, column) + 1)
        session.execute(delete(ObjectUpdate).where(ObjectUpdate.TargetCuid == client.Cuid))

    session.flush()

    from ..models import OrganizationSettings

    organization = session.get(OrganizationSettings, "OrganizationName")
    organization_name = (organization.Value or "") if organization is not None else ""

    return {
        "organizationName": organization_name,
        "serverKind": 1,
        # ClassIsland 2.x refuses to join when the manifest core version's major
        # does not match ``IAppHost.CoreVersion`` (2.0.0.0), see
        # ManagementService.cs:179. System.Version is serialized as a string.
        "coreVersion": "2.0.0.0",
        "subjectsSource": {
            "value": "{host}/api/v1/client/{cuid}/subjects",
            "version": client.SubjectsVersion,
        },
        "timeLayoutSource": {
            "value": "{host}/api/v1/client/{cuid}/timelayouts",
            "version": client.TimeLayoutVersion,
        },
        "classPlanSource": {
            "value": "{host}/api/v1/client/{cuid}/classplans",
            "version": client.ClassPlanVersion,
        },
        "policySource": {
            "value": "{host}/api/v1/client/{cuid}/policy",
            "version": client.PolicyVersion,
        },
        "defaultSettingsSource": {
            "value": "{host}/api/v1/client/{cuid}/default-settings",
            "version": client.DefaultSettingsVersion,
        },
        # Added by ClassIsland 2.1. Left empty on purpose: a null/blank "value"
        # makes ``ReVersionString.IsNewerAndNotNull`` return false, so clients
        # never try to fetch them (we do not manage credentials/components).
        "credentialSource": {"value": None, "version": 0},
        "componentsSource": {"value": None, "version": 0},
    }


# ---------------------------------------------------------------------------
# object delivery
# ---------------------------------------------------------------------------


def _client_or_404(request: Request, cuid: str) -> Client:
    session = sessions(request)
    client = session.get(Client, _guid(cuid))
    if client is None:
        raise _not_found()
    return client


def _empty_profile() -> dict[str, Any]:
    """Empty ``Profile`` payload including the auto-created class plan groups.

    ``Profile``'s constructor always injects the default and global class plan
    groups, whose ids come from ``ClassPlanGroup`` itself: the default group is
    ``ACAF4EF0-E261-4262-B941-34EA93CB4369`` (not the profile-group guid) and the
    global one is ``Guid.Empty``. ``TempClassPlanGroupType`` defaults to
    ``Inherit`` (1).
    """
    timestamp = now().strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "name": "",
        "timeLayouts": {},
        "classPlans": {},
        "subjects": {},
        "isOverlayClassPlanEnabled": False,
        "overlayClassPlanId": None,
        "tempClassPlanId": None,
        "tempClassPlanSetupTime": timestamp,
        "classPlanGroups": {
            "acaf4ef0-e261-4262-b941-34ea93cb4369": {"name": "默认", "isGlobal": False},
            "00000000-0000-0000-0000-000000000000": {
                "name": "全局课表群",
                "isGlobal": True,
            },
        },
        "selectedClassPlanGroupId": "acaf4ef0-e261-4262-b941-34ea93cb4369",
        "tempClassPlanGroupId": None,
        "tempClassPlanGroupExpireTime": timestamp,
        "isTempClassPlanGroupEnabled": False,
        "tempClassPlanGroupType": 1,
        # ClassIsland 2.1 additions.
        "id": "00000000-0000-0000-0000-000000000000",
        "orderedSchedules": {},
    }


def _deliver_objects(request: Request, cuid: str, object_type: int, key: str) -> dict[str, Any]:
    session = sessions(request)
    client = _client_or_404(request, cuid)
    service = build_profile_service(request)
    from ..services import ObjectsAssigneeService

    assignee_service = ObjectsAssigneeService(session)
    payload: dict[str, Any] = {}

    getter = {
        "subjects": service.get_subject_entity,
        "timeLayouts": service.get_time_layout_entity,
        "classPlans": service.get_class_plan_entity,
    }[key]
    model = {
        "subjects": ProfileSubject,
        "timeLayouts": ProfileTimeLayout,
        "classPlans": ProfileClassplan,
    }[key]

    for assignee in assignee_service.get_client_assigning_objects(client, object_type):
        entity = getter(assignee.ObjectId)
        if entity is not None:
            payload[assignee.ObjectId] = entity

    for group in assignee_service.get_client_assigning_objects(client, ObjectTypes.Group):
        rows = session.scalars(select(model).where(model.GroupId == group.ObjectId)).all()
        for row in rows:
            if row.Id in payload:
                continue
            entity = getter(row.Id)
            if entity is not None:
                payload[row.Id] = entity

    return payload


@delivery_router.get("/{cuid}/subjects")
async def get_subjects(request: Request, cuid: str):
    data = _deliver_objects(request, cuid, ObjectTypes.ProfileSubject, "subjects")
    profile = _empty_profile()
    profile["subjects"] = data
    return profile


@delivery_router.get("/{cuid}/timelayouts")
async def get_time_layouts(request: Request, cuid: str):
    data = _deliver_objects(request, cuid, ObjectTypes.ProfileTimeLayout, "timeLayouts")
    profile = _empty_profile()
    profile["timeLayouts"] = data
    return profile


@delivery_router.get("/{cuid}/classplans")
async def get_class_plans(request: Request, cuid: str):
    data = _deliver_objects(request, cuid, ObjectTypes.ProfileClassPlan, "classPlans")
    profile = _empty_profile()
    profile["classPlans"] = data
    return profile


@delivery_router.get("/{cuid}/policy")
async def get_policy(request: Request, cuid: str):
    session = sessions(request)
    client = _client_or_404(request, cuid)
    from ..services import ObjectsAssigneeService

    assignees = ObjectsAssigneeService(session).get_client_assigning_objects_leveled(
        client, ObjectTypes.Policy
    )
    for assignee in assignees:
        policy = session.get(Policy, assignee.ObjectId)
        if policy is not None and policy.IsEnabled:
            return policy.Content if policy.Content is not None else {}
    return {
        "disableProfileClassPlanEditing": False,
        "disableProfileTimeLayoutEditing": False,
        "disableProfileSubjectsEditing": False,
        "disableProfileEditing": False,
        "disableSettingsEditing": False,
        "disableSplashCustomize": False,
        "disableDebugMenu": False,
        "allowExitManagement": True,
        # ClassIsland 2.1 addition.
        "disableEasterEggs": False,
    }


@delivery_router.get("/{cuid}/default-settings")
async def get_default_settings(request: Request, cuid: str):
    session = sessions(request)
    client = _client_or_404(request, cuid)
    from ..services import ObjectsAssigneeService

    assignees = ObjectsAssigneeService(session).get_client_assigning_objects_leveled(
        client, ObjectTypes.AppSettings
    )
    for assignee in assignees:
        setting = session.get(Setting, assignee.ObjectId)
        if setting is not None:
            # The original answers with a raw JSON *string*.
            return Response(
                content=str(setting.Settings or "{}"),
                media_type="application/json",
            )
    return {
        "disableProfileClassPlanEditing": False,
        "disableProfileTimeLayoutEditing": False,
        "disableProfileSubjectsEditing": False,
        "disableProfileEditing": False,
        "disableSettingsEditing": False,
        "disableSplashCustomize": False,
        "disableDebugMenu": False,
        "allowExitManagement": True,
        # ClassIsland 2.1 addition (the original answers ``new ManagementPolicy()``).
        "disableEasterEggs": False,
    }
