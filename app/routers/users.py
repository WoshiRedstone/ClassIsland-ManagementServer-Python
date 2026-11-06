"""Identity user management controller (``UsersController``)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from .core import _not_found, _user_info, sessions
from ..db import ROLE_ADMIN, ROLE_USERS_MANAGER, Role, User, UserRole
from ..deps import error, paginate
from ..models import fmt_datetime, new_guid, now
from ..security import current_user, hash_password, require_roles

users_router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _info(user: User) -> dict[str, Any]:
    """``GetUserInfoFromUser`` with ``RedirectToOobe`` left at its default."""
    return {
        "userName": user.UserName or "",
        "name": user.Name or "",
        "emailAddress": user.Email or "",
        "phoneNumber": user.PhoneNumber or "",
        "id": user.Id,
        "allowChangePassword": bool(user.AllowChangePassword),
        "roles": list(user.role_names),
        "redirectToOobe": False,
        "createdTime": fmt_datetime(user.CreatedTime),
        "updatedTime": fmt_datetime(user.UpdatedTime),
    }


def _role_ids_from_body(body: dict[str, Any]) -> list[str]:
    roles = body.get("user", {}).get("roles") if isinstance(body.get("user"), dict) else None
    if roles is None:
        roles = body.get("roles")
    if not roles:
        return []
    out: list[str] = []
    for item in roles:
        if isinstance(item, dict):
            name = item.get("name") or item.get("id") or ""
        else:
            name = str(item)
        if name:
            out.append(name)
    return out


def _apply_user_fields(user: User, source: dict[str, Any]) -> None:
    if "name" in source and source["name"] is not None:
        user.Name = str(source["name"])
    if "emailAddress" in source:
        user.Email = source["emailAddress"]
    elif "email" in source:
        user.Email = source["email"]
    if "phoneNumber" in source:
        user.PhoneNumber = source["phoneNumber"]
    if "allowChangePassword" in source:
        user.AllowChangePassword = int(bool(source["allowChangePassword"]))
    user.UpdatedTime = now()


def _set_roles(session, user: User, add: list[str], remove: list[str]) -> None:
    existing = {r.RoleId for r in session.scalars(
        select(UserRole).where(UserRole.UserId == user.Id)
    ).all()}
    for role in add:
        if role and role not in existing:
            session.add(UserRole(UserId=user.Id, RoleId=role))
    for role in remove:
        row = session.scalars(
            select(UserRole).where(UserRole.UserId == user.Id, UserRole.RoleId == role)
        ).first()
        if row is not None:
            session.delete(row)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@users_router.post("/create")
async def create_user(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_USERS_MANAGER)),
):
    session = sessions(request)
    payload = body.get("user") or {}
    user_name = str(payload.get("userName") or "")
    password = str(body.get("password") or "")

    if not user_name:
        return _bad("创建用户失败：用户名不可为空")
    exists = session.scalars(select(User).where(User.UserName == user_name)).first()
    if exists is not None:
        return _bad("创建用户失败：用户名已被占用")

    user = User(
        Id=new_guid(),
        UserName=user_name,
        NormalizedUserName=user_name.upper(),
        Name=str(payload.get("name") or ""),
        Email=payload.get("email") or None,
        PhoneNumber=payload.get("phoneNumber") or None,
        AllowChangePassword=int(bool(payload.get("allowChangePassword", True))),
        PasswordHash=hash_password(password) if password else None,
        SecurityStamp=new_guid().replace("-", ""),
        CreatedTime=now(),
        UpdatedTime=now(),
    )
    session.add(user)
    session.flush()
    _set_roles(session, user, _role_ids_from_body(body), [])
    session.flush()
    return _info(user)


@users_router.get("/all")
async def list_users(
    request: Request,
    pageIndex: int = Query(default=1),
    pageSize: int = Query(default=20),
    _user: User = Depends(require_roles(ROLE_USERS_MANAGER)),
):
    session = sessions(request)
    result = paginate(
        session, User, pageIndex, pageSize, lambda row: _info(row)
    )
    # The controller re-paginates the already serialised list, so the payload
    # carries the mapped items while the counters describe them.
    return result


@users_router.post("/{user_id}")
async def update_user(
    request: Request,
    user_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    current: User = Depends(require_roles(ROLE_USERS_MANAGER)),
):
    session = sessions(request)
    user = session.get(User, user_id)
    if user is None:
        return _not_found_message()
    if current is None:
        return _bad("登录状态无效")

    add = _role_ids_from_body(body)
    owned = set(current.role_names)
    extra = [r for r in add if r not in owned]
    if extra:
        return _bad("不能为用户添加自身拥有的角色以外的角色")

    _apply_user_fields(user, body.get("user") or body)
    _set_roles(session, user, add, [])
    session.flush()
    return _info(user)


@users_router.delete("/{user_id}")
async def delete_user(
    request: Request,
    user_id: str,
    _user: User = Depends(require_roles(ROLE_USERS_MANAGER)),
):
    session = sessions(request)
    user = session.get(User, user_id)
    if user is None:
        return _not_found_message()
    if (user.UserName or "") == "root":
        return _bad("无法删除 root 用户")
    session.delete(user)
    session.flush()
    return Response(status_code=200)


@users_router.post("/{user_id}/set-password")
async def set_password(
    request: Request,
    user_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_USERS_MANAGER)),
):
    session = sessions(request)
    user = session.get(User, user_id)
    if user is None:
        return _not_found_message()
    password = str(body.get("password") or body.get("newPassword") or "")
    if not password:
        return _bad("设置密码失败：密码不可为空")
    user.PasswordHash = hash_password(password)
    user.SecurityStamp = new_guid().replace("-", "")
    user.UpdatedTime = now()
    session.flush()
    return Response(status_code=200)


@users_router.get("/current")
async def get_current_user(request: Request, user: User = Depends(current_user)):
    session = sessions(request)
    if user is None:
        return _not_found_message()
    from ..services import OrganizationSettingsService

    info = _info(user)
    settings = OrganizationSettingsService(session)
    info["redirectToOobe"] = (
        settings.get_settings("IsOobeCompleted") != "true"
        and ROLE_ADMIN in set(user.role_names)
    )
    return info


@users_router.post("/current")
async def update_current_user(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(current_user),
):
    session = sessions(request)
    if user is None:
        return _not_found_message()
    _apply_user_fields(user, body)
    session.flush()
    return {
        "userName": user.UserName or "",
        "name": user.Name or "",
        "emailAddress": user.Email or "",
        "phoneNumber": user.PhoneNumber or "",
        "id": user.Id,
        "allowChangePassword": bool(user.AllowChangePassword),
        "roles": [],
        "redirectToOobe": False,
        "createdTime": fmt_datetime(user.CreatedTime),
        "updatedTime": fmt_datetime(user.UpdatedTime),
    }


@users_router.post("/change-password")
async def change_password(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    user: User = Depends(current_user),
):
    session = sessions(request)
    if user is None:
        return _not_found_message()
    if not bool(user.AllowChangePassword):
        return _bad("当前用户不允许修改密码")
    password = str(body.get("newPassword") or "")
    if not password:
        return _bad("修改密码失败：密码不可为空")
    user.PasswordHash = hash_password(password)
    user.SecurityStamp = new_guid().replace("-", "")
    user.UpdatedTime = now()
    session.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _bad(message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content=error(message))


def _not_found_message():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content=error("当前用户信息未找到。"))
