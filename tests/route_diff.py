"""Compare the server's OpenAPI routes with the WebUI's apiDefinitions.ts.

Catches drift between the FastAPI routers and the frontend contract: a route the
frontend calls but the server does not expose would surface as a 404 in the UI.

Usage:
    python tests/route_diff.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "protos"))

API_DEFINITIONS = ROOT / "webui-src" / "src" / "api" / "apiDefinitions.ts"

# Each entry is `'name': ['METHOD', '/path']`, sometimes wrapped over two lines.
ENTRY_RE = re.compile(r"\[\s*'([A-Z]+)'\s*,\s*'([^']+)'\s*\]")


def _normalize(path: str) -> str:
    """Collapse path parameters so `/a/{id}` and `/a/${id}` compare equal."""
    path = re.sub(r"\$\{[^}]+\}", "{}", path)
    return re.sub(r"\{[^}]+\}", "{}", path)


def server_routes() -> set[tuple[str, str]]:
    from app.launcher import create_app

    spec = create_app().openapi()
    routes: set[tuple[str, str]] = set()
    for path, operations in spec["paths"].items():
        for method in operations:
            routes.add((method.upper(), _normalize(path)))
    return routes


def client_routes() -> set[tuple[str, str]]:
    source = API_DEFINITIONS.read_text(encoding="utf-8")
    # The file is generated as `'name': ['METHOD', '/path']` pairs.
    return {
        (method, _normalize(path))
        for method, path in ENTRY_RE.findall(source)
    }


def main() -> int:
    server = server_routes()
    client = client_routes()
    missing = sorted(client - server)

    print(f"server routes: {len(server)}")
    print(f"client routes: {len(client)}")

    if missing:
        print("\nMISSING FROM SERVER (the WebUI would get a 404):")
        for method, path in missing:
            print(f"  {method} {path}")
        return 1

    only_server = sorted(server - client)
    if only_server:
        print("\nonly on the server (gRPC-adjacent / not used by the UI):")
        for method, path in only_server:
            print(f"  {method} {path}")

    print("\nAll WebUI routes are served.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
