import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { createServer, type AddressInfo } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';
import { ConsoleConnection } from './console-connection.ts';
/** Isolated simulator-only harness. It never connects to the user's console. */
export async function harness() {
  if (!process.env.APRIS_PYTHON) throw new Error('APRIS_PYTHON is required');
  const listener = createServer();
  await new Promise<void>((resolve, reject) => { listener.once('error', reject); listener.listen(0, '127.0.0.1', resolve); });
  const port = (listener.address() as AddressInfo).port;
  await new Promise<void>((resolve, reject) => listener.close(error => error ? reject(error) : resolve()));
  const origin = `http://127.0.0.1:${port}`;
  const token = randomUUID();
  const child = spawn(process.env.APRIS_PYTHON!, ['-c', 'import sys,uvicorn; from apris_server.operator_console import create_console; uvicorn.run(create_console(sys.argv[1],origin="http://127.0.0.1:"+sys.argv[2]),host="127.0.0.1",port=int(sys.argv[2]),access_log=False)', token, String(port)], {
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) }, stdio: ['ignore', 'ignore', 'pipe'],
  });
  let stderr = ''; child.stderr.on('data', b => { stderr = (stderr + b).slice(-2000); });
  let launchError: unknown; child.on('error', e => { launchError = e; });
  const closed = new Promise<void>(resolve => child.once('close', () => resolve()));
  const rpc = new ConsoleConnection(token, origin);
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
    return { origin, token, rpc, control, operatorId, stopOperator: () => { stopped = true; clearInterval(timer); },
      close: async () => { stopped = true; clearInterval(timer); await cleanup(); } };
  } catch (e) { await cleanup(); throw e; }
}
export async function until<T>(get: () => Promise<T>, accept: (v: T) => boolean): Promise<T> {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) { const v = await get(); if (accept(v)) return v; await delay(25); }
  throw new Error('condition timeout');
}
