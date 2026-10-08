from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

WORLD_PROTOCOL_VERSION = 1
SUPPORTED_EFFECTS = frozenset(
    {"forward", "backward", "turn_left", "turn_right", "front_blocked"}
)


class JsonSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str: ...

    async def close(self) -> None: ...


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    physicode_ws_url: str
    apris_ws_url: str
    run_id: str
    driver_token: str
    world_id: str
    cell_size_m: float = 0.25
    turn_angle_deg: float = 90.0
    move_speed_mps: float = 0.18
    turn_speed_rad_s: float = 0.70
    motion_timeout_s: float = 30.0
    device_id: str = "apris-physicode-bridge"
    session_id: str = ""
    app_version: str = "0.1.0"
    build_id: str = "development"
    start_run_url: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id or not self.driver_token or not self.world_id:
            raise ValueError("run_id, driver_token, and world_id are required")
        if self.cell_size_m <= 0 or self.cell_size_m > 5:
            raise ValueError("cell_size_m must be greater than 0 and at most 5")
        if self.turn_angle_deg <= 0 or self.turn_angle_deg > 720:
            raise ValueError("turn_angle_deg must be greater than 0 and at most 720")
        if self.motion_timeout_s <= 0:
            raise ValueError("motion_timeout_s must be greater than 0")
        if not 0.05 <= self.move_speed_mps <= 0.30:
            raise ValueError("move_speed_mps must be between 0.05 and 0.30")
        if not 0.10 <= self.turn_speed_rad_s <= 1.20:
            raise ValueError("turn_speed_rad_s must be between 0.10 and 1.20")

    @property
    def world_socket_url(self) -> str:
        base = self.physicode_ws_url.rstrip("/")
        run_id = quote(self.run_id, safe="")
        return f"{base}/ws/world/{run_id}"

    @property
    def world_subprotocol(self) -> str:
        return f"physicode-driver.{self.driver_token}"


class PhysiCodeBridge:
    def __init__(self, config: BridgeConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("apris.physicode_bridge")
        self._apris_has_control = False
        self._active_request_id: str | None = None

    async def run(self) -> dict[str, Any]:
        async with connect(self.config.apris_ws_url) as apris_socket:
            try:
                async with connect(
                    self.config.world_socket_url,
                    subprotocols=[self.config.world_subprotocol],
                ) as world_socket:
                    return await self.run_with_sockets(world_socket, apris_socket)
            finally:
                await self._safe_release(apris_socket)

    async def run_with_sockets(
        self,
        world_socket: JsonSocket,
        apris_socket: JsonSocket,
    ) -> dict[str, Any]:
        try:
            await self._acquire_apris_control(apris_socket)
            await self._register_world(world_socket)
            if self.config.start_run_url is not None:
                await asyncio.to_thread(self._start_run)
            while True:
                try:
                    message = await self._receive_json(world_socket)
                except ConnectionClosed as exc:
                    raise BridgeError(
                        "physicode_disconnected", "PhysiCode World connection closed"
                    ) from exc
                self._require_v1(message, "PhysiCode")
                message_type = message.get("type")
                if message_type == "world_pong":
                    continue
                if message_type == "protocol_error":
                    raise BridgeError(
                        str(message.get("code", "physicode_protocol_error")),
                        str(message.get("message", "PhysiCode rejected the Bridge")),
                    )
                if message_type == "run_finished":
                    self._log("run_finished", status=message.get("status"))
                    return message
                if message_type != "effect":
                    raise BridgeError(
                        "unexpected_world_message",
                        f"unexpected PhysiCode message type {message_type!r}",
                    )
                await self._handle_effect(message, world_socket, apris_socket)
        finally:
            await self._safe_release(apris_socket)

    async def _acquire_apris_control(self, socket: JsonSocket) -> None:
        hello = await self._receive_until(socket, {"hello"}, self.config.motion_timeout_s)
        self._require_v1(hello, "APRIS")
        if WORLD_PROTOCOL_VERSION not in hello.get("supported_protocol_versions", []):
            raise BridgeError(
                "apris_protocol_incompatible", "APRIS Server does not support Client protocol v1"
            )
        session_id = self.config.session_id or self.config.run_id
        await self._send_json(
            socket,
            {
                "v": 1,
                "type": "client_hello",
                "client_kind": "physicode_bridge",
                "device_id": self.config.device_id,
                "session_id": session_id,
                "app_version": self.config.app_version,
                "build_id": self.config.build_id,
            },
        )
        await self._send_json(socket, {"v": 1, "type": "acquire_control"})
        while True:
            message = await self._receive_json_with_timeout(socket, self.config.motion_timeout_s)
            self._require_v1(message, "APRIS")
            if message.get("type") == "error":
                raise BridgeError(
                    f"apris_{message.get('code', 'error')}",
                    str(message.get("detail", "APRIS rejected control acquisition")),
                )
            if message.get("type") == "control" and message.get("is_owner") is True:
                if message.get("estop_latched") is True:
                    raise BridgeError(
                        "apris_estop_latched", "APRIS emergency stop is latched"
                    )
                self._apris_has_control = True
                self._log("control_acquired")
                return

    async def _register_world(self, socket: JsonSocket) -> None:
        await self._send_json(
            socket,
            {
                "v": WORLD_PROTOCOL_VERSION,
                "type": "world_hello",
                "world_id": self.config.world_id,
                "world_kind": "platform_gateway",
                "app_version": self.config.app_version,
                "build_id": self.config.build_id,
                "capabilities": sorted(SUPPORTED_EFFECTS),
            },
        )
        message = await self._receive_json_with_timeout(socket, self.config.motion_timeout_s)
        self._require_v1(message, "PhysiCode")
        if message.get("type") == "protocol_error":
            raise BridgeError(
                str(message.get("code", "world_registration_failed")),
                str(message.get("message", "PhysiCode rejected world_hello")),
            )
        if message.get("type") != "world_ready" or message.get("run_id") != self.config.run_id:
            raise BridgeError("world_not_ready", "PhysiCode did not acknowledge this Run")
        self._log("world_ready")

    async def _handle_effect(
        self,
        effect: dict[str, Any],
        world_socket: JsonSocket,
        apris_socket: JsonSocket,
    ) -> None:
        if effect.get("run_id") != self.config.run_id:
            raise BridgeError("wrong_run_id", "effect run_id does not match assigned Run")
        effect_id = effect.get("effect_id")
        effect_name = effect.get("name")
        if not isinstance(effect_id, str) or not effect_id:
            raise BridgeError("invalid_effect_id", "effect_id must be a non-empty string")
        if effect_name not in SUPPORTED_EFFECTS:
            await self._send_failed_result(
                world_socket,
                effect_id,
                "unsupported_effect",
                f"APRIS Bridge does not support effect {effect_name!r}",
            )
            return
        if effect.get("args") not in (None, []):
            await self._send_failed_result(
                world_socket,
                effect_id,
                "unsupported_effect_args",
                f"APRIS Bridge does not support arguments for {effect_name}",
            )
            return

        request_id = self._motion_request_id(effect_id)
        self._active_request_id = request_id
        self._log(
            "effect_started",
            effect_id=effect_id,
            effect_name=effect_name,
            request_id=request_id,
        )
        if effect_name == "front_blocked":
            await self._handle_front_blocked(
                effect_id,
                request_id,
                world_socket,
                apris_socket,
            )
            return
        await self._send_json(
            apris_socket,
            self._motion_command(effect_name, effect_id, request_id),
        )
        try:
            outcome = await self._wait_for_motion_or_world_exit(
                world_socket,
                apris_socket,
                request_id,
                effect_name,
            )
        except (ConnectionClosed, OSError):
            outcome = ("cancelled", None, None)
        finally:
            self._active_request_id = None
        status, value, error = outcome
        result: dict[str, Any] = {
            "v": WORLD_PROTOCOL_VERSION,
            "type": "effect_result",
            "run_id": self.config.run_id,
            "effect_id": effect_id,
            "status": status,
            "value": value,
        }
        if error is not None:
            result["error"] = error
        await self._send_json(world_socket, result)
        self._log(
            "effect_finished",
            effect_id=effect_id,
            effect_name=effect_name,
            request_id=request_id,
            status=status,
            value=value,
            error=error,
        )

    async def _handle_front_blocked(
        self,
        effect_id: str,
        request_id: str,
        world_socket: JsonSocket,
        apris_socket: JsonSocket,
    ) -> None:
        await self._send_json(
            apris_socket,
            {
                "v": 1,
                "type": "read_front_obstacle",
                "request_id": request_id,
                "run_id": self.config.run_id,
                "effect_id": effect_id,
            },
        )
        try:
            obstacle = await self._wait_for_front_obstacle(apris_socket, request_id)
        except (ConnectionClosed, OSError):
            status, value, error = "cancelled", None, None
        else:
            state = obstacle.get("state")
            healthy = obstacle.get("perception_health") == "healthy"
            stale = obstacle.get("stale") is True
            if state == "BLOCKED":
                status, value, error = "completed", True, None
            elif state == "CLEAR" and healthy and not stale:
                status, value, error = "completed", False, None
            else:
                status, value, error = (
                    "failed",
                    None,
                    {
                        "code": "perception_unavailable",
                        "message": "APRIS front-obstacle state is UNKNOWN or unhealthy",
                    },
                )
        result: dict[str, Any] = {
            "v": WORLD_PROTOCOL_VERSION,
            "type": "effect_result",
            "run_id": self.config.run_id,
            "effect_id": effect_id,
            "status": status,
            "value": value,
        }
        if error is not None:
            result["error"] = error
        await self._send_json(world_socket, result)
        self._active_request_id = None
        self._log(
            "effect_finished",
            effect_id=effect_id,
            effect_name="front_blocked",
            request_id=request_id,
            status=status,
            value=value,
            error=error,
        )

    async def _wait_for_front_obstacle(
        self,
        socket: JsonSocket,
        request_id: str,
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(self.config.motion_timeout_s):
                while True:
                    message = await self._receive_json(socket)
                    self._require_v1(message, "APRIS")
                    if message.get("type") == "error":
                        raise BridgeError(
                            f"apris_{message.get('code', 'error')}",
                            str(message.get("detail", "APRIS sensor read failed")),
                        )
                    if (
                        message.get("type") == "front_obstacle"
                        and message.get("request_id") == request_id
                    ):
                        obstacle = message.get("obstacle")
                        if not isinstance(obstacle, dict):
                            raise BridgeError(
                                "invalid_front_obstacle",
                                "APRIS returned an invalid front-obstacle snapshot",
                            )
                        return obstacle
        except TimeoutError as exc:
            raise BridgeError(
                "apris_sensor_timeout",
                "APRIS did not return front-obstacle state before timeout",
            ) from exc

    async def _wait_for_motion_or_world_exit(
        self,
        world_socket: JsonSocket,
        apris_socket: JsonSocket,
        request_id: str,
        effect_name: str,
    ) -> tuple[str, Any, dict[str, str] | None]:
        motion_task = asyncio.create_task(
            self._wait_for_motion(apris_socket, request_id, effect_name)
        )
        world_task = asyncio.create_task(self._receive_json(world_socket))
        done, pending = await asyncio.wait(
            {motion_task, world_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if motion_task in done:
            world_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await world_task
            return motion_task.result()

        await self._send_json(apris_socket, {"v": 1, "type": "cancel_motion"})
        motion_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await motion_task
        try:
            message = world_task.result()
        except ConnectionClosed as exc:
            raise BridgeError(
                "physicode_disconnected",
                "PhysiCode disconnected while an APRIS motion was active",
            ) from exc
        except OSError as exc:
            raise BridgeError(
                "physicode_disconnected",
                "PhysiCode disconnected while an APRIS motion was active",
            ) from exc
        self._require_v1(message, "PhysiCode")
        if message.get("type") == "protocol_error":
            raise BridgeError(
                str(message.get("code", "physicode_protocol_error")),
                str(message.get("message", "PhysiCode rejected the active effect")),
            )
        raise BridgeError(
            "run_ended_during_motion",
            f"PhysiCode sent {message.get('type')!r} while APRIS motion was active",
        )

    async def _wait_for_motion(
        self,
        socket: JsonSocket,
        request_id: str,
        effect_name: str,
    ) -> tuple[str, Any, dict[str, str] | None]:
        try:
            async with asyncio.timeout(self.config.motion_timeout_s):
                while True:
                    message = await self._receive_json(socket)
                    self._require_v1(message, "APRIS")
                    message_type = message.get("type")
                    if message_type == "control" and message.get("is_owner") is False:
                        return "cancelled", None, None
                    if message_type == "error":
                        code = str(message.get("code", "error"))
                        if code in {"not_controller", "estop_latched"}:
                            return "cancelled", None, None
                        return (
                            "failed",
                            None,
                            {
                                "code": f"apris_{code}",
                                "message": str(message.get("detail", "APRIS command failed")),
                            },
                        )
                    if message_type != "motion" or message.get("request_id") != request_id:
                        continue
                    status = message.get("status")
                    if status == "started":
                        continue
                    detail = str(message.get("detail", ""))
                    if status == "completed":
                        value = "moved" if effect_name in {"forward", "backward"} else None
                        return "completed", value, None
                    if status == "cancelled" and self._is_obstacle_stop(detail):
                        value = "blocked" if effect_name == "forward" else None
                        return "completed", value, None
                    if status == "cancelled" or self._is_safety_cancellation(detail):
                        return "cancelled", None, None
                    if status == "failed":
                        if "front_obstacle_unknown" in detail.casefold():
                            return (
                                "failed",
                                None,
                                {
                                    "code": "perception_unavailable",
                                    "message": detail,
                                },
                            )
                        return (
                            "failed",
                            None,
                            {
                                "code": "apris_motion_failed",
                                "message": detail or "APRIS motion failed",
                            },
                        )
        except TimeoutError:
            await self._send_json(socket, {"v": 1, "type": "cancel_motion"})
            return (
                "failed",
                None,
                {
                    "code": "apris_motion_timeout",
                    "message": "APRIS motion did not finish before Bridge timeout",
                },
            )

    def _motion_command(
        self, effect_name: str, effect_id: str, request_id: str
    ) -> dict[str, Any]:
        if effect_name in {"forward", "backward"}:
            direction = 1.0 if effect_name == "forward" else -1.0
            return {
                "v": 1,
                "type": "move",
                "request_id": request_id,
                "run_id": self.config.run_id,
                "effect_id": effect_id,
                "distance_m": direction * self.config.cell_size_m,
                "speed_mps": self.config.move_speed_mps,
            }
        direction = 1.0 if effect_name == "turn_left" else -1.0
        return {
            "v": 1,
            "type": "turn",
            "request_id": request_id,
            "run_id": self.config.run_id,
            "effect_id": effect_id,
            "angle_deg": direction * self.config.turn_angle_deg,
            "speed_rad_s": self.config.turn_speed_rad_s,
        }

    def _motion_request_id(self, effect_id: str) -> str:
        candidate = f"pc:{self.config.run_id}:{effect_id}"
        if len(candidate) <= 64:
            return candidate
        digest = hashlib.sha256(candidate.encode()).hexdigest()[:24]
        return f"pc:{self.config.run_id[:16]}:{effect_id[:16]}:{digest}"[:64]

    async def _safe_release(self, socket: JsonSocket) -> None:
        if not self._apris_has_control:
            return
        self._apris_has_control = False
        with contextlib.suppress(Exception):
            await self._send_json(socket, {"v": 1, "type": "cancel_motion"})
        with contextlib.suppress(Exception):
            await self._send_json(socket, {"v": 1, "type": "release_control"})
        self._log("control_released")

    def _start_run(self) -> None:
        assert self.config.start_run_url is not None
        base_url = self.config.start_run_url.rstrip("/") + "/"
        url = urljoin(base_url, f"api/runs/{self.config.run_id}/start")
        request = Request(url, data=b"", method="POST")
        with urlopen(request, timeout=self.config.motion_timeout_s) as response:  # noqa: S310
            if response.status != 200:
                raise BridgeError("run_start_failed", f"PhysiCode returned HTTP {response.status}")

    async def _send_failed_result(
        self,
        socket: JsonSocket,
        effect_id: str,
        code: str,
        message: str,
    ) -> None:
        await self._send_json(
            socket,
            {
                "v": 1,
                "type": "effect_result",
                "run_id": self.config.run_id,
                "effect_id": effect_id,
                "status": "failed",
                "value": None,
                "error": {"code": code, "message": message},
            },
        )

    async def _receive_until(
        self, socket: JsonSocket, message_types: set[str], timeout_s: float
    ) -> dict[str, Any]:
        async with asyncio.timeout(timeout_s):
            while True:
                message = await self._receive_json(socket)
                if message.get("type") in message_types:
                    return message

    @staticmethod
    async def _send_json(socket: JsonSocket, message: dict[str, Any]) -> None:
        await socket.send(json.dumps(message, separators=(",", ":")))

    @staticmethod
    async def _receive_json(socket: JsonSocket) -> dict[str, Any]:
        raw = await socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            message = json.loads(raw)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError("invalid_json", "peer sent invalid JSON") from exc
        if not isinstance(message, dict):
            raise BridgeError("invalid_message", "peer message must be a JSON object")
        return message

    @classmethod
    async def _receive_json_with_timeout(
        cls, socket: JsonSocket, timeout_s: float
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(timeout_s):
                return await cls._receive_json(socket)
        except TimeoutError as exc:
            raise BridgeError("peer_timeout", "peer did not respond in time") from exc

    @staticmethod
    def _require_v1(message: dict[str, Any], peer: str) -> None:
        if message.get("v") != WORLD_PROTOCOL_VERSION:
            raise BridgeError(
                "unsupported_protocol_version", f"{peer} message is not protocol v1"
            )

    @staticmethod
    def _is_obstacle_stop(detail: str) -> bool:
        normalized = detail.casefold().replace("-", "_").replace(" ", "_")
        return "front_obstacle_blocked" in normalized

    @staticmethod
    def _is_safety_cancellation(detail: str) -> bool:
        normalized = detail.casefold()
        return any(
            marker in normalized
            for marker in ("emergency stop", "control released", "controller disconnected")
        )

    def _log(self, event: str, **fields: Any) -> None:
        self.logger.info(
            json.dumps(
                {
                    "component": "physicode_bridge",
                    "event": event,
                    "run_id": self.config.run_id,
                    "world_id": self.config.world_id,
                    **fields,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive APRIS as a PhysiCode World v1")
    parser.add_argument("--physicode-ws", required=True, help="PhysiCode WS base URL")
    parser.add_argument("--apris-ws", required=True, help="APRIS Client WebSocket URL")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--driver-token",
        default=os.environ.get("PHYSICODE_DRIVER_TOKEN"),
        help="World driver token; prefer the PHYSICODE_DRIVER_TOKEN environment variable",
    )
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--cell-size-m", type=float, default=0.25)
    parser.add_argument("--turn-angle-deg", type=float, default=90.0)
    parser.add_argument("--move-speed-mps", type=float, default=0.18)
    parser.add_argument("--turn-speed-rad-s", type=float, default=0.70)
    parser.add_argument("--motion-timeout-s", type=float, default=30.0)
    parser.add_argument("--device-id", default="apris-physicode-bridge")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--app-version", default="0.1.0")
    parser.add_argument("--build-id", default="development")
    parser.add_argument(
        "--start-run-url",
        help=(
            "Optional PhysiCode HTTP base URL; explicitly starts the Run after both "
            "connections are ready"
        ),
    )
    return parser


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.driver_token:
        parser.error("--driver-token or PHYSICODE_DRIVER_TOKEN is required")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = BridgeConfig(
        physicode_ws_url=args.physicode_ws,
        apris_ws_url=args.apris_ws,
        run_id=args.run_id,
        driver_token=args.driver_token,
        world_id=args.world_id,
        cell_size_m=args.cell_size_m,
        turn_angle_deg=args.turn_angle_deg,
        move_speed_mps=args.move_speed_mps,
        turn_speed_rad_s=args.turn_speed_rad_s,
        motion_timeout_s=args.motion_timeout_s,
        device_id=args.device_id,
        session_id=args.session_id,
        app_version=args.app_version,
        build_id=args.build_id,
        start_run_url=args.start_run_url,
    )
    try:
        terminal = await PhysiCodeBridge(config).run()
    except (BridgeError, ConnectionClosed, OSError) as exc:
        logging.getLogger("apris.physicode_bridge").error(
            json.dumps(
                {
                    "component": "physicode_bridge",
                    "event": "bridge_failed",
                    "code": getattr(exc, "code", "connection_error"),
                    "message": str(exc),
                    "run_id": config.run_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    return 0 if terminal.get("status") == "COMPLETED" else 2


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
