from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .adapter import (
    BoundedMotionExecutionError,
    BoundedMotionGoal,
    BoundedMotionResult,
    DeviceBoundedMotionAdapter,
)
from .models import Capabilities, RoverState, Velocity
from .odometry import OdometryConfig, WheelImuOdometry


class FactoryHttpError(RuntimeError):
    pass


class FactoryHttpFeedback(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    response_type: int = Field(alias="T")
    left_mps: float = Field(alias="L")
    right_mps: float = Field(alias="R")
    left_odometry_cm: int = Field(alias="odl")
    right_odometry_cm: int = Field(alias="odr")
    voltage_centivolts: int = Field(alias="v")

    @field_validator("left_mps", "right_mps")
    @classmethod
    def finite_speed(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("wheel speed must be finite")
        return value

    @field_validator("response_type")
    @classmethod
    def base_feedback_only(cls, value: int) -> int:
        if value != 1001:
            raise ValueError("response is not UGV02 base feedback")
        return value


class FactoryHttpTransport(Protocol):
    async def send(
        self,
        command: dict[str, Any],
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any] | None: ...


class UrllibFactoryHttpTransport:
    def __init__(self, host: str, port: int = 80, timeout_s: float = 0.6) -> None:
        self.base_url = f"http://{host}:{port}"
        self.timeout_s = timeout_s

    async def send(
        self,
        command: dict[str, Any],
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any] | None:
        request = asyncio.create_task(
            asyncio.to_thread(self._send_sync, command, allow_empty_response)
        )
        try:
            return await asyncio.shield(request)
        except asyncio.CancelledError:
            # A cancelled to_thread task does not stop its socket operation. Resolve the
            # ambiguous request before the adapter sends its cancellation stop commands.
            await asyncio.shield(request)
            raise

    def _send_sync(
        self,
        command: dict[str, Any],
        allow_empty_response: bool,
    ) -> dict[str, Any] | None:
        query = urllib.parse.urlencode(
            {"json": json.dumps(command, separators=(",", ":"))}
        )
        url = f"{self.base_url}/js?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_s) as response:  # noqa: S310
            raw = response.read(16_385)
        if len(raw) > 16_384:
            raise FactoryHttpError("UGV02 HTTP response exceeds 16 KiB")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FactoryHttpError("UGV02 returned invalid JSON") from exc
        if payload is None and allow_empty_response:
            return None
        if not isinstance(payload, dict):
            raise FactoryHttpError("UGV02 returned a non-object response")
        return payload


@dataclass(slots=True)
class FactoryHttpAdapterConfig:
    track_width_m: float = 0.172
    max_wheel_speed_mps: float = 0.08
    command_refresh_interval_s: float = 1.0
    poll_interval_s: float = 0.50
    feedback_stale_after_s: float = 1.60
    stop_attempts: int = 6
    required_stop_sends: int = 2
    retry_delay_s: float = 0.05


class FactoryHttpRoverAdapter(DeviceBoundedMotionAdapter):
    """Diagnostic adapter for an unmodified UGV02 v0.96 factory firmware."""

    def __init__(
        self,
        transport: FactoryHttpTransport,
        config: FactoryHttpAdapterConfig | None = None,
    ) -> None:
        self.transport = transport
        self.config = config or FactoryHttpAdapterConfig()
        centimetre_odometry = OdometryConfig(
            wheel_radius_m=1.0 / (2.0 * math.pi),
            track_width_m=self.config.track_width_m,
            ticks_per_revolution=100,
            imu_weight=0.0,
        )
        self._odometry = WheelImuOdometry(centimetre_odometry)
        self._request_lock = asyncio.Lock()
        self._motion_lock = asyncio.Lock()
        self._running = False
        self._poll_task: asyncio.Task[None] | None = None
        self._last_feedback: FactoryHttpFeedback | None = None
        self._last_feedback_monotonic: float | None = None
        self._last_feedback_wall_time: float | None = None
        self._last_transport_error = False
        self._drive_deadline: float | None = None
        self._last_drive_target: tuple[float, float] | None = None
        self._last_drive_sent_at: float | None = None

    async def start(self) -> None:
        if self._running:
            return
        await self._confirmed_stop()
        await self._poll_once()
        self._running = True
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name="ugv02-factory-http-poll",
        )

    async def close(self) -> None:
        self._running = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        with contextlib.suppress(Exception):
            await self._confirmed_stop()

    async def drive(self, vx: float, vy: float, wz: float, *, ttl_ms: int = 500) -> None:
        if abs(vy) > 1e-9:
            raise ValueError("differential-drive adapter does not support lateral velocity")
        if not all(math.isfinite(value) for value in (vx, wz)):
            raise ValueError("velocity must be finite")

        half_track = self.config.track_width_m * 0.5
        left = vx - wz * half_track
        right = vx + wz * half_track
        peak = max(abs(left), abs(right))
        if peak > self.config.max_wheel_speed_mps:
            scale = self.config.max_wheel_speed_mps / peak
            left *= scale
            right *= scale

        target = (round(left, 4), round(right, 4))
        ttl_s = max(100, min(ttl_ms, 800)) / 1000.0
        async with self._motion_lock:
            now = time.monotonic()
            self._drive_deadline = now + ttl_s
            if (
                target == self._last_drive_target
                and self._last_drive_sent_at is not None
                and now - self._last_drive_sent_at
                < self.config.command_refresh_interval_s
            ):
                return

            try:
                await self._send(
                    {"T": 1, "L": target[0], "R": target[1]},
                    allow_empty_response=True,
                )
            except asyncio.CancelledError:
                await asyncio.shield(self._best_effort_stop_locked())
                raise
            except Exception:
                await self._best_effort_stop_locked()
                raise
            sent_at = time.monotonic()
            self._last_drive_target = target
            self._last_drive_sent_at = sent_at
            self._drive_deadline = sent_at + ttl_s

    async def stop(self) -> None:
        await self._confirmed_stop()

    async def emergency_stop(self, reason: str) -> None:
        del reason
        await self._confirmed_stop()

    async def clear_emergency_stop(self) -> None:
        return None

    async def reset_pose(self) -> None:
        self._odometry.reset()

    async def state(self, command_age_ms: float | None = None) -> RoverState:
        now = time.monotonic()
        age_s = (
            None
            if self._last_feedback_monotonic is None
            else max(0.0, now - self._last_feedback_monotonic)
        )
        connected = bool(
            self._running
            and age_s is not None
            and age_s <= self.config.feedback_stale_after_s
        )
        feedback = self._last_feedback
        anomalies = ["factory_http_diagnostic_only"]
        if self._last_transport_error:
            anomalies.append("factory_http_transport_error")
        if not connected:
            anomalies.append("factory_http_feedback_stale")

        quality = self._odometry.quality(age_ms=(age_s or 0.0) * 1000.0)
        quality = quality.model_copy(
            update={
                "confidence": min(quality.confidence, 0.62) if connected else 0.0,
                "anomalies": [*quality.anomalies, *anomalies],
            }
        )
        left = feedback.left_mps if feedback is not None else 0.0
        right = feedback.right_mps if feedback is not None else 0.0
        return RoverState(
            timestamp=self._last_feedback_wall_time or time.time(),
            connected=connected,
            pose=self._odometry.pose,
            velocity=Velocity(
                vx=(left + right) * 0.5,
                vy=0.0,
                wz=(right - left) / self.config.track_width_m,
            ),
            battery_percent=None,
            capabilities=Capabilities(pose=True, imu=False),
            command_age_ms=command_age_ms,
            pose_quality=quality,
        )

    async def execute_bounded_motion(self, goal: BoundedMotionGoal) -> BoundedMotionResult:
        result = BoundedMotionResult(
            motion_id=goal.motion_id,
            status="failed",
            reason="factory_http_manual_control_only",
        )
        raise BoundedMotionExecutionError(result)

    async def _poll_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.poll_interval_s)
            async with self._motion_lock:
                if (
                    self._drive_deadline is not None
                    and time.monotonic() >= self._drive_deadline
                ):
                    try:
                        await self._confirmed_stop_locked()
                    except Exception:
                        self._last_transport_error = True
            try:
                await self._poll_once()
            except Exception:
                self._last_transport_error = True

    async def _poll_once(self) -> None:
        last_error: Exception | None = None
        for _ in range(3):
            try:
                payload = await self._send({"T": 130})
                assert payload is not None
                feedback = FactoryHttpFeedback.model_validate(payload)
                now = time.monotonic()
                self._odometry.update(
                    timestamp=now,
                    left_ticks=feedback.left_odometry_cm,
                    right_ticks=feedback.right_odometry_cm,
                    imu_yaw_rate_rad_s=None,
                )
                self._last_feedback = feedback
                self._last_feedback_monotonic = now
                self._last_feedback_wall_time = time.time()
                self._last_transport_error = False
                return
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(self.config.retry_delay_s)
        raise FactoryHttpError("could not read UGV02 base feedback") from last_error

    async def _confirmed_stop(self) -> None:
        async with self._motion_lock:
            await self._confirmed_stop_locked()

    async def _confirmed_stop_locked(self) -> None:
        successful_sends = 0
        last_error: Exception | None = None
        self._drive_deadline = None
        self._last_drive_target = None
        self._last_drive_sent_at = None
        for _ in range(self.config.stop_attempts):
            try:
                await self._send(
                    {"T": 1, "L": 0, "R": 0},
                    allow_empty_response=True,
                )
                successful_sends += 1
                if successful_sends >= self.config.required_stop_sends:
                    return
            except Exception as exc:
                last_error = exc
            await asyncio.sleep(self.config.retry_delay_s)
        raise FactoryHttpError("could not send two UGV02 stop commands") from last_error

    async def _best_effort_stop_locked(self) -> None:
        with contextlib.suppress(Exception):
            await self._confirmed_stop_locked()

    async def _send(
        self,
        command: dict[str, Any],
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any] | None:
        async with self._request_lock:
            return await self.transport.send(
                command,
                allow_empty_response=allow_empty_response,
            )
