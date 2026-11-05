import test, { type TestContext } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
function harness(t: TestContext) {
  const child = spawn(process.execPath, [fileURLToPath(new URL('./process-experiment.ts', import.meta.url))], { stdio: ['pipe', 'pipe', 'pipe'] });
  const messages: any[] = []; let stderr = ''; let serial = 0;
  const waiters = new Set<() => void>();
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.stderr.on('data', c => { stderr += c; });
  const lines = createInterface({ input: child.stdout });
  lines.on('line', line => { messages.push(JSON.parse(line)); for (const notify of [...waiters]) notify(); });
  t.after(async () => {
    child.stdin.end();
    const timeout = setTimeout(() => child.kill('SIGKILL'), 3000);
    await exited; clearTimeout(timeout); lines.close();
  });
  const wait = (predicate: (m: any) => boolean): Promise<any> => new Promise((resolve, reject) => {
    const timer = setTimeout(() => { waiters.delete(check); reject(new Error('message timeout: ' + stderr + '; ' + JSON.stringify(messages))); }, 4000);
    function check() {
      const index = messages.findIndex(predicate);
      if (index < 0) return;
      clearTimeout(timer); waiters.delete(check); resolve(messages.splice(index, 1)[0]);
    }
    waiters.add(check); check();
  });
  const command = async (type: string, data: object = {}) => {
    const id = ++serial; child.stdin.write(JSON.stringify({ id, type, ...data }) + '\n');
    return wait(m => m.id === id);
  };
  const event = (name: string) => wait(m => m.event === name);
  const answer = (p: any, value: string, clearToMove = false) => command('answer', { promptId: p.id, session: p.session, answer: value, clearToMove });
  return { command, event, answer };
}
async function follow(t: TestContext) {
  const h = harness(t); const start = await h.command('start'); assert.equal(start.ok, true);
  assert.notEqual(start.value.runnerPid, start.value.gatewayPid);
  const help = await h.event('prompt'); assert.equal((await h.answer(help, 'Yes')).ok, true);
  const loading = await h.event('prompt');
  assert.equal((await h.answer(loading, 'Items are loaded', true)).ok, true);
  const arrival = await h.event('prompt');
  return { ...h, arrival };
}
test('unchanged myService completes across process boundary; loading requires clearance', { timeout: 8000 }, async t => {
  const h = harness(t); assert.equal((await h.command('start')).ok, true);
  const help = await h.event('prompt'); await h.answer(help, 'Yes');
  const loading = await h.event('prompt');
  assert.equal((await h.answer(loading, 'Items are loaded')).ok, false);
  assert.ok((await h.command('snapshot')).value.guard);
  await h.answer(loading, 'Items are loaded', true);
  const arrival = await h.event('prompt'); await h.answer(arrival, 'We have arrived');
  assert.equal((await h.event('service-result')).status, 'completed');
  await h.event('worker-exited');
  const state = (await h.command('snapshot')).value;
  assert.equal(state.moving, false); assert.equal(state.session, undefined);
  assert.equal((await h.answer(arrival, 'We have arrived')).ok, false);
});
test('existing decline branch completes without starting follow', { timeout: 8000 }, async t => {
  const h = harness(t); await h.command('start'); const p = await h.event('prompt');
  await h.answer(p, 'No'); assert.equal((await h.event('service-result')).status, 'completed');
  await h.event('worker-exited'); assert.equal((await h.command('snapshot')).value.moving, false);
});
for (const mode of ['kill', 'block', 'disconnect']) {
  test('separate gateway invalidates motion after runner ' + mode + ', including during pause', { timeout: 8000 }, async t => {
    const h = await follow(t); await h.command('pause'); await h.command('fault', { mode });
    let terminal = await h.event('terminal');
    if (terminal.status === 'completed') terminal = await h.event('terminal');
    assert.equal(terminal.status, 'interrupted');
    const state = (await h.command('snapshot')).value;
    assert.equal(state.moving, false); assert.equal(state.session, undefined);
    assert.equal(state.paused, true);
    assert.equal((await h.answer(h.arrival, 'We have arrived')).ok, false);
  });
}
test('missing stop evidence never reports arrival and inhibits another start', { timeout: 8000 }, async t => {
  const h = await follow(t); await h.command('fault', { mode: 'missing-evidence' });
  await h.answer(h.arrival, 'We have arrived');
  const result = await h.event('service-result'); assert.equal(result.status, 'failed');
  assert.match(result.reason, /stop-unconfirmed/);
  await h.event('worker-exited');
  assert.equal((await h.command('snapshot')).value.inhibited, true);
  assert.equal((await h.command('start')).ok, false);
  await h.command('fault', { mode: 'normal-evidence' });
  assert.equal((await h.command('recover', { confirmed: true })).ok, true);
  assert.equal((await h.command('start')).ok, true);
});
test('delayed stop evidence completes while paused without virtual step', { timeout: 8000 }, async t => {
  const h = await follow(t); await h.command('pause');
  await h.command('fault', { mode: 'delayed-evidence' }); await h.answer(h.arrival, 'We have arrived');
  assert.equal((await h.event('service-result')).status, 'completed');
  assert.equal((await h.command('snapshot')).value.moving, false);
});
