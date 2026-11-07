import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';
import { harness, until } from './console-test-harness.ts';
import { runConsoleService } from './console-connection.ts';
import { registeredDelivery } from '../pwa/src/missions/registeredDelivery.ts';
const opts = { skip: !process.env.APRIS_PYTHON, timeout: 40000 };
for (const interrupt of [false, true]) test(`registered delivery: ${interrupt ? 'interruption never reports arrival' : 'arrival precedes guarded receipt'}`, opts, async () => {
  const h = await harness(true, 'registered-delivery');
  const controller = new AbortController();
  let task: Promise<unknown> | undefined;
  try {
    const viewId = (await h.rpc.http('service/view', {})).viewId;
    if (interrupt) {
      task = runConsoleService(registeredDelivery, h.token, { origin: h.origin, signal: controller.signal, serviceMs: 35000 });
      void task.catch(() => {});
    } else {
      const state = await h.rpc.http('state');
      await h.rpc.http('service/launch', { controlEpoch: state.controlEpoch, operatorId: h.operatorId });
    }
    const answer = async (s: any) => {
      await h.rpc.http('service/answer', { viewId, runEpoch: s.runEpoch, questionId: s.prompt.id, value: s.prompt.choices[0] });
      await h.control('clearHandover', { operatorId: h.operatorId, guardId: s.guardId, confirmed: true });
    };
    const loading = await until(() => h.rpc.http('service/state'), s => !!s.prompt);
    await answer(loading);
    const moving = await until(() => h.rpc.http('state'), s => s.route?.status === 'running');
    await assert.rejects(h.rpc.http('service/route/start', { controlEpoch: moving.controlEpoch,
      runId: 'old', runEpoch: moving.session, requestId: 'stale-test', method: 'place', targetId: 'desk' }), /stale-run/);
    assert.ok(!(await h.rpc.http('service/state')).messages.some((s: string) => s.includes('到着')));
    if (interrupt) {
      controller.abort(new Error('service-cancelled'));
      await assert.rejects(task!, /cancel|cleanup|revoked/);
      const stopped = await until(() => h.rpc.http('state'), s => s.route.status !== 'running');
      assert.notEqual(stopped.route.status, 'completed');
      assert.equal(stopped.state.velocity.vx, 0);
      assert.ok(!(await h.rpc.http('service/state')).messages.some((s: string) => s.includes('到着')));
    } else {
      let receipt: any;
      const deadline = Date.now() + 30000;
      while (Date.now() < deadline) {
        const s = await h.rpc.http('service/state');
        if (s.prompt?.id !== loading.prompt.id && s.prompt) { receipt = s; break; }
        await delay(50);
      }
      assert.ok(receipt, 'receipt is published after arrival');
      const arrived = await h.rpc.http('state');
      assert.equal(arrived.route.status, 'completed');
      assert.equal(arrived.state.velocity.vx, 0);
      assert.ok(receipt.guardId);
      assert.ok(receipt.messages.some((s: string) => s.includes('到着')));
      await answer(receipt);
      await until(() => h.rpc.http('state'), s => !s.serviceProcess.active);
      assert.equal((await h.rpc.http('service/state')).result.status, 'completed');
    }
    const trace = await h.rpc.http('trace');
    assert.equal(trace.purpose, 'diagnostic-only');
    assert.equal(trace.complete, true);
    const events = trace.entries;
    const start = events.find((e: any) => e.kind === 'routeStarted');
    const terminal = events.find((e: any) => e.kind === 'routeTerminal');
    const finished = events.find((e: any) => e.kind === 'serviceFinished');
    assert.ok(start && terminal && finished);
    assert.equal(start.context.runEpoch, finished.context.runEpoch);
    assert.equal(terminal.context.runEpoch, start.context.runEpoch);
    assert.equal(terminal.context.route.id, start.context.route.id);
    assert.ok(start.context.localization.mapPose);
    assert.ok(events.some((e: any) => e.kind === 'routeAction'));
    if (interrupt) {
      assert.ok(events.some((e: any) => e.kind === 'revoked' && e.context.runEpoch === start.context.runEpoch));
      assert.notEqual(terminal.detail.status, 'completed');
    } else {
      const consumed = events.filter((e: any) => e.kind === 'serviceConsumed');
      assert.equal(consumed.length, 2);
      assert.ok(consumed[0].cursor < start.cursor);
      assert.ok(terminal.cursor < consumed[1].cursor);
      assert.ok(events.some((e: any) => e.kind === 'localizationSample'));
    }
  } finally {
    controller.abort(); await task?.catch(() => {});
    const s = await h.rpc.http('state');
    if (s.serviceProcess?.active) await h.rpc.http('service/stop', { controlEpoch: s.controlEpoch, launchId: s.serviceProcess.id });
    await h.close();
  }
});
for (const localization of [false, true]) test(`guidance rejects ${localization ? 'unregistered destination' : 'unavailable localization'} without arrival`, opts, async () => {
  const h = await harness(localization);
  try {
    await assert.rejects(runConsoleService({ title: 'unsupported destination', run: async api => {
      await api.guideTo(localization ? 'kitchen' : 'desk');
      api.say('arrived');
    } }, h.token, { origin: h.origin }), localization ? /unknown-destination/ : /routes-unavailable/);
    const s = await h.rpc.http('state');
    assert.equal(s.session, null);
    assert.equal(s.state.velocity.vx, 0);
    assert.ok(!(await h.rpc.http('service/state')).messages.includes('arrived'));
  } finally { await h.close(); }
});
