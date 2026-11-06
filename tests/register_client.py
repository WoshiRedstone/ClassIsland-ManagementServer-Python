"""Register a client over gRPC so REST delivery endpoints have something to serve.

The management server only serves `/api/v1/client/{cuid}/...` for clients that
registered through the gRPC `ClientRegister` service, so every test that reads
those endpoints first has to make sure the client exists. This helper does that
and is safe to call repeatedly (an already registered client simply answers
`Retcode.Registered`).

Usage:
    python tests/register_client.py [--cuid <guid>] [--id <device-id>] [--mac <mac>]

Prints the cuid on stdout so shell callers can capture it.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import grpc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protos"))

from Protobuf.Client import ClientRegisterCsReq_pb2  # noqa: E402
from Protobuf.Service import ClientRegister_pb2_grpc  # noqa: E402

RETCODE_SUCCESS = 200
RETCODE_REGISTERED = 10001

DEFAULT_CUID = "99999999-8888-7777-6666-555555555555"
DEFAULT_CLIENT_ID = "contract-test-client"
DEFAULT_MAC = "AA:BB:CC:DD:EE:FF"


def normalize_target(target: str) -> str:
    """Accept both `host:port` and `http://host:port`; gRPC wants the bare form."""
    for prefix in ("http://", "https://"):
        if target.startswith(prefix):
            return target[len(prefix):].rstrip("/")
    return target.rstrip("/")


def register(target: str, cuid: str, client_id: str, mac: str) -> int:
    metadata = [
        ("protocol_name", "Cyrene_MSP"),
        ("protocol_version", "2.0.0.0"),
        ("cuid", cuid),
        ("session", ""),
    ]
    request = ClientRegisterCsReq_pb2.ClientRegisterCsReq(
        ClientUid=cuid, ClientId=client_id, ClientMac=mac
    )
    with grpc.insecure_channel(normalize_target(target)) as channel:
        stub = ClientRegister_pb2_grpc.ClientRegisterStub(channel)
        response = stub.Register(request, metadata=metadata, timeout=30)
    if response.Retcode not in (RETCODE_SUCCESS, RETCODE_REGISTERED):
        print(
            f"register failed: Retcode={response.Retcode} {response.Message}",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grpc", default="127.0.0.1:7879")
    parser.add_argument("--cuid", default=DEFAULT_CUID)
    parser.add_argument("--id", dest="client_id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--mac", default=DEFAULT_MAC)
    args = parser.parse_args(argv)

    cuid = args.cuid
    if cuid == "random":
        cuid = str(uuid.uuid4())

    code = register(args.grpc, cuid, args.client_id, args.mac)
    if code == 0:
        print(cuid)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
