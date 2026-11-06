import test from 'node:test';
import assert from 'node:assert/strict';
import { parseMotionMessage, MotionClient, StartLedger, type MotionTransport } from './motion-contract.ts';

const scope = { protocolVersion: 1 as const, connectionEpoch: 'epoch-1', requestId: 'req-1', robotId: 'robot', runId: 'run', activityId: 'activity', operationId: 'op' };
const start = () => ({ ...scope, kind: 'startMotion' as const, goal: { kind: 'move' as const, distanceM: .4, speedMps: .1 } });
const accepted = () => ({ ...scope, kind: 'accepted' as const, generation: 1 });
const terminal = () => ({ ...scope, kind: 'terminal' as const, generation: 1, outcome: 'completed' as const, reason: 'goal-reached', evidence: { kind: 'simulated' as const, epoch: 'sim-1', observedAt: 2 } });

function harness(capacity = 8) {
  let receive: (value: unknown) => void = () => {};
  let disconnected: (reason: string) => void = () => {};
  const sent: unknown[] = [];
  let onSend = (_value: unknown) => {};
  const transport: MotionTransport = {
    send(value) { sent.push(value); onSend(value); },
    subscribe(message, close) { receive = message; disconnected = close; return () => {}; },
  };
  const client = new MotionClient(transport, 'epoch-1', capacity);
  return { client, sent, emit: (v: unknown) => receive(v), disconnect: () => disconnected('pipe-closed'), onSend: (f: typeof onSend) => { onSend = f; } };
}

test('strict SI move/turn parsing including limits', () => {
  assert.deepEqual(parseMotionMessage(start()), start());
  assert.doesNotThrow(() => parseMotionMessage({ ...start(), goal: { kind: 'turn', angleRad: Math.PI / 2, speedRadS: .7 } }));
  for (const distanceM of [0, 1e-12, NaN, Infinity, 5.01]) assert.throws(() => parseMotionMessage({ ...start(), goal: { ...start().goal, distanceM } }));
  for (const angleRad of [0, 1e-14, Infinity, 4 * Math.PI + .01]) assert.throws(() => parseMotionMessage({ ...start(), goal: { kind: 'turn', angleRad, speedRadS: .7 } }));
  for (const speedMps of [.049, .301, '0.1']) assert.throws(() => parseMotionMessage({ ...start(), goal: { ...start().goal, speedMps } }));
});

test('reject unknown fields, malformed IDs, versions and unsafe evidence claims', () => {
  for (const message of [{ ...start(), protocolVersion: 2 }, { ...start(), operationId: '' }, { ...start(), extra: true }, { ...start(), kind: 'drive' }, { ...accepted(), generation: 0 }, { ...terminal(), evidence: undefined }, { ...terminal(), outcome: 'stop-unconfirmed' }, { ...terminal(), evidence: { kind: 'physical', epoch: 'x', observedAt: NaN } }]) assert.throws(() => parseMotionMessage(message));
});

test('result handler exists before send, even for synchronous terminal-before-acceptance', async () => {
  const h = harness();
  h.onSend(() => { h.emit(terminal()); h.emit(accepted()); });
  const result = await h.client.start(start());
  assert.equal(result.kind, 'terminal');
  assert.equal(h.sent.length, 1);
});

test('running and duplicate terminal cannot replace the first terminal', async () => {
  const h = harness(); const result = h.client.start(start());
  h.emit(accepted()); h.emit({ ...accepted(), kind: 'running' }); h.emit(terminal());
  h.emit({ ...terminal(), outcome: 'interrupted', reason: 'late' });
  assert.equal((await result).reason, 'goal-reached');
});

test('old epoch, wrong scope and wrong generation cannot complete an operation', async () => {
  const h = harness(); let settled = false;
  const result = h.client.start(start()).then(v => { settled = true; return v; });
  h.emit(accepted());
  for (const change of [{ connectionEpoch: 'old' }, { runId: 'other' }, { activityId: 'other' }, { robotId: 'other' }, { requestId: 'other' }, { generation: 2 }]) h.emit({ ...terminal(), ...change });
  await Promise.resolve(); assert.equal(settled, false);
  h.emit(terminal()); await result;
});

test('rejected is a correlated result and requires no fabricated stop evidence', async () => {
  const h = harness(); const result = h.client.start(start());
  h.emit({ ...scope, kind: 'rejected', reason: 'front-unknown' });
  assert.equal((await result).kind, 'rejected');
});

test('disconnect rejects outstanding results as uncertain and forbids replay', async () => {
  const h = harness(); const result = h.client.start(start()); h.disconnect();
  await assert.rejects(result, /uncertain.*pipe-closed/);
  await assert.rejects(h.client.start(start()), /closed/);
  assert.equal(h.sent.length, 1);
});

test('send failure is uncertain and invalidates the connection', async () => {
  const h = harness(); h.onSend(() => { throw new Error('broken-pipe'); });
  await assert.rejects(h.client.start(start()), /uncertain.*broken-pipe/);
  await assert.rejects(h.client.start(start()), /closed/);
});

test('duplicate operation and capacity do not send additional starts', async () => {
  const h = harness(1); const first = h.client.start(start()); h.emit(terminal()); await first;
  await assert.rejects(h.client.start(start()), /duplicate/);
  await assert.rejects(h.client.start({ ...start(), operationId: 'next', requestId: 'next' }), /capacity/);
  assert.equal(h.sent.length, 1);
});

test('server start ledger returns the same generation on retry and rejects conflicting reuse', () => {
  const ledger = new StartLedger('epoch-1', 2);
  assert.deepEqual(ledger.admit(start()), { generation: 1, duplicate: false });
  assert.deepEqual(ledger.admit(start()), { generation: 1, duplicate: true });
  assert.throws(() => ledger.admit({ ...start(), goal: { ...start().goal, distanceM: .5 } }), /conflict/);
  assert.throws(() => ledger.admit({ ...start(), requestId: 'different' }), /conflict/);
  assert.throws(() => ledger.admit({ ...start(), operationId: 'different' }), /conflict/);
  assert.throws(() => ledger.admit({ ...start(), connectionEpoch: 'old' }), /epoch/);
});

test('ledger never evicts obligations, malformed input consumes no slot', () => {
  const ledger = new StartLedger('epoch-1', 1);
  assert.throws(() => ledger.admit({ ...start(), goal: { ...start().goal, distanceM: 0 } }));
  assert.equal(ledger.admit(start()).generation, 1);
  assert.throws(() => ledger.admit({ ...start(), requestId: 'two', operationId: 'two' }), /capacity/);
  assert.equal(ledger.admit(start()).duplicate, true);
});

test('stop uncertainty and failure-before-actuation have distinct evidence', () => {
  assert.doesNotThrow(() => parseMotionMessage({ ...terminal(), outcome: 'stop-unconfirmed', evidence: { kind: 'unknown' } }));
  assert.doesNotThrow(() => parseMotionMessage({ ...terminal(), outcome: 'failed', evidence: { kind: 'not-started' } }));
  assert.throws(() => parseMotionMessage({ ...terminal(), outcome: 'cancelled', evidence: { kind: 'not-started' } }));
  assert.throws(() => parseMotionMessage({ ...terminal(), outcome: 'failed', evidence: { kind: 'unknown' } }));
});

test('renew/cancel require full scope and a positive integer generation', () => {
  for (const kind of ['renewMotion', 'cancelMotion']) {
    assert.doesNotThrow(() => parseMotionMessage({ ...scope, kind, generation: 1 }));
    for (const generation of [undefined, -1, 1.5, Infinity]) assert.throws(() => parseMotionMessage({ ...scope, kind, generation }));
  }
});

test('malformed inbound message makes all pending operations uncertain', async () => {
  const h = harness(); const first = h.client.start(start());
  const second = h.client.start({ ...start(), requestId: 'two', operationId: 'two' });
  h.emit({ ...terminal(), evidence: { kind: 'unknown' } });
  await assert.rejects(first, /uncertain.*invalid-message/);
  await assert.rejects(second, /uncertain.*invalid-message/);
});

test('rejection after acceptance is a protocol error rather than a successful rejection', async () => {
  const h = harness(); const result = h.client.start(start()); h.emit(accepted());
  h.emit({ ...scope, kind: 'rejected', reason: 'contradiction' });
  await assert.rejects(result, /uncertain.*rejected-after-acceptance/);
});

test('canonical decoding detaches caller values and ledger ignores JSON key order', () => {
  const original = start(); const decoded = parseMotionMessage(original);
  original.goal.distanceM = 4;
  assert.equal(decoded.kind === 'startMotion' && decoded.goal.kind === 'move' && decoded.goal.distanceM, .4);
  const ledger = new StartLedger('epoch-1'); ledger.admit(start());
  const reordered = Object.fromEntries(Object.entries(start()).reverse());
  assert.equal(ledger.admit(reordered).duplicate, true);
});
