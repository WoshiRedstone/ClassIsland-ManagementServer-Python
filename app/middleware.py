"""Global request handling: sessions, authentication and ``Error`` payloads.

The original server answers *every* failure with ``{"message": "..."}`` (the
``Models.Error`` record) and the WebUI shows ``message`` verbatim in a toast, so
all HTTP errors are converted to that shape here.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .deps import error


class SessionMiddleware(BaseHTTPMiddleware):
    """Opens one SQLAlchemy session per request and commits on success."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        database = request.app.state.database
        session = database.session()
        request.state.session = session
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Anything reaching this point has already passed through
                # Starlette's ``ExceptionMiddleware``, so ``HTTPException`` and
                # request-validation errors were converted to responses
                # earlier. What is left are genuine handler failures such as a
                # database constraint violation. Letting them propagate would
                # reach ``ServerErrorMiddleware``, which writes a response and
                # then re-raises; that re-raise happens *after* the response
                # passed through this ``BaseHTTPMiddleware`` and corrupts the
                # surrounding anyio task group (the process would then log
                # ``TypeError: expected a function, exception type or tuple of
                # exception types`` instead of a useful error). Answering them
                # here keeps the failure contained and still gives the WebUI
                # the ``{"message": ...}`` shape it expects.
                session.rollback()
                return JSONResponse(status_code=500, content=error(str(exc)))
            if response.status_code < 400:
                try:
                    session.commit()
                except Exception as exc:
                    # Committing after the handler succeeded can still fail
                    # (foreign keys, unique constraints, ...). Same reasoning as
                    # above: never raise out of ``dispatch`` once a response
                    # exists.
                    session.rollback()
                    return JSONResponse(status_code=500, content=error(str(exc)))
            else:
                session.rollback()
            return response
        finally:
            session.close()


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "message" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        message = "" if detail is None else str(detail)
        if message == "unauthorized":
            message = "登录身份已失效，请重新登录!"
        elif message == "forbidden":
            message = "没有权限执行此操作。"
        return JSONResponse(
            status_code=exc.status_code,
            content=error(message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=error(str(exc)))
