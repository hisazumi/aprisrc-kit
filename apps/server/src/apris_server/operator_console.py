"""Loopback-only operator console for the existing planar simulator port."""

import argparse
import asyncio
import json
import secrets
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from .runner_port_experiment import RunnerPort
from .runtime_localization import demo_localization
from .service_process import ServiceProcess

ORIGIN = "http://127.0.0.1:8766"
STATIC = Path(__file__).with_name("operator_console")


def create_console(
    token: str, *, node: str | None = None, origin: str = ORIGIN, localization: bool = False
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        events = deque(maxlen=64)
        numbered = deque(maxlen=128)

        def emit(event):
            events.append(event)
            app.state.event_cursor += 1
            numbered.append({"cursor": app.state.event_cursor, "event": event})

        app.state.event_cursor = 0
        app.state.numbered = numbered
        app.state.service = None
        app.state.view_id = None
        port = RunnerPort(
            emit, backend="simulator", localization=demo_localization() if localization else None
        )
        # Browser connection liveness has a different budget from runner/motion safety.
        port.operator_lease_s = 3.0
        port.inhibited = True
        app.state.port, app.state.events = port, events
        app.state.process = ServiceProcess(
            port, token, lambda: app.state.service, node=node, origin=origin
        )
        await port.start()
        try:
            yield
        finally:
            await port.close()
            await app.state.process.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request, call_next):
        if request.headers.get("host") != origin.removeprefix("http://"):
            return JSONResponse({"detail": "loopback-host-required"}, status_code=403)
        if request.url.path.startswith("/api/"):
            if not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {token}"
            ):
                return JSONResponse({"detail": "console-token-required"}, status_code=401)
            request_origin = request.headers.get("origin")
            if request_origin not in (None, origin):
                return JSONResponse({"detail": "same-origin-required"}, status_code=403)
            if request.method != "GET" and request_origin != origin:
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

    @app.get("/app")
    async def service_page():
        return FileResponse(STATIC / "service.html")

    @app.get("/console")
    async def page():
        return FileResponse(STATIC / "index.html")

    @app.get("/console/{asset}")
    async def asset(asset: str):
        if asset not in {"console.js", "console.css", "service.js"}:
            raise HTTPException(404)
        return FileResponse(STATIC / asset)

    @app.get("/api/state")
    async def state(request: Request):
        port = request.app.state.port
        async with port.lock:
            # Snapshot does not renew any lease; expiry also applies to read-only reconnects.
            port._expire(time.monotonic())
            snapshot = await port._dispatch({"action": "snapshot"})
            snapshot["control"] = port._control_reply(
                {"requestId": uuid.uuid4().hex, "kind": "snapshot"}
            )
            snapshot["interlock"] = port.runtime.motion_interlock.snapshot()
            snapshot["events"] = list(request.app.state.events)
            snapshot["serviceProcess"] = request.app.state.process.snapshot()
            service = request.app.state.service
            snapshot["serviceRunEpoch"] = service["runEpoch"] if service else None
            snapshot["serviceResult"] = service["result"] if service else None
            snapshot["operatorLeaseMs"] = round(port.operator_lease_s * 1000)
            snapshot["eventCursor"] = request.app.state.event_cursor
            snapshot["eventLog"] = list(request.app.state.numbered)
            snapshot["serviceAttached"] = bool(
                request.app.state.service and request.app.state.service["runEpoch"] == port.session
            )
            return snapshot

    @app.post("/api/control")
    async def control(request: Request):
        value = await body(request)
        manager = request.app.state.process
        if value.get("kind") == "openRun" and manager.active:
            raise HTTPException(409, "service-process-busy")
        result = await dispatch(request, {"action": "control", "message": value})
        if value.get("kind") == "globalStop":
            manager.request_stop()
        return result

    @app.post("/api/localization/initialize")
    async def initialize_localization(request: Request):
        value = await body(request)
        if "action" in value:
            raise HTTPException(400, "invalid-localization-request")
        if request.app.state.process.active:
            raise HTTPException(409, "service-process-busy")
        return await dispatch(request, {**value, "action": "localize"})

    @app.post("/api/localization/observation")
    async def localization_observation(request: Request):
        # Fixed simulator input path; no physical camera calibration is claimed.
        return await dispatch(
            request, {"action": "localizationObservation", "observation": await body(request)}
        )

    @app.post("/api/route/start")
    async def route_start(request: Request):
        if request.app.state.process.active:
            raise HTTPException(409, "service-process-busy")
        return await dispatch(request, {"action": "routeStart", "message": await body(request)})

    @app.post("/api/route/cancel")
    async def route_cancel(request: Request):
        return await dispatch(request, {"action": "routeCancel", "message": await body(request)})

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

    @app.post("/api/service/launch")
    async def launch(request: Request):
        value = await body(request)
        port = request.app.state.port
        async with port.lock:
            port._expire(time.monotonic())
            if (
                value != {"controlEpoch": port.control_epoch, "operatorId": port.operator_id}
                or not port.operator_id
            ):
                raise HTTPException(409, "stale-operator")
            if port.session or port.guard or port.inhibited or port.operation or port.io_tasks:
                raise HTTPException(409, "recover-or-clear-guard-before-start")
            try:
                return request.app.state.process.launch()
            except ValueError as error:
                raise HTTPException(409, str(error)) from error

    @app.post("/api/service/stop")
    async def stop_service(request: Request):
        value = await body(request)
        port = request.app.state.port
        manager = request.app.state.process
        async with port.lock:
            if not manager.job or value != {
                "controlEpoch": port.control_epoch,
                "launchId": manager.job["id"],
            }:
                raise HTTPException(409, "stale-launch")
            if manager.active:
                port.inhibited = True
                if port.session == manager.job["runEpoch"]:
                    port._revoke("operator-service-stop")
                manager.request_stop()
            return manager.snapshot()

    @app.post("/api/service/start")
    async def service_start(request: Request):
        value = await body(request)
        port = request.app.state.port
        async with port.lock:
            port._expire(time.monotonic())
            expected = {"controlEpoch": port.control_epoch, "operatorId": port.operator_id}
            manager = request.app.state.process
            if manager.active:
                expected["launchId"] = manager.job["id"]
                if manager.job["stop"].is_set() or manager.job["operatorId"] != port.operator_id:
                    raise HTTPException(409, "launch-stopped")
            if value != expected:
                raise HTTPException(409, "stale-operator-or-launch")
            if port.session or not port.operator_id:
                raise HTTPException(409, "service-busy-or-no-operator")
            run_id = uuid.uuid4().hex
            try:
                opened = await port._control(
                    dict(
                        protocolVersion=1,
                        connectionEpoch=port.control_epoch,
                        requestId=uuid.uuid4().hex,
                        robotId="fake-only",
                        kind="openRun",
                        operatorId=port.operator_id,
                        runId=run_id,
                    )
                )
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
            if manager.active:
                manager.job["runEpoch"] = opened["runEpoch"]
                manager.job["status"] = "running"
            request.app.state.service = dict(
                runId=run_id,
                runEpoch=opened["runEpoch"],
                prompt=None,
                answered=None,
                used=[],
                messages=[],
                result=None,
            )
            return dict(
                controlEpoch=port.control_epoch,
                operatorId=port.operator_id,
                runId=run_id,
                runEpoch=opened["runEpoch"],
            )

    def live_service(request):
        service = request.app.state.service
        port = request.app.state.port
        port._expire(time.monotonic())
        if not service or service["runEpoch"] != port.session:
            raise HTTPException(409, "service-ended")
        return service

    @app.post("/api/service/route/start")
    async def service_route_start(request: Request):
        value = await body(request)
        port = request.app.state.port
        async with port.lock:
            service = live_service(request)
            if (value.get("runEpoch") != service["runEpoch"]
                    or value.get("runId") != service["runId"]):
                raise HTTPException(409, "stale-run")
            try:
                return await port._dispatch({"action": "routeStart", "message": value})
            except (ValueError, KeyError, TypeError) as error:
                raise HTTPException(409, str(error)) from error

    @app.post("/api/service/prompt")
    async def publish_prompt(request: Request):
        value = await body(request)
        async with request.app.state.port.lock:
            service = live_service(request)
            prompt = value.get("prompt")
            if value.get("runEpoch") != service["runEpoch"] or not isinstance(prompt, dict):
                raise HTTPException(409, "stale-run")
            if (
                set(prompt) != {"id", "message", "choices", "stationary"}
                or not isinstance(prompt["id"], str)
                or not 1 <= len(prompt["id"]) <= 128
                or not isinstance(prompt["message"], str)
                or len(prompt["message"]) > 4096
                or type(prompt["stationary"]) is not bool
                or not isinstance(prompt["choices"], list)
                or not 1 <= len(prompt["choices"]) <= 16
                or any(not isinstance(c, str) or not 1 <= len(c) <= 256 for c in prompt["choices"])
                or len(set(prompt["choices"])) != len(prompt["choices"])
            ):
                raise HTTPException(400, "invalid-question")
            if service["prompt"] or prompt["id"] in service["used"] or len(service["used"]) >= 128:
                raise HTTPException(409, "question-busy-or-reused")
            service["prompt"] = prompt
            service["answered"] = None
            service["used"].append(prompt["id"])
            return {"ok": True}

    @app.post("/api/service/view")
    async def attach_view(request: Request):
        if await body(request) != {}:
            raise HTTPException(400, "empty-view-request-required")
        # A new page invalidates old page answers without changing run or operator leases.
        request.app.state.view_id = uuid.uuid4().hex
        return {"viewId": request.app.state.view_id}

    @app.get("/api/service/state")
    async def service_state(request: Request):
        async with request.app.state.port.lock:
            service = request.app.state.service
            request.app.state.port._expire(time.monotonic())
            live = bool(service and service["runEpoch"] == request.app.state.port.session)
            return dict(
                live=live,
                runEpoch=service["runEpoch"] if live else None,
                prompt=service["prompt"] if live else None,
                answered=service["answered"] if live else None,
                guardId=request.app.state.port.guard_id,
                messages=service["messages"] if service else [],
                result=(
                    service["result"]
                    or (
                        None
                        if live
                        else {"status": "interrupted", "reason": "run-ended-without-completion"}
                    )
                )
                if service
                else None,
            )

    @app.post("/api/service/answer")
    async def answer(request: Request):
        value = await body(request)
        async with request.app.state.port.lock:
            service = live_service(request)
            prompt = service["prompt"]
            if (
                set(value) != {"viewId", "runEpoch", "questionId", "value"}
                or not request.app.state.view_id
                or value["viewId"] != request.app.state.view_id
                or value["runEpoch"] != service["runEpoch"]
                or not prompt
                or value["questionId"] != prompt["id"]
                or service["answered"] is not None
                or value["value"] not in prompt["choices"]
            ):
                raise HTTPException(409, "stale-or-invalid-answer")
            service["answered"] = {"questionId": prompt["id"], "value": value["value"]}
            return {"ok": True}

    @app.post("/api/service/consume")
    async def consume(request: Request):
        value = await body(request)
        async with request.app.state.port.lock:
            service = live_service(request)
            prompt = service["prompt"]
            if (
                value.get("runEpoch") != service["runEpoch"]
                or not prompt
                or value.get("questionId") != prompt["id"]
                or service["answered"] is None
                or (prompt["stationary"] and request.app.state.port.guard_id is not None)
            ):
                raise HTTPException(409, "question-not-ready")
            result = service["answered"]
            service["prompt"] = service["answered"] = None
            return result

    @app.post("/api/service/say")
    async def say(request: Request):
        value = await body(request)
        async with request.app.state.port.lock:
            service = live_service(request)
            if (
                value.get("runEpoch") != service["runEpoch"]
                or not isinstance(value.get("message"), str)
                or len(value["message"]) > 4096
                or len(service["messages"]) >= 128
            ):
                raise HTTPException(409, "invalid-message-or-capacity")
            service["messages"].append(value["message"])
            return {"ok": True}

    @app.post("/api/service/finish")
    async def finish(request: Request):
        value = await body(request)
        async with request.app.state.port.lock:
            service = request.app.state.service
            if (
                not service
                or set(value) != {"runEpoch", "status", "reason"}
                or value["runEpoch"] != service["runEpoch"]
                or value["status"] not in {"completed", "failed", "interrupted"}
                or not isinstance(value["reason"], str)
                or len(value["reason"]) > 512
            ):
                raise HTTPException(409, "stale-or-invalid-result")
            port = request.app.state.port
            if port.session == service["runEpoch"]:
                raise HTTPException(409, "run-still-active")
            result = {"status": value["status"], "reason": value["reason"]}
            if service["result"] is not None and service["result"] != result:
                raise HTTPException(409, "result-already-recorded")
            service["result"] = result
            service["prompt"] = service["answered"] = None
            return {"ok": True}

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--localization", action="store_true", help="enable map quality gate (simulator only)"
    )
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    print(f"Operator console (simulator only): {ORIGIN}/console#{token}", flush=True)
    print(f"Service page: {ORIGIN}/app#{token}", flush=True)
    uvicorn.run(
        create_console(token, localization=args.localization),
        host="127.0.0.1",
        port=8766,
        access_log=False,
    )


if __name__ == "__main__":
    main()
