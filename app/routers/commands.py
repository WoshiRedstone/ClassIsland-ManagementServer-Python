"""Client command delivery controller (``ClientCommandDeliverController``)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response

from .core import sessions
from ..db import ROLE_COMMANDS_USER, User
from ..deps import build_command_service
from ..models import AssigneeTypes, ObjectsAssignee, empty_guid
from ..security import require_roles

commands_router = APIRouter(prefix="/api/v1/client-commands", tags=["commands"])

COMMAND_RESTART_APP = 101
COMMAND_SEND_NOTIFICATION = 102

_PROTO_ROOT = Path(__file__).resolve().parents[2] / "protos"
if str(_PROTO_ROOT) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_PROTO_ROOT))


def _targets(body: dict[str, Any]) -> list[ObjectsAssignee]:
    out: list[ObjectsAssignee] = []
    for raw in body.get("targets") or []:
        if not isinstance(raw, dict):
            continue
        item = ObjectsAssignee()
        item.ObjectId = str(raw.get("objectId") or empty_guid())
        item.ObjectType = int(raw.get("objectType") or 0)
        item.TargetClientId = raw.get("targetClientId")
        item.TargetClientCuid = raw.get("targetClientCuid")
        item.TargetGroupId = raw.get("targetGroupId")
        item.AssigneeType = int(raw.get("assigneeType") or AssigneeTypes.Default)
        out.append(item)
    return out


def _notification_payload(payload: dict[str, Any]) -> bytes:
    """Serialise the JSON body into a ``SendNotification`` protobuf message."""
    from Protobuf.Command import SendNotification_pb2

    message = SendNotification_pb2.SendNotification()
    message.MessageMask = str(payload.get("messageMask") or "")
    message.MessageContent = str(payload.get("messageContent") or "")
    message.OverlayIconLeft = int(payload.get("overlayIconLeft") or 0)
    message.OverlayIconRight = int(payload.get("overlayIconRight") or 0)
    message.IsEmergency = bool(payload.get("isEmergency") or False)
    message.IsSpeechEnabled = bool(payload.get("isSpeechEnabled") or False)
    message.IsEffectEnabled = bool(payload.get("isEffectEnabled") or False)
    message.IsSoundEnabled = bool(payload.get("isSoundEnabled") or False)
    message.IsTopmost = bool(payload.get("isTopmost") or False)
    message.DurationSeconds = float(payload.get("durationSeconds") or 0)
    message.RepeatCounts = int(payload.get("repeatCounts") or 0)
    return message.SerializeToString()


def _empty_payload() -> bytes:
    from google.protobuf.empty_pb2 import Empty

    return Empty().SerializeToString()


@commands_router.post("/show-notification")
async def show_notification(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_COMMANDS_USER)),
):
    service = build_command_service(request)
    data = _notification_payload(body.get("payload") or {})
    for target in _targets(body):
        service.deliver_command(COMMAND_SEND_NOTIFICATION, data, target)
    return Response(status_code=200)


@commands_router.post("/restart-app")
async def restart_app(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict),
    _user: User = Depends(require_roles(ROLE_COMMANDS_USER)),
):
    service = build_command_service(request)
    data = _empty_payload()
    for target in _targets(body):
        service.deliver_command(COMMAND_RESTART_APP, data, target)
    return Response(status_code=200)
