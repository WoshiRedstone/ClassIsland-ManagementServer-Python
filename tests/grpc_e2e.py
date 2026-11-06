"""End-to-end gRPC coverage against the running server (127.0.0.1:7879)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protos"))

from Protobuf.Client import (  # noqa: E402
    AuditScReq_pb2,
    ClientRegisterCsReq_pb2,
    ConfigUploadScReq_pb2,
    HandshakeScReq_pb2,
)
from Protobuf.Service import (  # noqa: E402
    Audit_pb2_grpc,
    ClientCommandDeliver_pb2_grpc,
    ClientRegister_pb2_grpc,
    ConfigUpload_pb2_grpc,
    Handshake_pb2_grpc,
)

TARGET = "127.0.0.1:7879"
PROTOCOL = ("protocol_name", "Cyrene_MSP")
FAILURES: list[str] = []


def check(label, actual, wanted):
    ok = actual == wanted
    print(("  ok  " if ok else "  FAIL"), f"{label}: {actual} (want {wanted})")
    if not ok:
        FAILURES.append(f"{label}: got {actual}, want {wanted}")


def main() -> int:
    cuid = str(uuid.uuid4())
    device_id = f"py-test-{uuid.uuid4().hex[:8]}"

    with grpc.insecure_channel(TARGET) as channel:
        register = ClientRegister_pb2_grpc.ClientRegisterStub(channel)
        handshake = Handshake_pb2_grpc.HandshakeStub(channel)

        # Without the protocol header the interceptor rejects every call.
        try:
            register.Register(
                ClientRegisterCsReq_pb2.ClientRegisterCsReq(
                    ClientUid=cuid, ClientId=device_id, ClientMac="AA-BB"
                )
            )
            FAILURES.append("Register without protocol header should fail")
            print("  FAIL register without protocol header: accepted")
        except grpc.RpcError as exc:
            check("register without protocol header", exc.code(), grpc.StatusCode.INVALID_ARGUMENT)

        # Documented deviation from upstream: ClientRegister is exempt from the
        # session check because the real 2.x client registers *before* it has a
        # session (ManagementServerConnection.RegisterAsync -> GetMetadata(true)).
        early = register.Register(
            ClientRegisterCsReq_pb2.ClientRegisterCsReq(
                ClientUid=cuid, ClientId=device_id, ClientMac="AA-BB"
            ),
            metadata=[PROTOCOL],
        )
        check("register before session", early.Retcode, 200)
        check("register returns public key", bool(early.ServerPublicKey), True)

        # Establish the session first, exactly like the client does.
        session_rsp = handshake.CompleteHandshake(
            HandshakeScReq_pb2.HandshakeScCompleteHandshakeReq(Accepted=True),
            metadata=[PROTOCOL, ("cuid", cuid)],
        )
        check("complete handshake", session_rsp.Retcode, 200)
        check("complete handshake returns session", bool(session_rsp.SessionId), True)
        session_md = [PROTOCOL, ("cuid", cuid), ("session", session_rsp.SessionId)]

        # Other services still require a valid session.
        try:
            Audit_pb2_grpc.AuditStub(channel).LogEvent(
                AuditScReq_pb2.AuditScReq(TimestampUtc=1), metadata=[PROTOCOL]
            )
            FAILURES.append("Audit without a session should fail")
            print("  FAIL audit without session: accepted")
        except grpc.RpcError as exc:
            check("audit without session", exc.code(), grpc.StatusCode.PERMISSION_DENIED)

        response = register.Register(
            ClientRegisterCsReq_pb2.ClientRegisterCsReq(
                ClientUid=cuid, ClientId=device_id, ClientMac="AA-BB"
            ),
            metadata=session_md,
        )
        check("register twice with session", response.Retcode, 10001)

        rejected = handshake.BeginHandshake(
            HandshakeScReq_pb2.HandshakeScBeginHandShakeReq(
                ClientUid=str(uuid.uuid4()), ClientMac="AA-BB",
                ChallengeTokenEncrypted="x", RequestedServerKeyId=0,
            ),
            metadata=[PROTOCOL],
        )
        check("handshake unknown client", rejected.Retcode, 1001)

        bad_mac = handshake.BeginHandshake(
            HandshakeScReq_pb2.HandshakeScBeginHandShakeReq(
                ClientUid=cuid, ClientMac="ZZ-ZZ",
                ChallengeTokenEncrypted="x", RequestedServerKeyId=0,
            ),
            metadata=[PROTOCOL],
        )
        check("handshake wrong mac", bad_mac.Retcode, 1001)

        # Documented deviation from upstream: the C# stubs return a default
        # response (Retcode=Unspecified) from a `// todo` body; answering Success
        # is friendlier to clients and keeps the interceptor contract intact.
        audit = Audit_pb2_grpc.AuditStub(channel)
        audit_response = audit.LogEvent(
            AuditScReq_pb2.AuditScReq(TimestampUtc=1), metadata=session_md
        )
        check("audit LogEvent retcode", audit_response.Retcode, 200)

        upload_response = ConfigUpload_pb2_grpc.ConfigUploadStub(channel).UploadConfig(
            ConfigUploadScReq_pb2.ConfigUploadScReq(), metadata=session_md
        )
        check("config upload retcode", upload_response.Retcode, 200)

        unregister = register.UnRegister(
            ClientRegisterCsReq_pb2.ClientRegisterCsReq(ClientUid=cuid),
            metadata=session_md,
        )
        check("unregister", unregister.Retcode, 200)
        missing = register.UnRegister(
            ClientRegisterCsReq_pb2.ClientRegisterCsReq(ClientUid=cuid),
            metadata=session_md,
        )
        check("unregister missing", missing.Retcode, 10002)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL GRPC CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
