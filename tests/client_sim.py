"""Simulate a real ClassIsland client end to end (REST + gRPC).

Flow: client_configure -> BeginHandshake (PGP) -> CompleteHandshake ->
Register -> ListenCommand (stream) -> receive a notification pushed from REST.
Then exercise manifest version bumping and object delivery.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import grpc
import warnings

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "protos"))

import pgpy  # noqa: E402
from google.protobuf.empty_pb2 import Empty  # noqa: E402
from Protobuf.Client import (  # noqa: E402
    ClientCommandDeliverScReq_pb2,
    ClientRegisterCsReq_pb2,
    HandshakeScReq_pb2,
)
from Protobuf.Command import HeartBeat_pb2, SendNotification_pb2  # noqa: E402
from Protobuf.Service import (  # noqa: E402
    ClientCommandDeliver_pb2_grpc,
    ClientRegister_pb2_grpc,
    Handshake_pb2_grpc,
)

BASE = "http://127.0.0.1:7878"
GRPC = "127.0.0.1:7879"
PROTOCOL = ("protocol_name", "Cyrene_MSP")
FAILURES: list[str] = []


def check(label, actual, wanted):
    ok = actual == wanted
    print(("  ok  " if ok else "  FAIL"), f"{label}: {actual} (want {wanted})")
    if not ok:
        FAILURES.append(f"{label}: got {actual}, want {wanted}")


def rest_login(client: httpx.Client) -> None:
    response = client.post(
        f"{BASE}/api/v1/auth/login", json={"username": "root", "password": "root"}
    )
    response.raise_for_status()
    token = response.json()["accessToken"]
    client.headers["Authorization"] = f"Bearer {token}"


def main() -> int:
    api = httpx.Client(timeout=20.0, follow_redirects=False)
    rest_login(api)

    cuid = str(uuid.uuid4())
    mac = "AA-BB-CC-DD-EE-01"
    device_id = f"sim-{uuid.uuid4().hex[:8]}"

    # 1. the preset a client downloads to learn where the server lives
    preset = api.get(f"{BASE}/api/v1/clients_registry/client_configure")
    check("client_configure status", preset.status_code, 200)
    check(
        "client_configure filename",
        "ManagementPreset.json" in preset.headers.get("content-disposition", ""),
        True,
    )
    preset_json = preset.json()
    # 客户端用 ConfigureFileHelper.LoadConfig<ManagementSettings> 读取这个文件，
    # 该辅助类使用默认 JsonSerializerOptions（大小写敏感），所以键必须是 PascalCase。
    check("preset server kind", preset_json.get("ManagementServerKind"), 1)
    check("preset grpc url non-empty", bool(preset_json.get("ManagementServerGrpc")), True)
    check("preset pascal case keys", preset_json.get("isManagementEnabled"), None)

    with grpc.insecure_channel(GRPC) as channel:
        handshake = Handshake_pb2_grpc.HandshakeStub(channel)
        register = ClientRegister_pb2_grpc.ClientRegisterStub(channel)
        deliver = ClientCommandDeliver_pb2_grpc.ClientCommandDeliverStub(channel)

        # 2. handshake: the client encrypts a challenge with the server pubkey
        probe = handshake.BeginHandshake(
            HandshakeScReq_pb2.HandshakeScBeginHandShakeReq(
                ClientUid=cuid,
                ClientMac=mac,
                ChallengeTokenEncrypted="x",
                RequestedServerKeyId=0,
            ),
            metadata=[PROTOCOL],
        )
        # unknown client -> rejected, but the server key is only returned on success
        check("handshake before register", probe.Retcode, 1001)

        # register first (C# allows this because AllowUnregisteredClients defaults true)
        session_rsp = handshake.CompleteHandshake(
            HandshakeScReq_pb2.HandshakeScCompleteHandshakeReq(Accepted=True),
            metadata=[PROTOCOL, ("cuid", cuid)],
        )
        check("complete handshake", session_rsp.Retcode, 200)
        session_md = [PROTOCOL, ("cuid", cuid), ("session", session_rsp.SessionId)]

        registered = register.Register(
            ClientRegisterCsReq_pb2.ClientRegisterCsReq(
                ClientUid=cuid, ClientId=device_id, ClientMac=mac
            ),
            metadata=session_md,
        )
        check("register", registered.Retcode, 200)
        server_pubkey = registered.ServerPublicKey
        check("server public key returned", server_pubkey.startswith("-----BEGIN PGP PUBLIC KEY"), True)

        # 3. now the full handshake can complete with a real PGP challenge
        key, _ = pgpy.PGPKey.from_blob(server_pubkey)
        challenge = f"challenge-{uuid.uuid4().hex}"
        encrypted = str(key.encrypt(pgpy.PGPMessage.new(challenge)))

        begun = handshake.BeginHandshake(
            HandshakeScReq_pb2.HandshakeScBeginHandShakeReq(
                ClientUid=cuid,
                ClientMac=mac,
                ChallengeTokenEncrypted=encrypted,
                RequestedServerKeyId=0,
            ),
            metadata=[PROTOCOL],
        )
        check("begin handshake retcode", begun.Retcode, 200)
        check("challenge decrypted", begun.ChallengeTokenDecrypted, challenge)

        # a wrong MAC must be rejected
        wrong = handshake.BeginHandshake(
            HandshakeScReq_pb2.HandshakeScBeginHandShakeReq(
                ClientUid=cuid,
                ClientMac="FF-FF",
                ChallengeTokenEncrypted=encrypted,
                RequestedServerKeyId=0,
            ),
            metadata=[PROTOCOL],
        )
        check("handshake wrong mac", wrong.Retcode, 1001)

        # 4. open the command stream and make sure the server pushes a Pong first
        incoming: "queue.Queue" = queue.Queue()
        outbound: "queue.Queue" = queue.Queue()

        def request_stream():
            """Live request stream: blocks until the test pushes a message."""
            while True:
                item = outbound.get()
                if item is None:
                    return
                yield item

        def consume():
            try:
                for message in deliver.ListenCommand(request_stream(), metadata=session_md):
                    incoming.put(message)
            except Exception as exc:  # noqa: BLE001
                incoming.put(exc)

        worker = threading.Thread(target=consume, daemon=True)
        worker.start()

        first = incoming.get(timeout=10)
        check("first pushed command type", first.Type, 11)  # Pong
        check("first pushed command retcode", first.RetCode, 200)

        # a client Ping is answered with a Pong
        outbound.put(
            ClientCommandDeliverScReq_pb2.ClientCommandDeliverScReq(
                Type=10, Payload=HeartBeat_pb2.HeartBeat(isOnline=True).SerializeToString()
            )
        )
        pong = incoming.get(timeout=10)
        check("ping answered with pong", pong.Type, 11)
        check("ping answer retcode", pong.RetCode, 200)

        # 5. push a notification from REST to the live client
        notification = {
            "targets": [
                {"assigneeType": 1, "targetClientCuid": cuid, "objectType": 0}
            ],
            "type": 102,
            "payload": {
                "messageMask": "通知",
                "messageContent": "服务器推送测试",
                "durationSeconds": 5.0,
                "repeatCounts": 1,
                "isTopmost": True,
            },
        }
        pushed = api.post(f"{BASE}/api/v1/client-commands/show-notification", json=notification)
        check("show-notification status", pushed.status_code, 200)

        received = incoming.get(timeout=10)
        check("pushed command type", received.Type, 102)  # SendNotification
        decoded = SendNotification_pb2.SendNotification()
        decoded.ParseFromString(received.Payload)
        check("pushed notification text", decoded.MessageContent, "服务器推送测试")
        check("pushed notification mask", decoded.MessageMask, "通知")
        check("pushed notification topmost", decoded.IsTopmost, True)

        # 6. restart-app goes to the same live stream
        restart = api.post(
            f"{BASE}/api/v1/client-commands/restart-app",
            json={"targets": [{"assigneeType": 1, "targetClientCuid": cuid, "objectType": 0}], "type": 101},
        )
        check("restart-app status", restart.status_code, 200)
        restart_cmd = incoming.get(timeout=10)
        check("restart command type", restart_cmd.Type, 101)

    # 7. manifest + delivery, anonymous, straight after registration
    manifest = api.get(f"{BASE}/api/v1/client/{cuid}/manifest")
    check("manifest status", manifest.status_code, 200)
    body = manifest.json()
    check("manifest server kind", body.get("serverKind"), 1)
    check(
        "manifest subject source template",
        body["subjectsSource"]["value"],
        "{host}/api/v1/client/{cuid}/subjects",
    )

    # Uploading a profile bumps the version of every object whose assignees
    # include this client (``NotifyObjectUpdatingAsync`` only records updates
    # for clients that already have an assignee for the object), so the
    # assignee has to exist before the upload.
    subject_id = str(uuid.uuid4())
    assignee = api.post(
        f"{BASE}/api/v1/assignees/all",
        json={
            "objectId": subject_id,
            "objectType": 3,
            "targetClientCuid": cuid,
            "assigneeType": 1,
        },
    )
    check("assignee create status", assignee.status_code, 200)

    before = body["subjectsSource"]["version"]
    upload = api.post(
        f"{BASE}/api/v1/profiles/upload?replace=true",
        json={
            "subjects": {
                subject_id: {
                    "name": "数学",
                    "initial": "数",
                    "isOutDoor": False,
                    "teacherName": "",
                }
            },
            "timeLayouts": {},
            "classPlans": {},
        },
    )
    check("profile upload status", upload.status_code, 200)

    after_manifest = api.get(f"{BASE}/api/v1/client/{cuid}/manifest").json()
    check("subjects version bumped", after_manifest["subjectsSource"]["version"] > before, True)

    # the update is consumed by the manifest, so a second read is stable
    stable = api.get(f"{BASE}/api/v1/client/{cuid}/manifest").json()
    check(
        "manifest version stable after consumption",
        stable["subjectsSource"]["version"],
        after_manifest["subjectsSource"]["version"],
    )

    subjects = api.get(f"{BASE}/api/v1/client/{cuid}/subjects")
    check("subjects delivery status", subjects.status_code, 200)
    check("subjects delivery is a profile", "classPlanGroups" in subjects.json(), True)

    delivered = api.get(f"{BASE}/api/v1/client/{cuid}/subjects").json()
    check("delivered subject present", subject_id in delivered["subjects"], True)
    check(
        "delivered subject name",
        delivered["subjects"][subject_id]["name"],
        "数学",
    )

    # policy falls back to the empty policy when nothing is assigned
    policy = api.get(f"{BASE}/api/v1/client/{cuid}/policy")
    check("policy status", policy.status_code, 200)
    check("policy default allow exit", policy.json().get("allowExitManagement"), True)

    # unknown client is a 404 with the standard error shape
    missing = api.get(f"{BASE}/api/v1/client/{uuid.uuid4()}/manifest")
    check("manifest unknown client", missing.status_code, 404)
    check("manifest unknown message", missing.json().get("message"), "找不到请求的对象")

    # teardown
    for row in api.get(f"{BASE}/api/v1/assignees/by-object/assignees/3/{subject_id}").json()["items"]:
        api.delete(f"{BASE}/api/v1/assignees/all/{row['id']}")
    api.delete(f"{BASE}/api/v1/profiles/subjects/{subject_id}")
    api.delete(f"{BASE}/api/v1/clients_registry/unregister?Cuid={cuid}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL CLIENT SIMULATION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
