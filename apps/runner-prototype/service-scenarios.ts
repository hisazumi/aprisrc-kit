import assert from 'node:assert/strict';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { performance } from 'node:perf_hooks';
import { harness, until } from './console-test-harness.ts';
export interface Scenario {
  version: 1; id: string; description: string; flow: 'accept' | 'decline';
  operatorLossAt: 'handover' | null; reconnectAt: 'offer' | null; arrivalDelayMs: number;
  expected: { status: 'completed' | 'interrupted'; guard: boolean; minX: number; maxX: number; questions: number; message: string | null };
}
export function parseScenarios(value: unknown): Scenario[] {
  if (!Array.isArray(value) || !value.length || value.length > 32) throw new Error('invalid-scenario-list');
  const ids = new Set<string>();
  const exact = (v: any, fields: string[]) => v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k));
  for (const s of value) {
    if (!exact(s, ['version', 'id', 'description', 'flow', 'operatorLossAt', 'reconnectAt', 'arrivalDelayMs', 'expected']) ||
        s.version !== 1 || typeof s.id !== 'string' || !/^[a-z][a-z0-9-]{0,63}$/.test(s.id) || ids.has(s.id) ||
        typeof s.description !== 'string' || s.description.length > 512 || !['accept','decline'].includes(s.flow) ||
        ![null,'handover'].includes(s.operatorLossAt) || ![null,'offer'].includes(s.reconnectAt) ||
        !Number.isSafeInteger(s.arrivalDelayMs) || s.arrivalDelayMs < 0 || s.arrivalDelayMs > 3000 ||
        !exact(s.expected, ['status','guard','minX','maxX','questions','message'])) throw new Error('invalid-scenario');
    const e = s.expected;
    if (!['completed','interrupted'].includes(e.status) || typeof e.guard !== 'boolean' ||
        !Number.isFinite(e.minX) || !Number.isFinite(e.maxX) || e.minX < 0 || e.maxX < e.minX || e.maxX > 1 ||
        !Number.isSafeInteger(e.questions) || e.questions < 1 || e.questions > 8 ||
        !(e.message === null || typeof e.message === 'string' && e.message.length <= 512) ||
        (s.flow === 'decline' && s.operatorLossAt)) throw new Error('invalid-expectation');
    ids.add(s.id);
  }
  return value as Scenario[];
}
export function loadScenarios() {
  return parseScenarios(JSON.parse(readFileSync(new URL('../server/scenarios/runner/service-flows.json', import.meta.url), 'utf8')));
}
export interface Trace {
  version: 1; scenario: Scenario; startedAt: string; passed: boolean; error?: string;
  entries: { elapsedMs: number; kind: string; detail: unknown }[];
}
export function saveTrace(trace: Trace, directory: string) {
  parseScenarios([trace.scenario]);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, trace.scenario.id + '.json'), JSON.stringify(trace, null, 2) + '\n');
}
export async function runScenario(input: Scenario): Promise<Trace> {
  const scenario = parseScenarios([input])[0]; // Validate before creating processes or writing files.
  const trace: Trace = { version: 1, scenario, startedAt: new Date().toISOString(), passed: false, entries: [] };
  const began = performance.now();
  const record = (kind: string, detail: unknown) => {
    if (trace.entries.length >= 256) throw new Error('trace-capacity');
    trace.entries.push({ elapsedMs: Math.round(performance.now() - began), kind, detail });
  };
  let h: Awaited<ReturnType<typeof harness>> | undefined;
  try {
    h = await harness(); const connected = h;
    record('setup', { backend: 'simulator', syntheticFront: 'CLEAR', operatorRecovery: true });
    const initial = await h.rpc.http('state');
    let viewId = (await h.rpc.http('service/view', {})).viewId;
    await h.rpc.http('service/launch', { controlEpoch: initial.controlEpoch, operatorId: h.operatorId });
    record('launch', { service: 'myService' });
    const seen = new Set<string>(); let disconnected = false; let reconnected = false;
    let runEpoch: string | undefined;
    const deadline = performance.now() + 12000;
    while (performance.now() < deadline) {
      const state = await h.rpc.http('state');
      const service = await h.rpc.http('service/state');
      if (service.live) {
        if (runEpoch) assert.equal(service.runEpoch, runEpoch, 'unexpected replacement run');
        runEpoch = service.runEpoch;
      }
      if (state.serviceProcess && !state.serviceProcess.active) break;
      const p = service.prompt;
      if (p && !seen.has(p.id) && !disconnected) {
        seen.add(p.id);
        record('question', { id: p.id, runEpoch: service.runEpoch, message: p.message, choices: p.choices, stationary: p.stationary });
        if (p.stationary && scenario.operatorLossAt === 'handover') {
          assert.ok(service.guardId); h.stopOperator(); disconnected = true;
          record('operator-disconnect', { guardHeld: true });
          continue;
        }
        const offer = p.choices.includes('Yes') && p.choices.includes('No');
        const value = offer ? (scenario.flow === 'accept' ? 'Yes' : 'No') : p.choices[0];
        const answer = { viewId, runEpoch: service.runEpoch, questionId: p.id, value };
        if (offer && scenario.reconnectAt === 'offer') {
          viewId = (await h.rpc.http('service/view', {})).viewId;
          await assert.rejects(h.rpc.http('service/answer', answer), /stale/);
          reconnected = true; record('view-reconnect', { oldAnswerRejected: true, runEpoch: service.runEpoch });
        }
        if (p.message.includes('デモ：') && scenario.arrivalDelayMs) {
          await delay(scenario.arrivalDelayMs);
          const stopped = await h.rpc.http('state');
          assert.equal(stopped.operation, null); assert.equal(stopped.state.velocity.vx, 0);
          await delay(100);
          assert.deepEqual((await h.rpc.http('state')).state.pose, stopped.state.pose);
          record('arrival-wait', { delayMs: scenario.arrivalDelayMs, pose: stopped.state.pose, stationary: true });
        }
        await h.rpc.http('service/answer', { ...answer, viewId });
        record('answer', { questionId: p.id, value });
        if (p.stationary) {
          const pending = await h.rpc.http('service/state'); assert.ok(pending.guardId);
          await h.control('clearHandover', { operatorId: h.operatorId, guardId: pending.guardId, confirmed: true });
          record('operator-clearance', { confirmed: true });
        }
      }
      await delay(25);
    }
    const final = await until(() => connected.rpc.http('state'), s => !s.serviceProcess?.active && !s.pendingIo && !s.operation);
    const service = await h.rpc.http('service/state');
    record('final', { result: service.result, process: final.serviceProcess, messages: service.messages,
      pose: final.state.pose, velocity: final.state.velocity, guard: !!final.guard, inhibited: final.inhibited,
      session: final.session, pendingIo: final.pendingIo, events: final.events });
    const e = scenario.expected;
    assert.equal(service.result?.status, e.status); assert.equal(!!final.guard, e.guard);
    assert.equal(final.session, null); assert.equal(final.moving, false);
    assert.deepEqual(final.state.velocity, { vx: 0, vy: 0, wz: 0 });
    assert.ok(final.state.pose.x >= e.minX && final.state.pose.x <= e.maxX, 'pose outside expected interval');
    assert.equal(seen.size, e.questions);
    if (e.message) assert.ok(service.messages.some((m: string) => m.includes(e.message!)));
    if (scenario.operatorLossAt) { assert.ok(disconnected); assert.ok(final.inhibited); }
    if (scenario.reconnectAt) assert.ok(reconnected);
    trace.passed = true;
  } catch (error) {
    trace.error = String(error); record('failure', { message: String(error) });
    if (h) try {
      const s = await h.rpc.http('state');
      record('failure-state', { process: s.serviceProcess, result: s.serviceResult,
        pose: s.state.pose, velocity: s.state.velocity, guard: !!s.guard, session: s.session, pendingIo: s.pendingIo, events: s.events });
    } catch { record('failure-state-unavailable', {}); }
  } finally {
    try { await h?.close(); } catch (error) { trace.passed = false; trace.error = 'cleanup: ' + String(error); }
  }
  return trace;
}
