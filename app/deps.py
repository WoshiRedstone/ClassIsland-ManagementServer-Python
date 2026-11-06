"""Shared FastAPI dependencies and helpers for the routers."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ObjectTypes, fmt_datetime
from .services import (
    ClientCommandDeliverService,
    ObjectsAssigneeService,
    ObjectsCacheService,
    ObjectsUpdateNotifyService,
    OrganizationSettingsService,
    ProfileEntitiesService,
)


def error(message: str) -> dict[str, Any]:
    """``new Error(message)`` payload."""
    return {"message": message}


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error(message))


# ---------------------------------------------------------------------------
# request scoped services
# ---------------------------------------------------------------------------


def get_session(request: Request) -> Session:
    return request.state.session


def get_assignee_service(request: Request) -> ObjectsAssigneeService:
    return ObjectsAssigneeService(get_session(request))


def get_notify_service(request: Request) -> ObjectsUpdateNotifyService:
    return ObjectsUpdateNotifyService(get_session(request))


def get_cache(request: Request) -> ObjectsCacheService:
    return request.app.state.cache


def get_connections(request: Request):
    return request.app.state.connections


def build_profile_service(request: Request) -> ProfileEntitiesService:
    session = get_session(request)
    return ProfileEntitiesService(session, request.app.state.cache, ObjectsUpdateNotifyService(session))


def build_command_service(request: Request) -> ClientCommandDeliverService:
    session = get_session(request)
    return ClientCommandDeliverService(session, request.app.state.connections)


# ---------------------------------------------------------------------------
# pagination helpers
# ---------------------------------------------------------------------------


def paginate(
    session: Session,
    model: Any,
    page_index: int,
    page_size: int,
    serialize: Callable[[Any], Any],
    filters: Sequence[Any] | None = None,
    order_by_updated: bool = False,
    decreasing: bool = False,
) -> dict[str, Any]:
    """``PaginatedList<T>.CreateAsync`` equivalent."""
    if page_index <= 0:
        page_index = 1
    if page_size <= 0:
        page_size = 20
    column = model.UpdatedTime if order_by_updated else model.CreatedTime
    stmt = select(model)
    if filters:
        for item in filters:
            stmt = stmt.where(item)
    stmt = stmt.order_by(column.desc() if decreasing else column.asc())
    rows = session.scalars(stmt).all()
    count = len(rows)
    start = (page_index - 1) * page_size
    chunk = rows[start:start + page_size]
    total_pages = -(-count // page_size) if page_size else 0
    return {
        "pageIndex": page_index,
        "totalPages": total_pages,
        "pageSize": page_size,
        "itemCount": count,
        "items": [serialize(row) for row in chunk],
        "hasPreviousPage": page_index > 1,
        "hasNextPage": page_index < total_pages,
    }
