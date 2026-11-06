import test from 'node:test';
import assert from 'node:assert/strict';
import { myService } from '../pwa/src/missions/myService.ts';
import { runFakeService, type ServiceInputs } from './service-host.ts';
const inputs = (decline = false): ServiceInputs => ({
  recoveryClearance: true, operatorPresent: () => true,
  waitForPerson: async () => {}, say: () => {},
  prompt: async q => ({ value: decline && q.choices.includes('No') ? 'No' : q.choices[0], humanClear: q.stationary }),
});
const opts = { skip: !process.env.APRIS_PYTHON, timeout: 8000 };
test('unchanged student service runs through consolidated host and closes run', opts, async () => {
  const report = await runFakeService(myService, inputs());
  assert.equal(report.closed, true); assert.equal(report.snapshot?.session, null);
  assert.equal(report.snapshot?.moving, false);
  assert.ok(report.messages.some(m => m.includes('Please take your belongings')));
});
test('decline branch never asks for loading or following', opts, async () => {
  const seen: string[] = []; const source = inputs(true); const prompt = source.prompt;
  source.prompt = async (q, signal) => { seen.push(q.message); return prompt(q, signal); };
  const report = await runFakeService(myService, source);
  assert.equal(seen.length, 1); assert.ok(report.messages.some(m => m.includes('No problem')));
});
test('human clearance is separate from the service answer; guard survives failure', opts, async () => {
  const source = inputs(); source.prompt = async q => ({ value: q.choices[0] });
  await assert.rejects(runFakeService(myService, source), (error: any) => {
    assert.match(error.message, /human-clearance/); assert.ok(error.report.snapshot.guard);
    assert.equal(error.report.snapshot.moving, false); assert.equal(error.report.closed, true); return true;
  });
});
test('throwing service and unresponsive prompt are bounded and close the run', opts, async () => {
  await assert.rejects(runFakeService({ title: 'fail', run: async () => { throw new Error('student-error'); } }, inputs()), /student-error/);
  const source = inputs(); source.prompt = () => new Promise(() => {});
  await assert.rejects(runFakeService(myService, source, { serviceMs: 400 }), /service-timeout/);
});
test('missing Python executable cleans up without waiting for an exit event', { timeout: 3000 }, async () => {
  await assert.rejects(runFakeService(myService, inputs(), { python: '/missing/apris-python' }), /ENOENT/);
});
test('missing stop evidence never reports service completion', opts, async () => {
  await assert.rejects(runFakeService(myService, inputs(), { evidenceDelay: 'missing' }), /stop-unconfirmed|revoked/);
});

test('operator disappearance stops a waiting service independently of runner health', opts, async () => {
  const source = inputs(); let present = true;
  source.operatorPresent = () => present;
  source.prompt = async () => { present = false; return new Promise(() => {}); };
  await assert.rejects(runFakeService(myService, source), /operator-lease-expired|revoked/);
});
test('external cancellation aborts a noncooperative provider and closes the child', opts, async () => {
  const controller = new AbortController(); const source = inputs();
  source.waitForPerson = async () => { controller.abort(new Error('operator-cancelled')); return new Promise(() => {}); };
  await assert.rejects(runFakeService(myService, source, { signal: controller.signal }), (e: any) => {
    assert.match(e.message, /operator-cancelled/); assert.equal(e.report.closed, true); return true;
  });
});
