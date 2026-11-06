#!/usr/bin/env sh
# Start the ManagementServer (WebUI on 7878, gRPC on 7879).
# Equivalent to the reference implementation's start.sh.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EXE="$ROOT/out/main.dist/ManagementServer.exe"
if [ ! -f "$EXE" ]; then
    echo "[ERROR] Executable not found: $EXE" >&2
    echo "        Build it first with build_exe.bat" >&2
    exit 1
fi
cd "$ROOT/out/main.dist" || exit 1
exec "$EXE" "$@"
