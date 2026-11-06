"""Profile related controllers: subjects, time layouts, class plans, groups."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import delete, select

from .core import _guid, _not_found, sessions
from ..db import ROLE_OBJECTS_DELETE, ROLE_OBJECTS_WRITE, User
from ..deps import build_profile_service, error, get_notify_service, paginate
from ..models import (
    DEFAULT_PROFILE_GROUP_ID,
    EMPTY_GUID,
    ObjectTypes,
    ProfileClassPlanClass,
    ProfileClassplan,
    ProfileGroup,
    ProfileSubject,
    ProfileTimeLayout,
    ProfileTimeLayoutTimePoint,
    new_guid,
    ci_get,
    parse_guid,
    parse_guid_or_empty,
)
from ..security import current_user, require_roles

profiles_router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


# ---------------------------------------------------------------------------
# groups
# ---------------------------------------------------------------------------


@profiles_router.get("/groups")
async def list_groups(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), ProfileGroup, pageIndex, pageSize, lambda row: row.to_json())


@profiles_router.put("/groups/{group_id}")
async def update_group(
    request: Request,
    group_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(group_id)
    item = session.get(ProfileGroup, payload_id)
    if item is None:
        raise _not_found()
    item.Name = str(ci_get(body, "name") or "")
    item.Description = str(ci_get(body, "description") or "")
    item.ColorHex = str(ci_get(body, "colorHex") or "#66CCFF")
    session.flush()
    return Response(status_code=200)


@profiles_router.put("/groups")
async def add_group(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    item = ProfileGroup(
        Id=new_guid(),
        Name=str(ci_get(body, "name") or ""),
        Description=str(ci_get(body, "description") or ""),
        ColorHex=str(ci_get(body, "colorHex") or "#66CCFF"),
    )
    session.add(item)
    session.flush()
    return Response(status_code=200)


@profiles_router.delete("/groups/{group_id}")
async def delete_group(
    request: Request,
    group_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    payload_id = _guid(group_id)
    item = session.get(ProfileGroup, payload_id)
    if item is None:
        raise _not_found()
    if payload_id == DEFAULT_PROFILE_GROUP_ID:
        raise HTTPException(status_code=400, detail=error("不能删除默认分组"))
    session.delete(item)
    session.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# subjects
# ---------------------------------------------------------------------------


@profiles_router.get("/subjects")
async def list_subjects(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), ProfileSubject, pageIndex, pageSize, lambda row: row.to_json())


@profiles_router.put("/subjects/{subject_id}")
async def update_subject(
    request: Request,
    subject_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(subject_id)
    item = session.get(ProfileSubject, payload_id)
    if item is None:
        raise _not_found()
    item.Name = str(ci_get(body, "name") or "")
    item.Initials = str(ci_get(body, "initial") or ci_get(body, "initials") or "")
    item.IsOutDoor = bool(ci_get(body, "isOutDoor") or False)
    item.AttachedObjects = ci_get(body, "attachedObjects") or {}
    group = parse_guid(ci_get(body, "groupId"))
    if group:
        item.GroupId = group
    session.flush()
    request.app.state.cache.invalidate_cache(ObjectTypes.ProfileSubject, payload_id)
    # Push the change to every client this subject is assigned to; without this
    # the client manifest version never advances and clients keep stale data.
    get_notify_service(request).notify_object_updating(payload_id, ObjectTypes.ProfileSubject)
    session.flush()
    return Response(status_code=200)


@profiles_router.put("/subjects")
async def add_subject(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    # The original assigns ``Guid.Empty`` to added entities; we honour an id sent
    # by the WebUI (it generates one client side) and fall back to a fresh one so
    # repeated creations cannot collide on the primary key.
    payload_id = parse_guid(ci_get(body, "id")) or new_guid()
    existing = session.get(ProfileSubject, payload_id)
    if existing is not None:
        # The WebUI can re-send a subject it already created; treat the PUT as
        # an update instead of failing on the primary key.
        existing.Name = str(ci_get(body, "name") or "")
        existing.Initials = str(ci_get(body, "initial") or ci_get(body, "initials") or "")
        existing.IsOutDoor = bool(ci_get(body, "isOutDoor") or False)
        existing.AttachedObjects = ci_get(body, "attachedObjects") or {}
        group = parse_guid(ci_get(body, "groupId"))
        if group:
            existing.GroupId = group
        session.flush()
        request.app.state.cache.invalidate_cache(ObjectTypes.ProfileSubject, payload_id)
        get_notify_service(request).notify_object_updating(payload_id, ObjectTypes.ProfileSubject)
        session.flush()
        return Response(status_code=200)
    item = ProfileSubject(
        Id=payload_id,
        Name=str(ci_get(body, "name") or ""),
        Initials=str(ci_get(body, "initial") or ci_get(body, "initials") or ""),
        IsOutDoor=bool(ci_get(body, "isOutDoor") or False),
        AttachedObjects=ci_get(body, "attachedObjects") or {},
        GroupId=parse_guid(ci_get(body, "groupId")) or DEFAULT_PROFILE_GROUP_ID,
    )
    session.add(item)
    session.flush()
    return Response(status_code=200)


@profiles_router.delete("/subjects/{subject_id}")
async def delete_subject(
    request: Request,
    subject_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    payload_id = _guid(subject_id)
    item = session.get(ProfileSubject, payload_id)
    if item is None:
        raise _not_found()
    session.delete(item)
    session.flush()
    request.app.state.cache.invalidate_cache(ObjectTypes.ProfileSubject, payload_id)
    # Same reasoning as the update path above: deleting an assigned subject has
    # to bump the client manifest versions, otherwise clients keep serving the
    # removed subject from their local copy.
    get_notify_service(request).notify_object_updating(payload_id, ObjectTypes.ProfileSubject)
    session.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# time layouts
# ---------------------------------------------------------------------------


@profiles_router.get("/timeLayouts")
async def list_time_layouts(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), ProfileTimeLayout, pageIndex, pageSize, lambda row: row.to_json())


@profiles_router.get("/timeLayouts/{time_layout_id}")
async def get_time_layout(request: Request, time_layout_id: str, _user: User = Depends(current_user)):
    service = build_profile_service(request)
    payload = service.get_time_layout_entity(_guid(time_layout_id))
    if payload is None:
        raise _not_found()
    return payload


@profiles_router.put("/timeLayouts/{time_layout_id}")
async def update_time_layout(
    request: Request,
    time_layout_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(time_layout_id)
    if session.get(ProfileTimeLayout, payload_id) is None:
        raise _not_found()
    build_profile_service(request).set_time_layout_entity(payload_id, body, True)
    session.flush()
    return Response(status_code=200)


@profiles_router.put("/timeLayouts")
async def add_time_layout(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = parse_guid(ci_get(body, "id")) or new_guid()
    build_profile_service(request).set_time_layout_entity(payload_id, body, False)
    session.flush()
    return Response(status_code=200)


@profiles_router.delete("/timeLayouts/{time_layout_id}")
async def delete_time_layout(
    request: Request,
    time_layout_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    payload_id = _guid(time_layout_id)
    item = session.get(ProfileTimeLayout, payload_id)
    if item is None:
        raise _not_found()
    referencing = session.scalars(
        select(ProfileClassplan).where(ProfileClassplan.TimeLayoutId == payload_id)
    ).first()
    if referencing is not None:
        raise HTTPException(status_code=400, detail=error("不能删除此时间表，因为有课表引用了此时间表"))
    session.delete(item)
    session.flush()
    request.app.state.cache.invalidate_cache(ObjectTypes.ProfileTimeLayout, payload_id)
    get_notify_service(request).notify_object_updating(payload_id, ObjectTypes.ProfileTimeLayout)
    session.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# class plans
# ---------------------------------------------------------------------------


@profiles_router.get("/classPlans")
async def list_class_plans(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    return paginate(sessions(request), ProfileClassplan, pageIndex, pageSize, lambda row: row.to_json())


@profiles_router.get("/classPlans/{class_plan_id}")
async def get_class_plan(request: Request, class_plan_id: str, _user: User = Depends(current_user)):
    payload_id = _guid(class_plan_id)
    service = build_profile_service(request)
    payload = service.get_class_plan_entity(payload_id)
    if payload is None:
        raise _not_found()
    session = sessions(request)
    item = session.get(ProfileClassplan, payload_id)
    subject_names = []
    if item is not None:
        for entry in sorted(item.Classes, key=lambda c: c.Index):
            subject = session.get(ProfileSubject, entry.SubjectId)
            subject_names.append(subject.Name if subject is not None else "")
    return {"classPlan": payload, "classNames": subject_names}


@profiles_router.put("/classPlans/{class_plan_id}")
async def update_class_plan(
    request: Request,
    class_plan_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = _guid(class_plan_id)
    if session.get(ProfileClassplan, payload_id) is None:
        raise _not_found()
    build_profile_service(request).set_class_plan_entity(payload_id, body, True)
    session.flush()
    return Response(status_code=200)


@profiles_router.put("/classPlans")
async def add_class_plan(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    payload_id = parse_guid(ci_get(body, "id")) or new_guid()
    build_profile_service(request).set_class_plan_entity(payload_id, body, False)
    session.flush()
    return Response(status_code=200)


@profiles_router.delete("/classPlans/{class_plan_id}")
async def delete_class_plan(
    request: Request,
    class_plan_id: str,
    _user: User = Depends(require_roles(ROLE_OBJECTS_DELETE)),
):
    session = sessions(request)
    payload_id = _guid(class_plan_id)
    item = session.get(ProfileClassplan, payload_id)
    if item is None:
        raise _not_found()
    session.delete(item)
    session.flush()
    request.app.state.cache.invalidate_cache(ObjectTypes.ProfileClassPlan, payload_id)
    get_notify_service(request).notify_object_updating(payload_id, ObjectTypes.ProfileClassPlan)
    session.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# profile upload
# ---------------------------------------------------------------------------


@profiles_router.post("/upload")
async def upload_profile(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    replace: bool = Query(default=False),
    groupId: str | None = Query(default=None),
    _user: User = Depends(require_roles(ROLE_OBJECTS_WRITE)),
):
    session = sessions(request)
    group_id = parse_guid(groupId) or DEFAULT_PROFILE_GROUP_ID
    service = build_profile_service(request)
    for key, value in (ci_get(body, "subjects") or {}).items():
        service.set_subject_entity(parse_guid_or_empty(key), value or {}, replace, group_id)
    session.flush()
    for key, value in (ci_get(body, "timeLayouts") or {}).items():
        service.set_time_layout_entity(parse_guid_or_empty(key), value or {}, replace, group_id)
    session.flush()
    for key, value in (ci_get(body, "classPlans") or {}).items():
        service.set_class_plan_entity(parse_guid_or_empty(key), value or {}, replace, group_id)
    session.flush()
    return Response(status_code=200)
