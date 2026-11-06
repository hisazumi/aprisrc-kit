import test from 'node:test';
import assert from 'node:assert/strict';
import { ActivityRunner, type MotionCapability } from './activity-runner.ts';
const goal = { kind: 'move' as const, distanceM: .1, speedMps: .1 };
function motion() {
  const stopped: string[] = [];
  const port: MotionCapability = { move(scope, _goal, signal) {
    return new Promise(resolve => signal.addEventListener('abort', () => {
      stopped.push(scope.activityId);
      resolve({ kind: 'terminal', protocolVersion: 1, connectionEpoch: scope.runEpoch, requestId: 'r', robotId: 'fake-only', runId: scope.runId, activityId: scope.activityId, operationId: 'op', generation: 1, outcome: 'cancelled', reason: 'cancelled', evidence: { kind: 'simulated', epoch: 'fake', observedAt: 0 } });
    }, { once: true }));
  } };
  return { port, stopped };
}

test('nested cancellation fences all descendants before cleanup and joins resources', async () => {
  const m = motion(); const r = new ActivityRunner('run', 'epoch', m.port);
  const child = r.activity(r.root); const grandchild = r.activity(child);
  const movement = r.move(grandchild, goal);
  let cleaned = false;
  r.subscribe(grandchild, () => { assert.throws(() => r.activity(child), /closed/); cleaned = true; });
  await r.cancel(child); await movement;
  assert.equal(cleaned, true); assert.deepEqual(m.stopped, [grandchild.activityId]);
  assert.throws(() => r.send(grandchild, { type: 'late' }), /closed/);
  assert.doesNotThrow(() => r.activity(r.root));
  await r.cancel(r.root);
});

test('nonmoving question cancellation does not cancel sibling movement', async () => {
  const m = motion(); const r = new ActivityRunner('run', 'epoch', m.port);
  const delivery = r.activity(r.root); const question = r.activity(r.root);
  const moving = r.move(delivery, goal); const prompt = r.prompt(question, ['yes', 'no']);
  const rejected = assert.rejects(prompt.result, /cancelled/);
  await r.cancel(question); await rejected;
  assert.deepEqual(m.stopped, []); assert.throws(() => r.answer(prompt.id, 'yes'), /stale/);
  await r.cancel(r.root); await moving;
});

test('mailboxes are directed FIFO, clone data and expose overflow', async () => {
  const r = new ActivityRunner('run', 'epoch', motion().port, { queueLimit: 2 });
  const seen: string[] = [];
  const a = r.activity(r.root, e => { seen.push('a:' + e.type); });
  const b = r.activity(r.root, e => { seen.push('b:' + e.type); });
  const event = { type: 'one' }; r.send(a, event); event.type = 'mutated';
  r.send(a, { type: 'two' }); r.send(b, { type: 'other' });
  assert.throws(() => r.send(a, { type: 'full' }), /queue-full/);
  r.dispatch(); assert.deepEqual(seen, ['a:one', 'b:other']);
  r.dispatch(); assert.deepEqual(seen, ['a:one', 'b:other', 'a:two']);
  await r.cancel(r.root);
});

test('cancellation removes prompts timers subscriptions and rejects late answers', async () => {
  const r = new ActivityRunner('run', 'epoch', motion().port);
  const prompt = r.prompt(r.root, ['yes']); assert.throws(() => r.answer(prompt.id, 'wrong'), /invalid-answer/);
  const rejection = assert.rejects(prompt.result, /cancelled/);
  let fired = false; let disposed = 0;
  r.after(r.root, 10, { type: 'timer' }); r.subscribe(r.root, () => { disposed++; });
  const child = r.activity(r.root, () => { fired = true; }); r.send(child, { type: 'queued' });
  await r.cancel(r.root); await rejection;
  r.dispatch(); assert.equal(fired, false); assert.equal(disposed, 1);
  assert.deepEqual(r.snapshot(), { activities: 0, prompts: 0, timers: 0, pending: 0, failure: null });
});

test('handler failure interrupts the run; asynchronous handlers are rejected', async () => {
  for (const handler of [() => { throw new Error('handler-failed'); }, async () => {}]) {
    const r = new ActivityRunner('run', 'epoch', motion().port);
    const a = r.activity(r.root, handler); r.send(a, { type: 'event' }); r.dispatch();
    await r.cancel(r.root);
    assert.ok(r.failure); assert.throws(() => r.activity(r.root), /closed/);
  }
});

test('uncooperative capability times out join without pretending stop confirmation', async () => {
  const r = new ActivityRunner('run', 'epoch', { move: () => new Promise(() => {}) }, { joinMs: 10 });
  void r.move(r.root, goal);
  await assert.rejects(r.cancel(r.root), /cleanup-timeout/);
  assert.equal(r.snapshot().pending, 1);
  assert.throws(() => r.move(r.root, goal), /closed/);
});

test('activity count is bounded and foreign scope cannot reuse an ID', async () => {
  const r = new ActivityRunner('run', 'epoch', motion().port, { activityLimit: 2 });
  r.activity(r.root); assert.throws(() => r.activity(r.root), /capacity/);
  assert.throws(() => r.send({ ...r.root, runEpoch: 'old' }, { type: 'late' }), /scope/);
  await r.cancel(r.root);
});

test('failed or unconfirmed backend cleanup is not a successful join', async () => {
  for (const uncertainty of ['reject', 'unknown']) {
    const r = new ActivityRunner('run', 'epoch', { move(scope, _goal, signal) {
      return new Promise((resolve, reject) => signal.addEventListener('abort', () => {
        if (uncertainty === 'reject') reject(new Error('transport-lost'));
        else resolve({ protocolVersion: 1, connectionEpoch: scope.runEpoch, requestId: 'r', robotId: 'fake-only', runId: scope.runId, activityId: scope.activityId, operationId: 'op', kind: 'terminal', generation: 1, outcome: 'stop-unconfirmed', reason: 'missing', evidence: { kind: 'unknown' } });
      }, { once: true }));
    } });
    const movement = r.move(r.root, goal); void movement.catch(() => {});
    await assert.rejects(r.cancel(r.root), /cleanup-failed/);
    assert.ok(r.failure);
  }
});
