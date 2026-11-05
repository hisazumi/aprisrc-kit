import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { Runtime } from './runtime.ts';

test('concurrent activities receive ordered directed events while movement is pending', async () => {
  const r = new Runtime(); const root = r.start('delivery');
  const received: string[] = [];
  const orders = r.activity(root, e => received.push(e.type));
  const driver = r.activity(root, () => {});
  const movement = r.move(driver, 10);
  r.send(orders, { type: 'order-1' }); r.send(orders, { type: 'order-2' });
  r.step(1); r.step(1);
  assert.deepEqual(received, ['order-1', 'order-2']);
  assert.ok(r.motion.current(movement.token));
  r.step(8); assert.equal((await movement.result).status, 'completed');
});

test('cancel fences children and late events; old cleanup cannot stop new owner', async () => {
  const r = new Runtime(); const root = r.start('follow');
  const child = r.activity(root, () => assert.fail('cancelled event delivered'));
  const old = r.move(child, 100);
  r.send(child, { type: 'late' }); r.cancel(root);
  assert.equal((await old.result).status, 'cancelled');
  assert.throws(() => r.send(child, { type: 'late' }), /stale-scope/);
  assert.throws(() => r.move(child, 1), /stale-scope/);
  const next = r.move(r.start('route'), 10);
  assert.equal(r.motion.current(old.token), false);
  assert.equal(r.motion.stop(old.token), false);
  assert.ok(r.motion.current(next.token));
  r.globalStop(); assert.equal((await next.result).status, 'interrupted');
});

test('cancel question activity does not stop concurrent delivery', async () => {
  const r = new Runtime(); const root = r.start('delivery');
  const question = r.activity(root, () => {});
  const movement = r.move(root, 10); const id = r.prompt(question);
  r.cancel(question); assert.throws(() => r.answer(id), /stale-prompt/);
  assert.ok(r.motion.current(movement.token));
  r.step(10); await movement.result;
});

test('handover inhibits all runs, including after prompt cancellation', () => {
  const r = new Runtime(); const a = r.start('handover'); const b = r.start('other');
  const id = r.prompt(a, true);
  assert.throws(() => r.move(b, 1), /inhibited/);
  assert.throws(() => r.answer(id), /clearance/);
  r.cancel(a);
  assert.throws(() => r.answer(id, true), /stale-prompt/);
  assert.throws(() => r.move(b, 1), /inhibited/);
  // Explicit operator recovery in this in-process fake test.
  r.motion.clear(id);
  assert.ok(r.move(b, 1)); r.globalStop();
});

test('handover requires stationary entry and explicit clearance', async () => {
  const r = new Runtime(); const root = r.start('delivery');
  const movement = r.move(root, 1);
  assert.throws(() => r.prompt(root, true), /not-stationary/);
  r.step(1); await movement.result;
  const id = r.prompt(root, true); r.answer(id, true);
  assert.throws(() => r.answer(id, true), /stale-prompt/);
  assert.ok(r.move(root, 1)); r.globalStop();
});

test('pause freezes virtual progress; cancel/reset need no simulation step', async () => {
  const r = new Runtime(); const root = r.start('route'); const op = r.move(root, 1);
  r.paused = true; r.step(100); assert.equal(r.time, 0);
  r.cancel(root); assert.equal((await op.result).status, 'cancelled');
  const next = r.move(r.start('route'), 1);
  r.reset(); assert.equal((await next.result).status, 'interrupted');
  assert.equal(r.epoch, 1); assert.equal(r.motion.owner, undefined);
  assert.throws(() => r.move(root, 1), /stale-scope/);
  r.step(100); assert.equal(r.motion.owner, undefined);
});

test('duplicate admission and overflow reject visibly; stop bypasses full queue', () => {
  const r = new Runtime(); const root = r.start('service');
  assert.throws(() => r.start('service'), /duplicate/);
  const a = r.activity(root, () => {});
  for (let i = 0; i < r.queueLimit; i++) r.send(a, { type: 'job' });
  assert.throws(() => r.send(a, { type: 'job' }), /queue-full/);
  r.globalStop(); assert.equal(r.snapshot().activities, 0);
});

test('handler failure interrupts run and releases motion', async () => {
  const r = new Runtime(); const root = r.start('service');
  const a = r.activity(root, () => { throw new Error('service-failed'); });
  const op = r.move(a, 10); r.send(a, { type: 'fail' });
  assert.throws(() => r.dispatch(), /service-failed/);
  assert.equal((await op.result).status, 'interrupted');
});

test('browser-free child process accepts control during pause and exits on EOF', { timeout: 5000 }, async t => {
  const child = spawn(process.execPath, [new URL('./runner.ts', import.meta.url).pathname], {
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  t.after(() => child.kill());
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]();
  const next = async () => JSON.parse((await lines.next()).value!);
  const send = (v: unknown) => child.stdin.write(JSON.stringify(v) + '\n');
  send({ id: 1, type: 'start', service: 'test' }); const start = await next();
  assert.equal(start.ok, true);
  send({ id: 2, type: 'move', scope: start.value, duration: 10 }); assert.equal((await next()).ok, true);
  send({ id: 3, type: 'pause' }); await next();
  send({ id: 4, type: 'cancel', scope: start.value }); assert.equal((await next()).ok, true);
  const terminal = await next(); assert.equal(terminal.result.status, 'cancelled');
  send({ id: 5, type: 'snapshot' }); assert.equal((await next()).value.runs, 0);
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.stdin.end(); assert.equal(await exited, 0);
});
