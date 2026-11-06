import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { ConsoleConnection, runConsoleService } from './console-connection.ts';
import { myService } from '../pwa/src/missions/myService.ts';
const opts = { skip: !process.env.APRIS_PYTHON, timeout: 12000 };
async function harness() {
  const token = randomUUID();
  const child = spawn(process.env.APRIS_PYTHON!, ['-c', 'import sys,uvicorn; from apris_server.operator_console import create_console; uvicorn.run(create_console(sys.argv[1]),host="127.0.0.1",port=8766,access_log=False)', token], {
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) }, stdio: ['ignore', 'ignore', 'pipe'],
  });
  let stderr = ''; child.stderr.on('data', b => { stderr = (stderr + b).slice(-2000); });
  let launchError: unknown; child.on('error', e => { launchError = e; });
  const closed = new Promise<void>(resolve => child.once('close', () => resolve()));
  const rpc = new ConsoleConnection(token);
  const cleanup = async () => { rpc.close(); child.kill(); const timer = setTimeout(() => child.kill('SIGKILL'), 800); try { await closed; } finally { clearTimeout(timer); } };
  let state: any;
  try {
    const until = Date.now() + 3000;
    while (Date.now() < until) {
      if (launchError || child.exitCode !== null) throw new Error('server-start: ' + stderr + launchError);
      try { state = await rpc.http('state'); break; } catch { await delay(40); }
    }
    assert.ok(state, 'console startup timed out');
    const control = (kind: string, fields: object = {}) => rpc.http('control', {
      protocolVersion: 1, connectionEpoch: state.controlEpoch, requestId: randomUUID(), robotId: 'fake-only', kind, ...fields,
    });
    const operatorId = (await control('openOperator')).operatorId;
    await control('recover', { operatorId, guardId: null, confirmed: true });
    await rpc.http('front', { clear: true });
    let sequence = 0, renewing = false, stopped = false;
    const timer = setInterval(() => {
      if (renewing || stopped) return; renewing = true;
      void (async () => { await control('operatorHeartbeat', { operatorId, sequence: ++sequence }); await rpc.http('front', { clear: true }); })().catch(() => {}).finally(() => { renewing = false; });
    }, 50);
    return { token, rpc, control, operatorId, stopOperator: () => { stopped = true; clearInterval(timer); },
      close: async () => { stopped = true; clearInterval(timer); await cleanup(); } };
  } catch (e) { await cleanup(); throw e; }
}
async function until<T>(get: () => Promise<T>, accept: (v: T) => boolean): Promise<T> {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) { const v = await get(); if (accept(v)) return v; await delay(25); }
  throw new Error('condition timeout');
}
test('attached student service: reconnect rejects old page, separate clearance, same runtime survives', opts, async () => {
  const h = await harness(); let task: Promise<any> | undefined;
  try {
    let view = (await h.rpc.http('service/view', {})).viewId;
    task = runConsoleService(myService, h.token, { serviceMs: 7000 }); void task.catch(() => {});
    let last = ''; let checkedGuard = false; let checkedReload = false;
    let done = false; task.then(() => { done = true; }, () => { done = true; });
    const deadline = Date.now() + 6500;
    while (!done && Date.now() < deadline) {
      const s = await h.rpc.http('service/state');
      if (s.prompt && s.prompt.id !== last) {
        last = s.prompt.id;
        if (s.prompt.message.includes('デモ：')) {
          await delay(1800);
          const stopped = await h.rpc.http('state');
          assert.ok(stopped.session); assert.equal(stopped.operation, null);
          assert.equal(stopped.state.velocity.vx, 0);
          await delay(100);
          assert.deepEqual((await h.rpc.http('state')).state.pose, stopped.state.pose);
        }
        const answer = { viewId: view, runEpoch: s.runEpoch, questionId: s.prompt.id, value: s.prompt.choices[0] };
        if (!checkedReload) {
          view = (await h.rpc.http('service/view', {})).viewId;
          await assert.rejects(h.rpc.http('service/answer', answer), /stale/);
          checkedReload = true;
        }
        await h.rpc.http('service/answer', { ...answer, viewId: view });
        await assert.rejects(h.rpc.http('service/answer', { ...answer, viewId: view }), /stale/);
        if (s.prompt.stationary) {
          const pending = await h.rpc.http('service/state');
          assert.ok(pending.guardId); assert.ok(pending.answered);
          await assert.rejects(h.rpc.http('service/consume', { runEpoch: s.runEpoch, questionId: s.prompt.id }), /not-ready/);
          await h.control('clearHandover', { operatorId: h.operatorId, guardId: pending.guardId, confirmed: true });
          checkedGuard = true;
        }
      }
      await delay(20);
    }
    const report = await task;
    assert.ok(checkedReload && checkedGuard); assert.equal(report.closed, true);
    const final = await h.rpc.http('state');
    assert.equal((await h.rpc.http('service/state')).result.status, 'completed');
    assert.equal(final.session, null); assert.equal(final.state.velocity.vx, 0);
    assert.ok(final.state.pose.x > .02);
    assert.ok((await h.rpc.http('service/state')).messages.some((s: string) => s.includes('belongings')));
  } finally { h.stopOperator(); if (task) await task.catch(() => {}); await h.close(); }
});
test('operator lease expires during handover even while attached Node and service page remain alive', opts, async () => {
  const h = await harness(); let task: Promise<any> | undefined;
  try {
    task = runConsoleService({ title: 'handover', run: async api => { await api.confirm('Load'); } }, h.token, { serviceMs: 5000 });
    void task.catch(() => {});
    const s = await until(() => h.rpc.http('service/state'), s => !!s.prompt);
    assert.ok(s.guardId);
    h.stopOperator();
    await assert.rejects(task, /revoked|lease|service-ended/);
    const state = await h.rpc.http('state');
    assert.ok(state.guard); assert.ok(state.inhibited); assert.equal(state.session, null);
    assert.equal(state.state.velocity.vx, 0);
  } finally { if (task) await task.catch(() => {}); await h.close(); }
});

test('killed attached Node loses its run while operator stays present and guard survives', opts, async () => {
  const h = await harness(); let host: ReturnType<typeof spawn> | undefined;
  try {
    const moduleUrl = new URL('./console-connection.ts', import.meta.url).href;
    host = spawn(process.execPath, ['--input-type=module', '-e',
      `import {runConsoleService} from ${JSON.stringify(moduleUrl)}; await runConsoleService({title:'hold',run:async api=>{await api.confirm('Load')}},process.env.APRIS_CONSOLE_TOKEN);`],
      { env: { ...process.env, APRIS_CONSOLE_TOKEN: h.token }, stdio: ['ignore', 'ignore', 'pipe'] });
    host.stderr?.resume();
    const exited = new Promise<void>(resolve => host!.once('close', () => resolve()));
    await until(() => h.rpc.http('service/state'), s => !!s.prompt);
    host.kill('SIGKILL'); await exited;
    const state = await until(() => h.rpc.http('state'), s => s.session === null);
    assert.equal(state.control.operatorId, h.operatorId);
    assert.ok(state.guard); assert.equal(state.state.velocity.vx, 0);
    await assert.rejects(runConsoleService(myService, h.token), /operator-must-recover/);
  } finally { host?.kill('SIGKILL'); await h.close(); }
});

test('HTTP late-renew error delivers preceding terminal first; event gaps fail closed', async () => {
  const rpc = new ConsoleConnection('test');
  const terminal = { kind: 'terminal', operationId: 'old-op', generation: 1 };
  const order: string[] = [];
  rpc.onEvent(e => { order.push(String(e.kind)); });
  rpc.http = async (path: string) => {
    if (path === 'motion') throw new Error('stale-motion');
    return { eventCursor: 1, eventLog: [{ cursor: 1, event: terminal }] };
  };
  try {
    await assert.rejects(rpc.request('motion', { message: {} }).catch(e => { order.push('error'); throw e; }), /stale-motion/);
    assert.deepEqual(order, ['terminal', 'error']);
    rpc.http = async (path: string) => {
      if (path === 'motion') throw new Error('stale-motion');
      return { eventCursor: 130, eventLog: [{ cursor: 3, event: terminal }] };
    };
    await assert.rejects(rpc.request('motion', { message: {} }), /event-gap/);
  } finally { rpc.close(); }
});
