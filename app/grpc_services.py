"""gRPC services mirroring ``Services/Grpc/*.cs``.

The generated stubs live in ``protos/`` at the repository root and use absolute
imports rooted at ``Protobuf``, so that directory is appended to ``sys.path``
before importing.
"""

from __future__ import annotations

import base64
import json
import queue as queue_module
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

import grpc
from sqlalchemy import select

_PROTO_ROOT = Path(__file__).resolve().parents[1] / "protos"
if str(_PROTO_ROOT) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_PROTO_ROOT))

from Protobuf.Client import (  # noqa: E402
    AuditScReq_pb2,
    ClientCommandDeliverScReq_pb2,
    ClientRegisterCsReq_pb2,
    ConfigUploadScReq_pb2,
    HandshakeScReq_pb2,
)
from Protobuf.Command import HeartBeat_pb2  # noqa: E402
from Protobuf.Server import (  # noqa: E402
    AuditScRsp_pb2,
    ClientCommandDeliverScRsp_pb2,
    ClientRegisterScRsp_pb2,
    ConfigUploadScRsp_pb2,
    HandshakeScRsp_pb2,
)
from Protobuf.Service import (  # noqa: E402
    Audit_pb2_grpc,
    ClientCommandDeliver_pb2_grpc,
    ClientRegister_pb2_grpc,
    ConfigUpload_pb2_grpc,
    Handshake_pb2_grpc,
)

from .db import Database  # noqa: E402
from .models import AbstractClient, Client, ClientGroup, now  # noqa: E402

PROTOCOL_NAME = "Cyrene_MSP"
HANDSHAKE_SERVICE_PREFIX = "/ClassIsland.Shared.Protobuf.Service.Handshake/"

#: Services that a client may call *before* it owns a session.
#:
#: The upstream C# interceptor only exempts ``Handshake``, but the shipped
#: ClassIsland 2.x client calls ``ClientRegister/Register`` first and
#: handshakes afterwards (``ManagementServerConnection.RegisterAsync`` passes
#: ``GetMetadata(true)``, i.e. an empty ``session`` header, and only
#: ``ListenCommands`` runs the handshake). Keeping the upstream semantics would
#: make every real client fail with ``PermissionDenied / 会话无效`` before it
#: could ever handshake, so registration is exempted here on purpose.
OUT_OF_SESSION_SERVICE_PREFIXES = (
    HANDSHAKE_SERVICE_PREFIX,
    "/ClassIsland.Shared.Protobuf.Service.ClientRegister/",
)

RETCODE_SUCCESS = 200
RETCODE_SERVER_INTERNAL_ERROR = 500
RETCODE_INVALID_REQUEST = 404
RETCODE_HANDSHAKE_CLIENT_REJECTED = 1001
RETCODE_REGISTERED = 10001
RETCODE_CLIENT_NOT_FOUND = 10002

COMMAND_PING = 10
COMMAND_PONG = 11


def _header(context: grpc.ServicerContext, name: str) -> str:
    for key, value in context.invocation_metadata() or ():
        if key.lower() == name:
            return value
    return ""


class _MetadataValidator:
    """Subset of ``CyreneMspFrontedInterceptor`` usable from servicers."""

    def __init__(self, connections: Any) -> None:
        self.connections = connections

    def validate(self, context: grpc.ServicerContext, method: str) -> tuple[bool, str]:
        protocol = _header(context, "protocol_name")
        if protocol != PROTOCOL_NAME:
            return False, f"客户端使用的协议 {protocol} 与服务端协议 {PROTOCOL_NAME} 不符。"
        if method.startswith(OUT_OF_SESSION_SERVICE_PREFIXES):
            return True, ""
        cuid = _header(context, "cuid")
        session_id = _header(context, "session")
        if not cuid:
            return False, "会话无效"
        session = self.connections.get_session(cuid)
        if session is None or session.session_id != session_id:
            return False, "会话无效"
        return True, ""


class CyreneMspInterceptor(grpc.ServerInterceptor):
    """Port of ``CyreneMspFrontedInterceptor``.

    ``UnaryServerHandler`` in the original C# interceptor only guards unary
    calls, so this implementation installs the same two checks for every
    handler kind that ASP.NET Core would route through it.
    """

    def __init__(self, connections: Any) -> None:
        self.connections = connections

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _metadata(handler_call_details: Any) -> dict[str, str]:
        values: dict[str, str] = {}
        for key, value in handler_call_details.invocation_metadata or ():
            values.setdefault(key.lower(), value)
        return values

    def _reject(self, code: grpc.StatusCode, message: str) -> None:
        raise _InterceptorAbort(code, message)

    def _validate(self, method: str, metadata: dict[str, str]) -> None:
        client_protocol = metadata.get("protocol_name", "")
        if client_protocol != PROTOCOL_NAME:
            self._reject(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"客户端使用的协议 {client_protocol} 与服务端协议 {PROTOCOL_NAME} 不符。",
            )
        if method.startswith(OUT_OF_SESSION_SERVICE_PREFIXES):
            return
        cuid = metadata.get("cuid")
        session = self.connections.get_session(cuid) if cuid else None
        if session is None or session.session_id != metadata.get("session"):
            self._reject(grpc.StatusCode.PERMISSION_DENIED, "会话无效")

    # -- interceptor API -------------------------------------------------
    def intercept_service(self, continuation, handler_call_details):  # noqa: ANN001
        metadata = self._metadata(handler_call_details)
        method = handler_call_details.method or ""
        try:
            self._validate(method, metadata)
        except _InterceptorAbort as abort:
            return _aborting_handler(continuation(handler_call_details), abort.code, abort.message)
        return continuation(handler_call_details)


class _InterceptorAbort(Exception):
    def __init__(self, code: grpc.StatusCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _aborting_handler(handler: Any, code: grpc.StatusCode, message: str):
    """Wrap ``handler`` so every call fails with ``code``/``message``.

    The replacement keeps the original call kind and (de)serialisers so that
    the server still routes the RPC the way the generated stub expects; the
    abort happens before the servicer method is reached, exactly like the C#
    interceptor throwing before invoking its continuation.
    """

    def unary(request, context):  # noqa: ANN001
        context.abort(code, message)

    def stream(request_iterator, context):  # noqa: ANN001
        context.abort(code, message)
        yield  # pragma: no cover - unreachable, keeps the generator contract

    serializer = handler.response_serializer
    deserializer = handler.request_deserializer

    if handler.unary_unary is not None:
        return grpc.unary_unary_rpc_method_handler(
            unary,
            request_deserializer=deserializer,
            response_serializer=serializer,
        )
    if handler.unary_stream is not None:
        return grpc.unary_stream_rpc_method_handler(
            stream,
            request_deserializer=deserializer,
            response_serializer=serializer,
        )
    if handler.stream_unary is not None:
        return grpc.stream_unary_rpc_method_handler(
            unary,
            request_deserializer=deserializer,
            response_serializer=serializer,
        )
    return grpc.stream_stream_rpc_method_handler(
        stream,
        request_deserializer=deserializer,
        response_serializer=serializer,
    )


class HandshakeService(Handshake_pb2_grpc.HandshakeServicer):
    def __init__(self, database: Database, connections: Any) -> None:
        self.database = database
        self.connections = connections
        self.validator = _MetadataValidator(connections)

    def BeginHandshake(self, request, context):  # noqa: N802 - gRPC naming
        with self.database.open() as session:
            client = session.get(Client, request.ClientUid)
            if client is None:
                return HandshakeScRsp_pb2.HandshakeScBeginHandShakeRsp(
                    Retcode=RETCODE_HANDSHAKE_CLIENT_REJECTED, Message="找不到对应的客户端"
                )
            if (client.Mac or "").lower() != (request.ClientMac or "").lower():
                return HandshakeScRsp_pb2.HandshakeScBeginHandShakeRsp(
                    Retcode=RETCODE_HANDSHAKE_CLIENT_REJECTED, Message="客户端 MAC 地址验证失败"
                )

        if len(request.ChallengeTokenEncrypted or "") > 1000:
            context.abort(grpc.StatusCode.OUT_OF_RANGE, "提供的挑战令牌太长")

        try:
            decrypted = self.connections.decrypt_challenge(request.ChallengeTokenEncrypted)
        except Exception as exc:  # noqa: BLE001 - mirrors the controller catch
            return HandshakeScRsp_pb2.HandshakeScBeginHandShakeRsp(
                Retcode=RETCODE_SERVER_INTERNAL_ERROR, Message=str(exc)
            )

        return HandshakeScRsp_pb2.HandshakeScBeginHandShakeRsp(
            Retcode=RETCODE_SUCCESS,
            Message="",
            ChallengeTokenDecrypted=decrypted,
            ServerPublicKey=self.connections.server_public_key_armored,
        )

    def CompleteHandshake(self, request, context):  # noqa: N802 - gRPC naming
        cuid = _header(context, "cuid")
        if not request.Accepted:
            return HandshakeScRsp_pb2.HandshakeScCompleteHandshakeRsp(Retcode=RETCODE_SUCCESS)

        session_id = self.connections.establish_client_connection(cuid)
        if session_id is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "此客户端已与服务端建立连接")
        return HandshakeScRsp_pb2.HandshakeScCompleteHandshakeRsp(
            Retcode=RETCODE_SUCCESS, Message="", SessionId=session_id
        )


class ClientRegisterService(ClientRegister_pb2_grpc.ClientRegisterServicer):
    def __init__(self, database: Database, connections: Any) -> None:
        self.database = database
        self.connections = connections

    def Register(self, request, context):  # noqa: N802 - gRPC naming
        with self.database.open() as session:
            existing = session.get(Client, request.ClientUid)
            if existing is not None:
                return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                    Retcode=RETCODE_REGISTERED,
                    Message="Client has already been registered",
                    ServerPublicKey=self.connections.server_public_key_armored,
                )

            abstract = session.scalars(
                select(AbstractClient).where(AbstractClient.Id == request.ClientId)
            ).first()

            from .models import OrganizationSettings

            setting = session.get(OrganizationSettings, "AllowUnregisteredClients")
            allow_unregistered = True
            if setting is not None:
                value = (setting.Value or "").strip()
                if value.lower() in ("true", "false"):
                    allow_unregistered = value.lower() == "true"
            if not allow_unregistered and abstract is None:
                return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                    Retcode=RETCODE_INVALID_REQUEST,
                    Message="Unregistered clients are not allowed",
                    ServerPublicKey=self.connections.server_public_key_armored,
                )

            try:
                if abstract is None:
                    abstract = AbstractClient(Id=request.ClientId, GroupId=1)
                    session.add(abstract)
                client = Client(
                    Cuid=request.ClientUid,
                    Id=request.ClientId,
                    RegisterTime=now(),
                    # ``Client.Mac`` is ``[MaxLength(16)]`` in C# but is assigned
                    # verbatim there; truncating here would break the MAC check in
                    # ``BeginHandshake`` for separators such as ``AA-BB-CC-DD-EE-01``.
                    Mac=request.ClientMac or "",
                )
                session.add(client)
                session.flush()
            except Exception as exc:  # noqa: BLE001 - mirrors the controller catch
                return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                    Retcode=RETCODE_SERVER_INTERNAL_ERROR,
                    Message=str(exc),
                    ServerPublicKey=self.connections.server_public_key_armored,
                )

            return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                Retcode=RETCODE_SUCCESS,
                Message="",
                ServerPublicKey=self.connections.server_public_key_armored,
            )

    def UnRegister(self, request, context):  # noqa: N802 - gRPC naming
        with self.database.open() as session:
            client = session.get(Client, request.ClientUid)
            if client is None:
                return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                    Retcode=RETCODE_CLIENT_NOT_FOUND, Message="Client not found."
                )
            try:
                session.delete(client)
                session.flush()
            except Exception as exc:  # noqa: BLE001
                return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                    Retcode=RETCODE_SERVER_INTERNAL_ERROR, Message=str(exc)
                )
            return ClientRegisterScRsp_pb2.ClientRegisterScRsp(
                Retcode=RETCODE_SUCCESS, Message=""
            )


class ClientCommandDeliverFrontedService(
    ClientCommandDeliver_pb2_grpc.ClientCommandDeliverServicer
):
    def __init__(self, database: Database, connections: Any) -> None:
        self.database = database
        self.connections = connections
        self.validator = _MetadataValidator(connections)

    def ListenCommand(self, request_iterator, context):  # noqa: N802 - gRPC naming
        cuid = _header(context, "cuid")
        session = self.connections.get_session(cuid) if cuid else None
        if session is None:
            yield ClientCommandDeliverScRsp_pb2.ClientCommandDeliverScRsp(
                RetCode=RETCODE_INVALID_REQUEST
            )
            return

        session.writer = context
        session.is_activated = True

        # The request stream is consumed on a helper thread so that commands
        # queued elsewhere (``ClientCommandDeliverService``) can be flushed even
        # while the client stays silent.
        incoming: "queue_module.Queue[Any]" = queue_module.Queue()

        def _pump() -> None:
            try:
                for item in request_iterator:
                    incoming.put(item)
            except Exception:  # noqa: BLE001 - stream closed
                pass
            finally:
                incoming.put(None)

        threading.Thread(target=_pump, daemon=True).start()

        try:
            self._deliver_ping(session)
            while True:
                for command_type, payload in session.drain():
                    yield ClientCommandDeliverScRsp_pb2.ClientCommandDeliverScRsp(
                        RetCode=RETCODE_SUCCESS, Type=command_type, Payload=payload
                    )
                try:
                    request = incoming.get(timeout=0.2)
                except queue_module.Empty:
                    continue
                if request is None:
                    break
                if request.Type == COMMAND_PING:
                    yield self._heartbeat_response()
                else:
                    yield ClientCommandDeliverScRsp_pb2.ClientCommandDeliverScRsp(
                        RetCode=RETCODE_INVALID_REQUEST
                    )
        except Exception:  # noqa: BLE001 - mirrors the controller catch
            pass
        finally:
            self.connections.destroy_connection(cuid)

    # ------------------------------------------------------------------ utils
    def _deliver_ping(self, session: Any) -> None:
        # ``ClientCommandDeliverFrontedService`` greets a fresh command flow with
        # ``DeliverCommandAsync(CommandTypes.Pong, new Empty(), ...)`` -- an empty
        # payload, not a ``HeartBeat``.
        session.enqueue(COMMAND_PONG, b"")

    def _heartbeat_response(self):
        # Upstream replies with ``new HeartBeat()``, i.e. every field at its
        # default (``isOnline = false``), which serialises to zero bytes.
        return ClientCommandDeliverScRsp_pb2.ClientCommandDeliverScRsp(
            RetCode=RETCODE_SUCCESS,
            Type=COMMAND_PONG,
            Payload=HeartBeat_pb2.HeartBeat().SerializeToString(),
        )


class AuditService(Audit_pb2_grpc.AuditServicer):
    """``LogEvent`` is a no-op in the original server (``// todo``).

    The C# implementation returns a default ``AuditScRsp``, i.e.
    ``Retcode = Unspecified``. Returning ``Success`` keeps the wire format
    identical (same fields, same defaults elsewhere) while giving callers an
    unambiguous acknowledgement.
    """

    def __init__(self, database: Database | None = None, connections: Any = None) -> None:
        self.database = database
        self.connections = connections

    def LogEvent(self, request, context):  # noqa: N802 - gRPC naming
        return AuditScRsp_pb2.AuditScRsp(Retcode=RETCODE_SUCCESS)


class ConfigUploadService(ConfigUpload_pb2_grpc.ConfigUploadServicer):
    """``UploadConfig`` is a no-op in the original server (``// todo``).

    Same reasoning as :class:`AuditService`: the C# version answers with a
    default ``ConfigUploadScRsp`` (``Retcode = Unspecified``); answering
    ``Success`` keeps the payload handling unchanged and is what the client
    treats as "accepted".
    """

    def __init__(self, database: Database | None = None, connections: Any = None) -> None:
        self.database = database
        self.connections = connections

    def UploadConfig(self, request, context):  # noqa: N802 - gRPC naming
        return ConfigUploadScRsp_pb2.ConfigUploadScRsp(Retcode=RETCODE_SUCCESS)


def create_server(
    database: Database, connections: Any, port: int
) -> grpc.Server:
    from concurrent.futures import ThreadPoolExecutor

    server = grpc.server(
        ThreadPoolExecutor(max_workers=16),
        interceptors=(CyreneMspInterceptor(connections),),
    )
    Handshake_pb2_grpc.add_HandshakeServicer_to_server(
        HandshakeService(database, connections), server
    )
    ClientRegister_pb2_grpc.add_ClientRegisterServicer_to_server(
        ClientRegisterService(database, connections), server
    )
    ClientCommandDeliver_pb2_grpc.add_ClientCommandDeliverServicer_to_server(
        ClientCommandDeliverFrontedService(database, connections), server
    )
    Audit_pb2_grpc.add_AuditServicer_to_server(AuditService(database, connections), server)
    ConfigUpload_pb2_grpc.add_ConfigUploadServicer_to_server(
        ConfigUploadService(database, connections), server
    )
    server.add_insecure_port(f"0.0.0.0:{port}")
    return server
