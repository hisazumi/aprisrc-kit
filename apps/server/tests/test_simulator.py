import asyncio
import math

import pytest

from apris_server.simulator import DifferentialDriveSimulator, SimulatorConfig, SimulatorFaults


@pytest.mark.asyncio
async def test_simulator_moves_forward_and_stops() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=100.0))
    await simulator.start()
    try:
        await simulator.drive(vx=1.0, vy=0.0, wz=0.0)
        await asyncio.sleep(0.08)
        moving = await simulator.state()
        assert moving.pose.x > 0.04
        assert moving.pose.y == pytest.approx(0.0, abs=1e-3)

        await simulator.stop()
        stopped_x = (await simulator.state()).pose.x
        await asyncio.sleep(0.05)
        assert (await simulator.state()).pose.x == pytest.approx(stopped_x, abs=2e-3)
    finally:
        await simulator.close()


@pytest.mark.asyncio
async def test_simulator_rejects_lateral_velocity() -> None:
    simulator = DifferentialDriveSimulator()
    await simulator.start()
    try:
        with pytest.raises(ValueError):
            await simulator.drive(vx=0.0, vy=0.1, wz=0.0)
    finally:
        await simulator.close()


@pytest.mark.asyncio
async def test_simulator_faults_are_deterministic_and_clearable() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    await simulator.start()
    try:
        await simulator.set_faults(
            SimulatorFaults(
                drop_next_commands=1,
                pose_noise_m=0.03,
                yaw_noise_deg=2.0,
                battery_percent=12.0,
                seed=42,
            )
        )
        await simulator.drive(vx=0.2, vy=0.0, wz=0.0)
        assert (await simulator.state()).velocity.vx == 0.0
        assert (await simulator.faults()).drop_next_commands == 0

        await simulator.drive(vx=0.2, vy=0.0, wz=0.0)
        await asyncio.sleep(0.06)
        faulted = await simulator.state()
        assert faulted.velocity.vx == pytest.approx(0.2)
        assert faulted.battery_percent == 12.0
        assert math.hypot(faulted.pose.x, faulted.pose.y) > 0.01

        await simulator.clear_faults()
        cleared = await simulator.state()
        assert cleared.battery_percent is not None
        assert cleared.battery_percent > 99.0
        assert (await simulator.faults()) == SimulatorFaults()
    finally:
        await simulator.close()


@pytest.mark.asyncio
async def test_simulator_can_return_stale_state() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    await simulator.start()
    try:
        await simulator.drive(vx=0.3, vy=0.0, wz=0.0)
        await asyncio.sleep(0.15)
        await simulator.set_faults(SimulatorFaults(stale_state_ms=100))
        stale = await simulator.state()
        await simulator.clear_faults()
        current = await simulator.state()

        assert current.pose.x - stale.pose.x > 0.015
        assert current.timestamp > stale.timestamp
    finally:
        await simulator.close()


@pytest.mark.asyncio
async def test_simulator_exposes_encoder_and_imu_quality_and_faults() -> None:
    simulator = DifferentialDriveSimulator(SimulatorConfig(update_hz=200.0))
    await simulator.start()
    try:
        await asyncio.sleep(0.03)
        nominal = await simulator.state()
        assert nominal.pose_quality.source == "encoder_imu"
        assert nominal.pose_quality.anomalies == []

        await simulator.set_faults(SimulatorFaults(encoder_fault=True, imu_fault=True))
        await asyncio.sleep(0.03)
        faulted = await simulator.state()
        assert faulted.pose_quality.source == "unavailable"
        assert faulted.pose_quality.anomalies == ["encoder_fault", "imu_fault"]
    finally:
        await simulator.close()
