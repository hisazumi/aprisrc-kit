import asyncio

import pytest

from apris_server.runner_port_experiment import RunnerPort


async def terminal(events):
    async with asyncio.timeout(2):
        while not any(e["kind"] == "terminal" for e in events):  # noqa: ASYNC110
            await asyncio.sleep(0.01)
    return next(e["event"] for e in events if e["kind"] == "terminal")


@pytest.mark.asyncio
async def test_runtime_rejects_forward_without_fresh_clear():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        session = await port.request({"action": "admit"})
        await port.request({"action": "move", "session": session, "duration": 0.05})
        result = await terminal(events)
        assert result["status"] == "failed"
        assert "front_obstacle" in result["reason"]
        assert not port.adapter.goals
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_runtime_preserves_control_and_estop_rejection():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        session = await port.request({"action": "admit"})
        await port.runtime.handle_text(port.client, '{"type":"estop"}')
        await port.request({"action": "move", "session": session, "duration": 0.05})
        result = await terminal(events)
        assert result["status"] == "failed"
        assert "emergency" in result["reason"]
        assert not port.adapter.goals
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_stale_token_cannot_cancel_new_motion_and_handover_survives_loss():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        await port.request({"action": "fixture", "front": "CLEAR"})
        old = await port.request({"action": "admit"})
        token = await port.request({"action": "move", "session": old, "duration": 0.05})
        await terminal(events)
        await port.request({"action": "revoke"})
        new = await port.request({"action": "admit"})
        current = await port.request({"action": "move", "session": new, "duration": 0.1})
        with pytest.raises(ValueError, match="revoked"):
            await port.request({"action": "stop", "session": new, "token": token})
        assert port.operation["token"] == current
        events.clear()
        await terminal(events)
        await port.request({"action": "hold", "session": new})
        await port.request({"action": "revoke"})
        with pytest.raises(ValueError, match="inhibited"):
            await port.request({"action": "admit"})
        await port.request({"action": "recover", "confirmed": True})
        assert await port.request({"action": "admit"})
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_missing_stop_evidence_latches_new_admission():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        await port.request({"action": "fixture", "front": "CLEAR", "evidenceDelay": "missing"})
        session = await port.request({"action": "admit"})
        await port.request({"action": "move", "session": session, "duration": 0.05})
        result = await terminal(events)
        assert result["status"] == "stop-unconfirmed"
        with pytest.raises(ValueError, match="inhibited"):
            await port.request({"action": "admit"})
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_arrival_pending_evidence_is_interrupted_on_revocation():
    events = []
    port = RunnerPort(events.append)
    await port.start()
    try:
        await port.request({"action": "fixture", "front": "CLEAR", "evidenceDelay": 0.1})
        session = await port.request({"action": "admit"})
        await port.request({"action": "move", "session": session, "duration": 0.02})
        async with asyncio.timeout(1):
            while not port.operation["finishing"]:  # noqa: ASYNC110
                await asyncio.sleep(0.005)
        await port.request({"action": "revoke"})
        result = await terminal(events)
        assert result["status"] == "interrupted"
    finally:
        await port.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("renew", [False, True])
async def test_heartbeat_cannot_extend_ttl_or_fixed_progress_deadline(renew):
    events = []
    port = RunnerPort(events.append)
    if renew:
        port.progress_s = 0.15
    await port.start()
    heartbeat = None
    try:
        await port.request({"action": "fixture", "front": "CLEAR"})
        session = await port.request({"action": "admit"})
        token = await port.request({"action": "move", "session": session, "duration": 0.8})

        async def pulse():
            while True:
                await asyncio.sleep(0.03)
                try:
                    await port.request(
                        {
                            "action": "heartbeat",
                            "session": session,
                            "token": token if renew else None,
                        }
                    )
                except ValueError:
                    return

        heartbeat = asyncio.create_task(pulse())
        result = await terminal(events)
        assert result["status"] == "interrupted"
        assert result["reason"] == ("progress-deadline" if renew else "command-ttl")
        assert not port.adapter.actuating
    finally:
        if heartbeat:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        await port.close()
