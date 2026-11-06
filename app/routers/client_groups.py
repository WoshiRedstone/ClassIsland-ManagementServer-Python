"""Client group controller.

Port of ``ClientGroupController`` from the original server
(``Route("api/v1/client_groups")``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from .core import sessions
from ..db import ROLE_CLIENTS_DELETE, ROLE_CLIENTS_WRITE, User
from ..deps import error, error_response, paginate
from ..models import (
    DEFAULT_GROUP_ID,
    GLOBAL_GROUP_ID,
    AbstractClient,
    Client,
    ClientGroup,
)
from ..security import current_user, require_roles

client_groups_router = APIRouter(prefix="/api/v1/client_groups", tags=["client-groups"])


@client_groups_router.get("")
async def list_groups(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(current_user),
):
    session = sessions(request)
    return paginate(session, ClientGroup, pageIndex, pageSize, lambda g: g.to_json())


@client_groups_router.get("/{group_id}")
async def get_group(request: Request, group_id: int, _user: User = Depends(current_user)):
    session = sessions(request)
    group = session.get(ClientGroup, group_id)
    if group is None:
        return error_response("找不到请求的对象", 404)
    return group.to_json()


@client_groups_router.put("")
async def create_group(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_CLIENTS_WRITE)),
):
    session = sessions(request)
    group = ClientGroup(
        Name=str(body.get("name") or ""),
        ColorHex=str(body.get("colorHex") or "#66CCFF"),
    )
    session.add(group)
    session.flush()
    return group.to_json()


@client_groups_router.put("/{group_id}")
async def update_group(
    request: Request,
    group_id: int,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_CLIENTS_WRITE)),
):
    session = sessions(request)
    group = session.get(ClientGroup, group_id)
    if group is None:
        return error_response("找不到请求的对象", 404)
    # ``DbContext.Entry(group).State = Modified`` writes every column from the
    # request body, so absent fields fall back to the entity defaults.
    group.Name = str(body.get("name") or "")
    group.ColorHex = str(body.get("colorHex") or "#66CCFF")
    session.flush()
    return Response(status_code=200)


@client_groups_router.delete("/{group_id}")
async def delete_group(
    request: Request,
    group_id: int,
    _user: User = Depends(require_roles(ROLE_CLIENTS_DELETE)),
):
    session = sessions(request)
    group = session.get(ClientGroup, group_id)
    if group is None:
        return error_response("找不到请求的对象", 404)
    if group_id in (DEFAULT_GROUP_ID, GLOBAL_GROUP_ID):
        return error_response("不能删除默认组或全局分组", 400)

    # Re-home every abstract client that belonged to this group, exactly like
    # the original controller (``i.GroupId = ClientGroup.DefaultGroupId``).
    for item in session.scalars(
        select(AbstractClient).where(AbstractClient.GroupId == group_id)
    ).all():
        item.GroupId = DEFAULT_GROUP_ID

    session.delete(group)
    session.flush()
    return Response(status_code=200)
