import test from 'node:test';
import assert from 'node:assert/strict';
import { Gateway, limits, type Terminal } from './gateway-core.ts';
function fixture() {
  let time = 0; const gateway = new Gateway(() => time); const events: Terminal[] = [];
  gateway.terminal = event => events.push(event);
  return { gateway, events, advance: (dt: number) => { time += dt; gateway.tick(); } };
}
test('heartbeat alone cannot renew a motion command TTL', () => {
  const { gateway: g, advance, events } = fixture(); const s = g.admit(); const token = g.begin(s, 0.8);
  advance(0.15); g.heartbeat(s); advance(0.11);
  assert.equal(events[0].reason, 'command-ttl'); assert.equal(g.snapshot().moving, false);
  assert.throws(() => g.renew(token), /revoked/);
});
test('lease expires while paused even if command was renewed', () => {
  const { gateway: g, advance, events } = fixture(); const s = g.admit(); const token = g.begin(s, 0.8);
  g.setPause(true); advance(0.2); g.renew(token); advance(0.21);
  assert.equal(events[0].reason, 'lease-expired'); assert.equal(g.snapshot().paused, true);
});
test('heartbeat and command renewal cannot extend stalled operation progress budget', () => {
  const { gateway: g, advance, events } = fixture(); const s = g.admit(); const token = g.begin(s, 0.1);
  g.stalled = true;
  for (let i = 0; i < 9; i++) { advance(0.1); g.heartbeat(s); g.renew(token); }
  advance(0.11);
  assert.equal(events[0].reason, 'progress-deadline'); assert.equal(g.snapshot().session, undefined);
});
test('pause freezes progress but stop evidence uses real time and blocks takeover until confirmed', () => {
  const { gateway: g, advance, events } = fixture(); const s = g.admit(); const token = g.begin(s, 0.1);
  g.setPause(true); g.evidenceDelay = 0.1; g.stop(token);
  assert.throws(() => g.begin(s, 0.1), /inhibited/); advance(0.05); assert.equal(events.length, 0);
  advance(0.05); assert.equal(events[0].status, 'cancelled');
  assert.equal(g.snapshot().virtualTime, 0); assert.ok(g.begin(s, 0.1));
});
test('missing/late stop evidence latches inhibition and requires explicit recovery', () => {
  for (const delay of [Infinity, limits.stop + 0.01]) {
    const { gateway: g, advance, events } = fixture(); const s = g.admit(); const token = g.begin(s, 0.1);
    g.evidenceDelay = delay; g.stop(token); advance(0.3);
    assert.equal(events[0].status, 'stop-unconfirmed'); assert.equal(g.snapshot().inhibited, true);
    assert.throws(() => g.admit(), /inhibited/); assert.throws(() => g.recover(false), /not-ready/);
    advance(1); assert.equal(events.length, 1);
    g.recover(true); assert.ok(g.admit());
  }
});
test('old stop and renew cannot affect a newly admitted session; global stop still works', () => {
  const { gateway: g, events } = fixture(); const s = g.admit(); const old = g.begin(s, 0.1);
  g.revoke('takeover'); g.tick(); const nextSession = g.admit(); const next = g.begin(nextSession, 0.1);
  assert.throws(() => g.stop(old), /revoked/); assert.throws(() => g.renew(old), /revoked/);
  assert.deepEqual(g.snapshot().owner, next);
  g.revoke('operator-stop'); g.tick(); assert.equal(events.length, 2);
});
test('handover guard survives session loss; explicit clearance required', () => {
  const { gateway: g } = fixture(); const s = g.admit(); g.hold(s);
  assert.throws(() => g.begin(s, 0.1), /inhibited/); assert.throws(() => g.clear(s, false), /clearance/);
  g.revoke('runner-exited'); assert.throws(() => g.admit(), /inhibited/);
  g.recover(true); assert.ok(g.admit());
});
test('revocation during pending arrival evidence cannot report successful completion', () => {
  const { gateway: g, advance, events } = fixture(); const s = g.admit();
  g.evidenceDelay = 0.1; g.begin(s, 0.05); advance(0.05);
  assert.equal(g.snapshot().stopping, true);
  g.revoke('runner-disconnected'); advance(0.11);
  assert.equal(events.length, 1); assert.equal(events[0].status, 'interrupted');
  assert.equal(events[0].reason, 'runner-disconnected');
});
