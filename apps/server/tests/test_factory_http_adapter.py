from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from apris_server.adapter import BoundedMotionExecutionError, BoundedMotionGoal
from apris_server.factory_http_adapter import (
    FactoryHttpAdapterConfig,
    FactoryHttpRoverAdapter,
    UrllibFactoryHttpTransport,
)


class MemoryFactoryTransport:
    def __init__(self) -> None:
        self.commands: list[dict[str, Any]] = []
        self.feedback: dict[str, Any] = {
            "T": 1001,
            "L": 0.0,
            "R": 0.0,
            "odl": 0,
            "odr": 0,
            "v": 1230,
        }
        self.fail_nonzero_once = False
        self.nonzero_delay_s = 0.0

    async def send(
        self,
        command: dict[str, Any],
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any] | None:
        del allow_empty_response
        self.commands.append(dict(command))
        if command.get("T") == 130:
            return dict(self.feedback)
        if self.nonzero_delay_s and (command.get("L") or command.get("R")):
            await asyncio.sleep(self.nonzero_delay_s)
        if self.fail_nonzero_once and (command.get("L") or command.get("R")):
            self.fail_nonzero_once = False
            raise ConnectionResetError("ambiguous factory HTTP reset")
        return None


def adapter_config(**overrides: Any) -> FactoryHttpAdapterConfig:
    values = {
        "poll_interval_s": 0.01,
        "feedback_stale_after_s": 0.10,
        "retry_delay_s": 0.001,
    }
    values.update(overrides)
    return FactoryHttpAdapterConfig(**values)


@pytest.mark.asyncio
async def test_start_stops_before_feedback_and_reports_encoder_state() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())

    await adapter.start()
    try:
        assert transport.commands[:3] == [
            {"T": 1, "L": 0, "R": 0},
            {"T": 1, "L": 0, "R": 0},
            {"T": 130},
        ]
        state = await adapter.state()
        assert state.connected is True
        assert state.capabilities.pose is True
        assert state.capabilities.imu is False
        assert state.pose_quality.source == "unavailable"
        assert "factory_http_diagnostic_only" in state.pose_quality.anomalies

        transport.feedback.update({"L": 0.05, "R": 0.05, "odl": 10, "odr": 10})
        await asyncio.sleep(0.03)
        state = await adapter.state()
        assert state.pose.x == pytest.approx(0.10)
        assert state.velocity.vx == pytest.approx(0.05)
        assert state.pose_quality.source == "encoder_only"
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_drive_scales_wheels_and_local_ttl_sends_redundant_stop() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())
    await adapter.start()
    transport.commands.clear()

    try:
        await adapter.drive(1.0, 0.0, 0.0, ttl_ms=100)
        assert transport.commands[0] == {"T": 1, "L": 0.08, "R": 0.08}

        await asyncio.sleep(0.14)
        stop_commands = [
            command
            for command in transport.commands
            if command == {"T": 1, "L": 0, "R": 0}
        ]
        assert len(stop_commands) >= 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_drive_coalesces_identical_targets_but_sends_changes_immediately() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(
        transport,
        adapter_config(
            command_refresh_interval_s=0.03,
            poll_interval_s=10.0,
        ),
    )
    await adapter.start()
    transport.commands.clear()

    try:
        await adapter.drive(0.04, 0.0, 0.0)
        await adapter.drive(0.04, 0.0, 0.0)
        await adapter.drive(0.05, 0.0, 0.0)
        assert transport.commands == [
            {"T": 1, "L": 0.04, "R": 0.04},
            {"T": 1, "L": 0.05, "R": 0.05},
        ]

        await asyncio.sleep(0.04)
        await adapter.drive(0.05, 0.0, 0.0)
        assert transport.commands[-1] == {"T": 1, "L": 0.05, "R": 0.05}
        assert len(transport.commands) == 3
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_coalesced_drive_refreshes_local_ttl() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())
    await adapter.start()
    transport.commands.clear()

    try:
        await adapter.drive(0.04, 0.0, 0.0, ttl_ms=100)
        await asyncio.sleep(0.07)
        await adapter.drive(0.04, 0.0, 0.0, ttl_ms=100)
        await asyncio.sleep(0.07)
        assert {"T": 1, "L": 0, "R": 0} not in transport.commands

        await asyncio.sleep(0.06)
        stop_commands = [
            command
            for command in transport.commands
            if command == {"T": 1, "L": 0, "R": 0}
        ]
        assert len(stop_commands) >= 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_slow_drive_starts_ttl_after_transport_acknowledgement() -> None:
    transport = MemoryFactoryTransport()
    transport.nonzero_delay_s = 0.12
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())
    await adapter.start()
    transport.commands.clear()

    try:
        await adapter.drive(0.04, 0.0, 0.0, ttl_ms=100)
        await asyncio.sleep(0.05)
        assert {"T": 1, "L": 0, "R": 0} not in transport.commands

        await asyncio.sleep(0.07)
        stop_commands = [
            command
            for command in transport.commands
            if command == {"T": 1, "L": 0, "R": 0}
        ]
        assert len(stop_commands) >= 2
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_ambiguous_drive_failure_triggers_redundant_stop() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())
    await adapter.start()
    transport.commands.clear()
    transport.fail_nonzero_once = True

    try:
        with pytest.raises(ConnectionResetError):
            await adapter.drive(0.05, 0.0, 0.0)
        assert transport.commands[0] == {"T": 1, "L": 0.05, "R": 0.05}
        assert transport.commands[1:3] == [
            {"T": 1, "L": 0, "R": 0},
            {"T": 1, "L": 0, "R": 0},
        ]
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_factory_http_rejects_automatic_bounded_motion() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(transport, adapter_config())
    goal = BoundedMotionGoal(
        motion_id="motion-1",
        kind="linear",
        distance_m=0.2,
        angle_rad=None,
        max_linear_speed_mps=0.05,
        max_angular_speed_rad_s=0.2,
        max_duration_ms=2000,
    )

    with pytest.raises(
        BoundedMotionExecutionError,
        match="factory_http_manual_control_only",
    ):
        await adapter.execute_bounded_motion(goal)
    assert transport.commands == []


@pytest.mark.asyncio
async def test_feedback_becomes_disconnected_when_stale() -> None:
    transport = MemoryFactoryTransport()
    adapter = FactoryHttpRoverAdapter(
        transport,
        adapter_config(poll_interval_s=10.0, feedback_stale_after_s=0.01),
    )
    await adapter.start()
    try:
        await asyncio.sleep(0.02)
        state = await adapter.state()
        assert state.connected is False
        assert state.pose_quality.confidence == 0.0
        assert "factory_http_feedback_stale" in state.pose_quality.anomalies
    finally:
        await adapter.close()


@pytest.mark.asyncio
async def test_urllib_transport_resolves_socket_thread_before_propagating_cancel(
    monkeypatch,
) -> None:
    request_started = threading.Event()
    release_request = threading.Event()
    transport = UrllibFactoryHttpTransport("127.0.0.1")

    def delayed_request(command: dict[str, Any], allow_empty_response: bool):
        del command, allow_empty_response
        request_started.set()
        release_request.wait(timeout=1.0)
        return None

    monkeypatch.setattr(transport, "_send_sync", delayed_request)
    send_task = asyncio.create_task(
        transport.send({"T": 1, "L": 0.05, "R": 0.05}, allow_empty_response=True)
    )
    assert await asyncio.to_thread(request_started.wait, 1.0)

    send_task.cancel()
    await asyncio.sleep(0)
    assert send_task.done() is False
    release_request.set()
    with pytest.raises(asyncio.CancelledError):
        await send_task
