import asyncio

import pytest
from test_motion_contract import start, wire

from apris_server.runner_port_experiment import RunnerPort


async def run_goal(port, events, session, goal, *, cancel=False, renew=True):
    command = dict(start(session), goal=goal)
    accepted = await wire(port, session, command)
    assert accepted['kind'] == 'accepted'
    scope = {k: v for k, v in command.items() if k != 'goal'}
    async with asyncio.timeout(3):
        for seq in range(100):
            await asyncio.sleep(0.04)
            terminal = next((e for e in events if e['kind'] == 'terminal'), None)
            if terminal:
                return terminal
            if renew:
                await port.request(dict(action='heartbeat', session=session))
                await port.request(dict(action='fixture', front='CLEAR'))
                await wire(port, session, dict(scope, kind='renewMotion',
                    requestId=f'renew-{seq}', generation=accepted['generation']))
            if cancel and seq == 3:
                await wire(port, session, dict(scope, kind='cancelMotion',
                    requestId='cancel', generation=accepted['generation']))
    raise AssertionError('missing terminal')


@pytest.mark.asyncio
@pytest.mark.parametrize('goal,axis,expected,tolerance', [
    (dict(kind='move', distanceM=.04, speedMps=.1), 'x', .04, .016),
    (dict(kind='move', distanceM=-.04, speedMps=.1), 'x', -.04, .016),
    (dict(kind='turn', angleRad=.10, speedRadS=.7), 'yaw', .10, .027),
    (dict(kind='turn', angleRad=-.10, speedRadS=.7), 'yaw', -.10, .027),
])
async def test_goal_changes_odometry_and_stays_stopped(goal, axis, expected, tolerance):
    events = []
    port = RunnerPort(events.append, backend='simulator')
    await port.start()
    try:
        await port.request(dict(action='fixture', front='CLEAR'))
        session = await port.request(dict(action='admit'))
        result = await run_goal(port, events, session, goal)
        assert result['outcome'] == 'completed'
        assert result['evidence']['kind'] == 'simulated'
        state = await port.adapter.state()
        assert getattr(state.pose, axis) == pytest.approx(expected, abs=tolerance)
        assert abs(getattr(state.pose, axis)) > abs(expected) / 2
        assert state.velocity.vx == state.velocity.wz == 0
        assert state.pose_quality.age_ms < 100
        await asyncio.sleep(.08)
        later = await port.adapter.state()
        assert later.pose == state.pose
        assert not port.adapter.actuating
        assert (await port.request(dict(action='snapshot')))['backend'] == 'simulator'
    finally:
        await port.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel,renew,outcome', [(True, True, 'cancelled'),
                                                  (False, False, 'interrupted')])
async def test_cancel_or_ttl_stops_before_goal(cancel, renew, outcome):
    events = []
    port = RunnerPort(events.append, backend='simulator')
    await port.start()
    try:
        await port.request(dict(action='fixture', front='CLEAR'))
        session = await port.request(dict(action='admit'))
        result = await run_goal(port, events, session,
            dict(kind='move', distanceM=.3, speedMps=.1), cancel=cancel, renew=renew)
        assert result['outcome'] == outcome
        state = await port.adapter.state()
        assert 0 < state.pose.x < .1
        assert state.velocity.vx == state.velocity.wz == 0
        await asyncio.sleep(.08)
        assert (await port.adapter.state()).pose == state.pose
    finally:
        await port.close()


@pytest.mark.asyncio
async def test_unknown_front_fails_without_motion_and_handover_blocks_manual_owner():
    from test_motion_interlock import manual

    events = []
    port = RunnerPort(events.append, backend='simulator')
    await port.start()
    try:
        session = await port.request(dict(action='admit'))
        # No synthetic CLEAR observation: forward motion must fail, not silently run.
        result = await run_goal(port, events, session,
                                dict(kind='move', distanceM=.04, speedMps=.1), renew=False)
        assert result['outcome'] == 'failed'
        assert (await port.adapter.state()).pose.x == 0
        await port.request(dict(action='hold', session=session))
        await port.request(dict(action='revoke'))
        if port.io_tasks:
            await asyncio.wait(port.io_tasks, timeout=.5)
        client, socket = await manual(port.runtime)
        await port.runtime.handle_text(client, '{"type":"drive","vx":-0.1,"wz":0,"seq":1}')
        assert any(m.get('code') == 'motion_inhibited' for m in socket.messages)
        await asyncio.sleep(.08)
        assert (await port.adapter.state()).pose.x == 0
    finally:
        await port.close()
