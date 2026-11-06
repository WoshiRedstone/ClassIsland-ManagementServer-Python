"""Process entry point.

Kept at the repository root so the Nuitka build has a single, obvious target::

    python -m nuitka --standalone --output-dir=build main.py

Running from source works the same way (``python main.py``); the launcher
resolves the repository root automatically in that case.
"""

from __future__ import annotations

import os
import sys
import traceback


def _log_startup_failure(exc: BaseException) -> str | None:
    """Write a traceback next to the application (windowed builds have no console)."""
    candidates: list[str] = []
    compiled = "__compiled__" in globals() or bool(getattr(sys, "frozen", False))
    if compiled:
        # The directory holding ManagementServer.exe.
        try:
            candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        except Exception:  # pragma: no cover - defensive
            pass
    else:
        # From source: the directory holding main.py.  ``sys.executable`` is the
        # interpreter (possibly inside a conda environment) and must never be
        # used, otherwise a stray ``data`` directory is created there.
        main_file = globals().get("__file__")
        if main_file:
            candidates.append(os.path.dirname(os.path.abspath(main_file)))
    candidates.append(os.getcwd())

    seen: set[str] = set()
    for base in candidates:
        if not base or base in seen:
            continue
        seen.add(base)
        for directory in (os.path.join(base, "data"), base):
            try:
                os.makedirs(directory, exist_ok=True)
                path = os.path.join(directory, "startup_error.log")
                with open(path, "a", encoding="utf-8") as fp:
                    fp.write("".join(traceback.format_exception(exc)))
                    fp.write("\n")
                return path
            except Exception:
                continue
    return None


def main() -> int:
    from app.launcher import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - top level guard
        from app.launcher import DatabaseUnavailable

        if isinstance(exc, DatabaseUnavailable):
            # A database problem is a configuration problem, not a crash:
            # print the actionable message without the SQLAlchemy internals.
            print("启动失败：数据库不可用。", file=sys.stderr)
            print(exc.describe(), file=sys.stderr)
        else:
            traceback.print_exc()
        path = _log_startup_failure(exc)
        if path:
            print(f"启动失败，详情见 {path}", file=sys.stderr)
        sys.exit(1)
