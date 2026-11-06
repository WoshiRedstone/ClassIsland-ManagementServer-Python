#!/usr/bin/env sh
# Run the first-time setup wizard (writes data/appsettings.json).
# Equivalent to the reference implementation's setup.sh.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EXE="$ROOT/out/main.dist/ManagementServer.exe"
if [ ! -f "$EXE" ]; then
    echo "[ERROR] Executable not found: $EXE" >&2
    echo "        Build it first with build_exe.bat" >&2
    exit 1
fi
exec "$EXE" --setup=true
