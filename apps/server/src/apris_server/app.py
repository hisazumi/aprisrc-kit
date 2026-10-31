from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .assistant import AssistantCommandRequest, AssistantIntentInterpreter
from .config import AppConfig
from .factory_http_adapter import FactoryHttpRoverAdapter, UrllibFactoryHttpTransport
from .front_obstacle import ClearFrontObstacleInput, FrontObstacleObservationInput
from .ironx_adapter import IronXAdapter
from .models import Pose
from .perception import PoseFusion, load_course_markers
from .ros2_readonly_adapter import Ros2ReadOnlyAdapter
from .rover_protocol import RoverError, RoverHello, rover_session_message_adapter
from .rover_registry import RoverProtocolError, RoverRegistry
from .runtime import RoverRuntime, RuntimeConfig, RuntimeMetadata
from .scenario import ReplayRequest, ScenarioController, ScenarioEventInput
from .simulator import DifferentialDriveSimulator, SimulatorFaults, SimulatorPoseInput
from .structured_log import StructuredLog
from .websocket_rover_adapter import WebSocketRoverAdapter

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCENARIO_DIRECTORY = Path(__file__).resolve().parents[2] / "scenarios"
COURSE_MARKERS_FILE = Path(__file__).resolve().parents[2] / "config" / "course-markers.json"
APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig.from_environment(REPOSITORY_ROOT)
    structured_log = StructuredLog(config.log_directory)
    rover_registry = RoverRegistry(
        config.rover_token_value(),
        structured_log=structured_log,
    )
    pose_fusion = PoseFusion(load_course_markers(COURSE_MARKERS_FILE))
    simulator: DifferentialDriveSimulator | None = None
    scenarios: ScenarioController | None = None
    if config.adapter_type == "simulator":
        adapter = simulator = DifferentialDriveSimulator()
    elif config.adapter_type == "ros2_readonly":
        adapter = Ros2ReadOnlyAdapter(config.ros2_state_file)
    elif config.adapter_type == "ironx":
        adapter = IronXAdapter(
            config.ros2_state_file, config.ironx_command_file, config.ironx_bridge_state_file
        )
    elif config.adapter_type == "websocket_rover":
        if config.rover_id is None:
            raise RuntimeError("validated websocket_rover config has no rover_id")
        adapter = WebSocketRoverAdapter(rover_registry, config.rover_id)
    else:
        if config.factory_http_host is None:
            raise RuntimeError("validated factory_http config has no host")
        adapter = FactoryHttpRoverAdapter(
            UrllibFactoryHttpTransport(
                str(config.factory_http_host),
                port=config.factory_http_port,
            )
        )
    runtime = RoverRuntime(
        adapter,
        config=RuntimeConfig(max_vx=0.05, max_wz=0.2, motion_ttl_ms=200)
        if config.adapter_type == "ironx"
        else None,
        structured_log=structured_log,
        pose_fusion=pose_fusion,
        metadata=RuntimeMetadata(
            instance_id=config.instance_id,
            deployment_profile=config.deployment_profile,
            app_version=APP_VERSION,
            build_id=config.build_id,
            adapter_type=config.adapter_type,
        ),
    )
    if simulator is not None:
        scenarios = ScenarioController(runtime, simulator, structured_log, SCENARIO_DIRECTORY)
    app.state.apris_config = config
    app.state.rover_runtime = runtime
    app.state.rover_registry = rover_registry
    app.state.simulator_scenarios = scenarios
    app.state.structured_log = structured_log
    app.state.assistant_interpreter = AssistantIntentInterpreter(
        config.assistant_api_key_value(),
        config.assistant_model,
    )
    await runtime.start()
    try:
        yield
    finally:
        if scenarios is not None:
            await scenarios.close()
        await runtime.close()
        await rover_registry.close()
        structured_log.close()


app = FastAPI(title="APRIS Rover Local Server", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/livez")
async def livez() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ros2")
async def ros2_monitor() -> FileResponse:
    return FileResponse(Path(__file__).with_name("ros2_monitor.html"))


@app.get("/api/readyz")
async def readyz() -> JSONResponse:
    status = await _server_status()
    return JSONResponse(status_code=200 if status["ready"] else 503, content=status)


@app.get("/api/status")
async def runtime_status() -> dict[str, object]:
    return await _server_status()


@app.get("/api/assistant/status")
async def assistant_status() -> dict[str, object]:
    interpreter: AssistantIntentInterpreter = app.state.assistant_interpreter
    return {
        "configured": interpreter.configured,
        "mode": "openai" if interpreter.configured else "rules",
        "model": interpreter.model if interpreter.configured else None,
    }


@app.post("/api/assistant/interpret")
async def interpret_assistant_command(
    request: AssistantCommandRequest,
) -> dict[str, object]:
    interpreter: AssistantIntentInterpreter = app.state.assistant_interpreter
    return (await interpreter.interpret(request.text, request.intents)).model_dump(mode="json")


@app.get("/api/health", deprecated=True)
async def health() -> JSONResponse:
    status = await _server_status()
    return JSONResponse(
        status_code=200 if status["ready"] else 503,
        content={
            "status": status["status"],
            "adapter": status["adapter"]["type"],
        },
    )


@app.get("/api/simulator/scenarios")
async def simulator_scenarios() -> dict[str, object]:
    controller = _simulator_controller()
    return {"scenarios": controller.list_scenarios()}


@app.get("/api/simulator/status")
async def simulator_status() -> dict[str, object]:
    controller = _simulator_controller()
    return await controller.status()


@app.post("/api/simulator/scenarios/{scenario_id}/run", status_code=202)
async def run_simulator_scenario(scenario_id: str) -> dict[str, object]:
    controller = _simulator_controller()
    try:
        return await controller.run(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown simulator scenario") from exc


@app.post("/api/simulator/scenarios/stop")
async def stop_simulator_scenario() -> dict[str, object]:
    controller = _simulator_controller()
    stopped = await controller.stop()
    return {"stopped": stopped, "status": await controller.status()}


@app.post("/api/simulator/events")
async def inject_simulator_event(event: ScenarioEventInput) -> dict[str, object]:
    controller = _simulator_controller()
    message = await controller.inject_event(event)
    return message.model_dump(mode="json")


@app.put("/api/simulator/pose")
async def place_simulator_pose(request: SimulatorPoseInput) -> dict[str, object]:
    controller = _simulator_controller()
    markers = load_course_markers(COURSE_MARKERS_FILE)
    if len({marker.id for marker in request.markers}) != len(request.markers):
        raise HTTPException(status_code=422, detail="Duplicate marker IDs")
    for marker in request.markers:
        if marker.id not in markers:
            raise HTTPException(status_code=422, detail="Unknown marker ID")
        markers[marker.id] = markers[marker.id].model_copy(
            update={"x_m": marker.x_m, "y_m": marker.y_m}
        )
    await controller.stop()
    runtime: RoverRuntime = app.state.rover_runtime
    await runtime.prepare_simulator_scenario("playground scene reset")
    await controller.clear_faults()
    await controller.simulator.reset_pose()
    pose = Pose(**request.model_dump(exclude={"markers"}))
    runtime.pose_fusion.markers = markers
    runtime.pose_fusion.set_course_origin(pose)
    app.state.structured_log.record("simulator", "pose_placed", request.model_dump())
    return {"pose": pose.model_dump(mode="json")}


@app.put("/api/simulator/faults")
async def set_simulator_faults(faults: SimulatorFaults) -> dict[str, object]:
    controller = _simulator_controller()
    applied = await controller.set_faults(faults)
    return {"faults": applied.model_dump(mode="json")}


@app.delete("/api/simulator/faults")
async def clear_simulator_faults() -> dict[str, object]:
    controller = _simulator_controller()
    await controller.clear_faults()
    return {"faults": (await controller.simulator.faults()).model_dump(mode="json")}


@app.put("/api/simulator/front-obstacle")
async def set_simulator_front_obstacle(
    observation: FrontObstacleObservationInput,
) -> dict[str, object]:
    controller = _simulator_controller()
    snapshot = await controller.set_front_obstacle(observation)
    return {"front_obstacle": snapshot.model_dump(mode="json")}


@app.post("/api/simulator/front-obstacle/clear")
async def clear_simulator_front_obstacle(
    request: ClearFrontObstacleInput,
) -> dict[str, object]:
    controller = _simulator_controller()
    try:
        snapshot = await controller.clear_front_obstacle(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"front_obstacle": snapshot.model_dump(mode="json")}


@app.get("/api/simulator/logs")
async def simulator_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    include_state: bool = False,
) -> dict[str, object]:
    _simulator_controller()
    structured_log: StructuredLog = app.state.structured_log
    return {
        "session_id": structured_log.session_id,
        "filename": structured_log.filename,
        "entries": structured_log.recent(limit, include_state=include_state),
    }


@app.delete("/api/simulator/logs")
async def clear_simulator_logs() -> dict[str, object]:
    _simulator_controller()
    structured_log: StructuredLog = app.state.structured_log
    structured_log.clear_memory()
    return {"session_id": structured_log.session_id, "cleared": True}


@app.post("/api/simulator/logs/replay", status_code=202)
async def replay_simulator_inputs(request: ReplayRequest) -> dict[str, object]:
    controller = _simulator_controller()
    try:
        return await controller.replay_inputs(request.speed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.websocket("/ws")
async def rover_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime: RoverRuntime = websocket.app.state.rover_runtime
    client_id = await runtime.add_client(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            await runtime.handle_text(client_id, raw)
    except WebSocketDisconnect:
        pass
    except RuntimeError as exc:
        if "WebSocket is not connected" not in str(exc):
            raise
    finally:
        await runtime.remove_client(client_id)


@app.websocket("/ws/rover")
async def device_rover_websocket(websocket: WebSocket) -> None:
    registry: RoverRegistry = websocket.app.state.rover_registry
    if not registry.authorize(websocket.headers.get("authorization")):
        await websocket.close(
            code=4401 if registry.credential_configured else 4403,
            reason=(
                "invalid rover credential"
                if registry.credential_configured
                else "rover credential is not configured"
            ),
        )
        return

    await websocket.accept()
    rover_id: str | None = None
    connection_epoch: str | None = None
    try:
        try:
            raw_hello = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            hello = RoverHello.model_validate_json(raw_hello)
        except TimeoutError:
            await websocket.send_json(
                RoverError(
                    code="rover_hello_timeout",
                    detail="rover_hello must be the first message",
                ).model_dump(mode="json")
            )
            await websocket.close(code=4408, reason="rover_hello timeout")
            return
        except ValidationError:
            await websocket.send_json(
                RoverError(
                    code="invalid_rover_hello",
                    detail="First message must be a valid rover_hello",
                ).model_dump(mode="json")
            )
            await websocket.close(code=4400, reason="invalid rover_hello")
            return

        runtime: RoverRuntime = websocket.app.state.rover_runtime
        welcome = await registry.connect(
            websocket,
            hello,
            server_version=runtime.metadata.app_version,
            build_id=runtime.metadata.build_id,
            instance_id=runtime.metadata.instance_id,
        )
        rover_id = hello.rover_id
        connection_epoch = welcome.connection_epoch
        await websocket.send_json(welcome.model_dump(mode="json"))

        while True:
            raw = await websocket.receive_text()
            try:
                message = rover_session_message_adapter.validate_json(raw)
                await registry.handle(rover_id, connection_epoch, message)
            except ValidationError:
                await websocket.send_json(
                    RoverError(
                        code="invalid_rover_message",
                        detail="Message does not match Rover protocol v1",
                    ).model_dump(mode="json")
                )
            except RoverProtocolError as exc:
                await websocket.send_json(
                    RoverError(code=exc.code, detail=exc.detail).model_dump(mode="json")
                )
                await websocket.close(code=exc.close_code, reason=exc.code)
                return
    except RoverProtocolError as exc:
        await websocket.send_json(
            RoverError(code=exc.code, detail=exc.detail).model_dump(mode="json")
        )
        await websocket.close(code=exc.close_code, reason=exc.code)
    except WebSocketDisconnect:
        pass
    finally:
        if rover_id is not None and connection_epoch is not None:
            await registry.disconnect(rover_id, connection_epoch)


async def _server_status() -> dict[str, object]:
    runtime: RoverRuntime = app.state.rover_runtime
    registry: RoverRegistry = app.state.rover_registry
    status = await runtime.status()
    status["rovers"] = await registry.status()
    return status


def _simulator_controller() -> ScenarioController:
    controller: ScenarioController | None = app.state.simulator_scenarios
    if controller is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "simulator_only",
                "message": "This endpoint is unavailable for the selected Rover Adapter",
            },
        )
    return controller


PWA_DIST = Path(__file__).resolve().parents[3] / "pwa" / "dist"
if PWA_DIST.exists():
    assets = PWA_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_pwa(path: str) -> FileResponse:
        requested = PWA_DIST / path
        if path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(PWA_DIST / "index.html")
