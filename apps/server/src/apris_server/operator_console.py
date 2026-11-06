"""Loopback-only operator console for the existing planar simulator port."""

import asyncio
import json
import secrets
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .runner_port_experiment import RunnerPort

ORIGIN = "http://127.0.0.1:8766"
STATIC = Path(__file__).with_name("operator_console")


def create_console(token: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        events = deque(maxlen=64)
        port = RunnerPort(events.append, backend="simulator")
        port.inhibited = True
        app.state.port, app.state.events = port, events
        await port.start()
        try:
            yield
        finally:
            await port.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request, call_next):
        if request.headers.get("host") != "127.0.0.1:8766":
            return JSONResponse({"detail": "loopback-host-required"}, status_code=403)
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {token}"
            ):
                return JSONResponse({"detail": "console-token-required"}, status_code=401)
            origin = request.headers.get("origin")
            if origin not in (None, ORIGIN):
                return JSONResponse({"detail": "same-origin-required"}, status_code=403)
            if request.method != "GET" and origin != ORIGIN:
                return JSONResponse({"detail": "same-origin-required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    async def body(request):
        data = bytearray()
        try:
            async with asyncio.timeout(2):
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise HTTPException(413, "frame-too-large")
            value = json.loads(data)
        except (ValueError, TimeoutError) as error:
            raise HTTPException(400, "invalid-json-body") from error
        if not isinstance(value, dict):
            raise HTTPException(400, "object-required")
        return value

    async def dispatch(request, message):
        try:
            return await request.app.state.port.request(message)
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/console")
    async def page():
        return FileResponse(STATIC / "index.html")

    @app.get("/console/{asset}")
    async def asset(asset: str):
        if asset not in {"console.js", "console.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / asset)

    @app.get("/api/state")
    async def state(request: Request):
        port = request.app.state.port
        async with port.lock:
            # Snapshot does not renew any lease; expiry also applies to read-only reconnects.
            import time

            port._expire(time.monotonic())
            snapshot = await port._dispatch({"action": "snapshot"})
            snapshot["control"] = port._control_reply(
                {"requestId": uuid.uuid4().hex, "kind": "snapshot"}
            )
            snapshot["interlock"] = port.runtime.motion_interlock.snapshot()
            snapshot["events"] = list(request.app.state.events)
            return snapshot

    @app.post("/api/control")
    async def control(request: Request):
        return await dispatch(request, {"action": "control", "message": await body(request)})

    @app.post("/api/motion")
    async def motion(request: Request):
        value = await body(request)
        return await dispatch(
            request, {"action": "motion", "session": value.get("connectionEpoch"), "message": value}
        )

    @app.post("/api/front")
    async def front(request: Request):
        value = await body(request)
        if set(value) != {"clear"} or type(value["clear"]) is not bool:
            raise HTTPException(400, "explicit-synthetic-front-required")
        return await dispatch(
            request, {"action": "fixture", "front": "CLEAR" if value["clear"] else "UNKNOWN"}
        )

    return app


def main():
    token = secrets.token_urlsafe(32)
    print(f"Operator console (simulator only): {ORIGIN}/console#{token}", flush=True)
    uvicorn.run(create_console(token), host="127.0.0.1", port=8766, access_log=False)


if __name__ == "__main__":
    main()
