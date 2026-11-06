import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { parseControlMessage } from './control-contract.ts';
import { MotionClient, parseMotionMessage, type MotionTransport, type StartMotion } from './motion-contract.ts';

const fixtures = JSON.parse(readFileSync(new URL('./fixtures/motion-v1.json', import.meta.url), 'utf8'));
for (const fixture of fixtures) {
  test('shared wire fixture: ' + fixture.name, () => {
    if (fixture.valid) assert.deepEqual(parseMotionMessage(fixture.message), fixture.message);
    else assert.throws(() => parseMotionMessage(fixture.message));
  });
}

// Test-only harness for the existing trusted JSON-lines experiment; not a production transport.
for (const mode of ['complete', 'cancel', 'missing-evidence', 'control'] as const) {
  test('typed client to Python port: ' + mode, { skip: !process.env.APRIS_PYTHON, timeout: 6000 }, async () => {
    const child = spawn(process.env.APRIS_PYTHON!, ['-m', 'apris_server.runner_port_experiment'], {
      env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stderr = ''; child.stderr.on('data', b => { stderr = (stderr + b).slice(-4096); });
    const closed = new Promise<void>(resolve => child.once('close', () => resolve()));
    let id = 0;
    const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
    let receive = (_v: unknown) => {};
    let disconnect = (_reason: string) => {};
    const abort = (e: Error) => { for (const p of pending.values()) p.reject(e); pending.clear(); disconnect(e.message); };
    child.on('error', abort); child.stdin.on('error', abort);
    child.on('close', () => abort(new Error('port-closed: ' + stderr)));
    const lines = createInterface({ input: child.stdout });
    lines.on('line', line => {
      try {
        const m = JSON.parse(line);
        if (m.kind === 'reply') {
          const p = pending.get(m.id); if (!p) return;
          pending.delete(m.id);
          if (m.ok) p.resolve(m.value); else p.reject(new Error(m.error));
        } else if (m.protocolVersion === 1) receive(m);
      } catch (e) { abort(e as Error); }
    });
    const rpc = (action: string, data: object = {}) => new Promise<any>((resolve, reject) => {
      const key = ++id; pending.set(key, { resolve, reject });
      child.stdin.write(JSON.stringify({ id: key, action, ...data }) + '\n');
    });
    let heartbeat: ReturnType<typeof setInterval> | undefined;
    let client: MotionClient | undefined;
    try {
      await rpc('fixture', { front: 'CLEAR', ...(mode === 'missing-evidence' ? { evidenceDelay: 'missing' } : {}) });
      let session: string;
      let controlSequence = 0;
      if (mode === 'control') {
        const epoch = (await rpc('snapshot')).controlEpoch;
        const control = async (kind: string, fields: object = {}) => {
          const value = parseControlMessage(await rpc('control', { message: { protocolVersion: 1, connectionEpoch: epoch, requestId: 'c' + (++controlSequence), robotId: 'fake-only', kind, ...fields } }));
          if (value.kind !== 'controlReply') throw new Error('expected-control-reply');
          return value;
        };
        const operatorId = (await control('openOperator')).operatorId;
        await control('recover', { operatorId, guardId: null, confirmed: true });
        session = (await control('openRun', { operatorId, runId: 'run' })).runEpoch!;
        let sequence = 0;
        heartbeat = setInterval(() => {
          sequence++;
          void control('operatorHeartbeat', { operatorId, sequence }).catch(() => {});
          void control('runnerHeartbeat', { runId: 'run', runEpoch: session, sequence }).catch(() => {});
        }, 50);
        const held = await control('acquireHandover', { runId: 'run', runEpoch: session });
        assert.ok(held.guardId);
        await control('clearHandover', { operatorId, guardId: held.guardId, confirmed: true });
      } else {
        session = await rpc('admit');
        heartbeat = setInterval(() => { void rpc('heartbeat', { session }).catch(() => {}); }, 50);
      }
      const transport: MotionTransport = {
        send(m) { void rpc('motion', { session, message: m }).then(v => receive(v), e => disconnect(e.message)); },
        subscribe(message, close) { receive = message; disconnect = close; return () => { receive = () => {}; disconnect = () => {}; }; },
      };
      client = new MotionClient(transport, session);
      const command: StartMotion = { protocolVersion: 1, connectionEpoch: session, requestId: 'start', robotId: 'fake-only', runId: 'run', activityId: 'activity', operationId: 'op', kind: 'startMotion', goal: { kind: 'move', distanceM: mode === 'cancel' ? .04 : .005, speedMps: .1 } };
      const result = client.start(command);
      if (mode === 'cancel') {
        // Replay obtains the actual generation without scheduling another goal.
        const accepted = parseMotionMessage(await rpc('motion', { session, message: command }));
        assert.equal(accepted.kind, 'accepted');
        if (accepted.kind !== 'accepted') throw new Error('expected-acceptance');
        const { goal: _goal, ...scope } = command;
        const ack = parseMotionMessage(await rpc('motion', { session, message: { ...scope, kind: 'cancelMotion', requestId: 'cancel', generation: accepted.generation } }));
        assert.equal(ack.kind, 'commandAck');
      }
      const done = await result;
      assert.equal(done.kind, 'terminal');
      if (done.kind !== 'terminal') throw new Error('unexpected-rejection');
      assert.equal(done.outcome, (mode === 'complete' || mode === 'control') ? 'completed' : mode === 'cancel' ? 'cancelled' : 'stop-unconfirmed');
      assert.equal(done.evidence.kind, mode === 'missing-evidence' ? 'unknown' : 'simulated');
      const snapshot = await rpc('snapshot');
      assert.equal(snapshot.moving, false);
      if (mode === 'missing-evidence') assert.equal(snapshot.inhibited, true);
    } finally {
      clearInterval(heartbeat); client?.close(); child.stdin.end();
      const kill = setTimeout(() => child.kill('SIGKILL'), 700);
      try { await closed; } finally { clearTimeout(kill); lines.close(); }
    }
  });
}
