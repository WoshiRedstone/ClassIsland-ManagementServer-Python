"""Copy the server PGP public key into the real client's management folder.

A real ClassIsland client only writes `ServerKey.asc` after it completes a
registration through its own UI flow. When a client is registered by the test
harness instead, the file is missing and `ListenCommand` fails with
`FileNotFoundException`. This helper closes that gap.

Usage:
    python tests/export_server_key.py [--db <path to management.db>]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "out" / "main.dist" / "data" / "management.db"
DEFAULT_OUT = pathlib.Path(os.environ["LOCALAPPDATA"]) / "ClassIsland" / "Management" / "ServerKey.asc"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    if not pathlib.Path(args.db).exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 1

    with sqlite3.connect(args.db) as db:
        row = db.execute(
            "select Value from organization_settings where Key = 'CyreneMspPublicKey'"
        ).fetchone()
    if not row:
        print("CyreneMspPublicKey is not seeded in this database", file=sys.stderr)
        return 1

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(row[0], encoding="utf-8")
    print(f"{out} ({len(row[0])} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
