import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import type { StudentService, StudentServiceApi, ServiceChoiceInput, ServiceQuestion } from '../pwa/src/service/studentService.ts';
import { ActivityRunner, motionCapability } from './activity-runner.ts';
import { MotionClient, type MotionResult, type MotionTransport } from './motion-contract.ts';
import { parseControlMessage, type ControlReply } from './control-contract.ts';
import { JsonLineRpc } from './json-line-rpc.ts';
export interface HostQuestion extends ServiceQuestion { id: string; stationary: boolean }
export interface ServiceInputs {
  recoveryClearance: true;
  operatorPresent(): boolean;
  waitForPerson(signal: AbortSignal): Promise<void>;
  prompt(question: HostQuestion, signal: AbortSignal): Promise<{ value: string; humanClear?: boolean }>;
  say(message: string): void;
}
export interface HostConnection {
  rpc: Pick<JsonLineRpc, 'request' | 'onEvent' | 'signal' | 'close'>;
  controlEpoch: string; operatorId: string; runId: string; runEpoch: string;
}
export interface HostReport { messages: string[]; snapshot?: Record<string, unknown>; closed: boolean }
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('invalid-server-object');
  return v as Record<string, unknown>;
}
/** Single host for the consolidated runner; launches only local synthetic or planar simulator backends. */
export async function runFakeService(definition: StudentService, inputs: ServiceInputs,
  options: { waitForArrivalAfterStop?: boolean; onFinished?: (result: { status: 'completed' | 'failed'; reason: string }) => Promise<void>; connection?: HostConnection; backend?: 'fake' | 'simulator'; python?: string; serviceMs?: number; evidenceDelay?: number | 'missing'; signal?: AbortSignal } = {}): Promise<HostReport> {
  const backend = options.backend ?? 'fake';
  if (backend !== 'fake' && backend !== 'simulator') throw new Error('invalid-backend');
  const serviceMs = options.serviceMs ?? 5000;
  if (!Number.isSafeInteger(serviceMs) || serviceMs < 1) throw new Error('invalid-service-timeout');
  if (inputs.recoveryClearance !== true) throw new Error('initial-human-clearance-required');
  const child = options.connection ? undefined : spawn(options.python ?? process.env.APRIS_PYTHON ?? 'python3', ['-m', 'apris_server.runner_port_experiment', '--backend', backend], {
    env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../server/src', import.meta.url)) },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const report: HostReport = { messages: [], closed: false };
  const closed = child ? new Promise<void>(resolve => child.once('close', () => { report.closed = true; resolve(); })) : Promise.resolve();
  const rpc = options.connection?.rpc ?? new JsonLineRpc(child!.stdout, child!.stdin);
  let stderr = ''; child?.stderr.on('data', b => { stderr = (stderr + b).slice(-4096); });
  child?.on('error', e => { if (rpc instanceof JsonLineRpc) rpc.fail(e); });
  child?.on('close', () => { if (rpc instanceof JsonLineRpc) rpc.fail(new Error('Python closed: ' + stderr)); });
  const lifecycle = new AbortController();
  const stop = (reason: unknown) => { if (!lifecycle.signal.aborted) lifecycle.abort(reason instanceof Error ? reason : new Error(String(reason))); };
  const aborted = new Promise<never>((_, reject) => lifecycle.signal.addEventListener('abort', () => reject(lifecycle.signal.reason), { once: true }));
  void aborted.catch(() => {});
  const externalAbort = () => stop(options.signal?.reason ?? 'service-cancelled');
  options.signal?.addEventListener('abort', externalAbort, { once: true });
  if (options.signal?.aborted) externalAbort();
  rpc.signal.addEventListener('abort', () => stop(rpc.signal.reason), { once: true });
  const check = () => lifecycle.signal.throwIfAborted();
  const wait = <T>(p: Promise<T>) => Promise.race([p, aborted]);
  const deadline = setTimeout(() => stop(new Error('service-timeout')), serviceMs);
  let runner: ActivityRunner | undefined;
  let motion: MotionClient | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let closing = false;
  let error: unknown;
  let controlEpoch = '';
  let runEpoch = '';
  const runId = options.connection?.runId ?? randomUUID();
  const control = async (kind: string, fields: object = {}): Promise<ControlReply> => {
    const response = parseControlMessage(await rpc.request('control', { message: {
      protocolVersion: 1, connectionEpoch: controlEpoch, requestId: randomUUID(), robotId: 'fake-only', kind, ...fields,
    } }));
    if (response.kind !== 'controlReply' || response.command !== kind || response.connectionEpoch !== controlEpoch) throw new Error('unexpected-control-reply');
    return response;
  };
  const off = rpc.onEvent(m => { if (m.kind === 'revoked' && !closing) stop(new Error('run-revoked: ' + m.reason)); });
  try {
    check();
    const bootstrap = object(await rpc.request('snapshot'));
    if (typeof bootstrap.controlEpoch !== 'string') throw new Error('missing-control-epoch');
    controlEpoch = bootstrap.controlEpoch;
    let operatorId: string | null;
    if (options.connection) {
      if (controlEpoch !== options.connection.controlEpoch) throw new Error('stale-attachment');
      operatorId = options.connection.operatorId;
      runEpoch = options.connection.runEpoch;
      await control('runnerHeartbeat', { runId, runEpoch, sequence: 1 });
    } else {
      await rpc.request('fixture', { front: 'CLEAR', ...(options.evidenceDelay !== undefined ? { evidenceDelay: options.evidenceDelay } : {}) });
      operatorId = (await control('openOperator')).operatorId;
      await control('recover', { operatorId, guardId: null, confirmed: inputs.recoveryClearance });
      const admitted = await control('openRun', { operatorId, runId });
      if (!admitted.runEpoch) throw new Error('missing-run-epoch');
      runEpoch = admitted.runEpoch;
    }
    const transport: MotionTransport = {
      send(m) { void rpc.request('motion', { session: runEpoch, message: m }).then(v => receive(v), e => { if (!motion || motion.rejectCommand(m, e)) { disconnect(String(e)); stop(e); } }); },
      subscribe(message, close) { receive = message; disconnect = close;
        const unlisten = rpc.onEvent(v => { if (v.protocolVersion === 1) message(v); });
        const abort = () => close(String(rpc.signal.reason)); rpc.signal.addEventListener('abort', abort, { once: true });
        return () => { unlisten(); rpc.signal.removeEventListener('abort', abort); };
      },
    };
    let receive = (_value: unknown) => {}; let disconnect = (_reason: string) => {};
    motion = new MotionClient(transport, runEpoch);
    runner = new ActivityRunner(runId, runEpoch, motionCapability(motion, 'fake-only'));
    const active = runner;
    let sequence = 1; let ticking = false;
    heartbeat = setInterval(() => {
      if (closing || ticking) return;
      if (active.failure) { stop(active.failure); return; }
      ticking = true; sequence++;
      void (async () => {
        // Operator presence is independent of runner health, even in this scripted host.
        if (!options.connection && inputs.operatorPresent()) await control('operatorHeartbeat', { operatorId, sequence });
        await control('runnerHeartbeat', { runId, runEpoch, sequence });
      })().catch(stop).finally(() => { ticking = false; });
    }, 40);
    const question = async (message: string, choices: readonly ServiceChoiceInput[], stationary = false): Promise<string> => {
      check();
      const values = choices.map(c => typeof c === 'string' ? c : c.value);
      const opts = choices.map(c => typeof c === 'string' ? { value: c, label: c } : { ...c });
      if (!values.length || new Set(values).size !== values.length || opts.some(c => !c.value.trim() || !c.label.trim() || c.phrases?.some(p => !p.trim()))) throw new Error('invalid-choices');
      const scope = active.activity(active.root);
      let guardId: string | null = null;
      try {
        if (stationary) guardId = (await control('acquireHandover', { runId, runEpoch })).guardId;
        const prompt = active.prompt(scope, values);
        const answer = await wait(inputs.prompt({ id: prompt.id, message, choices: values, options: opts, stationary }, active.signal(scope)));
        check(); active.answer(prompt.id, answer.value); await prompt.result;
        if (stationary) {
          if (!guardId || answer.humanClear !== true) throw new Error('human-clearance-required');
          if (!options.connection) await control('clearHandover', { operatorId, guardId, confirmed: true });
          else {
            const current = await control('snapshot');
            if (current.guardId || current.runEpoch !== runEpoch) throw new Error('operator-clearance-pending');
          }
        }
        return answer.value;
      } finally { await active.cancel(scope); }
    };
    const completed = (result: MotionResult, expected: 'completed' | 'cancelled') => {
      if (result.kind !== 'terminal' || result.outcome !== expected) throw new Error(result.kind === 'terminal' ? result.outcome + ': ' + result.reason : 'motion-rejected: ' + result.reason);
    };
    const unsupported = async (): Promise<never> => { check(); throw new Error('capability-not-supported-in-fake-host'); };
    const api: StudentServiceApi = {
      waitForPerson: async () => {
        check(); const scope = active.activity(active.root);
        try { await wait(inputs.waitForPerson(active.signal(scope))); check(); }
        finally { await active.cancel(scope); }
      },
      approachPerson: async () => {
        check(); const scope = active.activity(active.root);
        try { completed(await wait(active.move(scope, { kind: 'move', distanceM: backend === 'simulator' ? .04 : .008, speedMps: .1 })), 'completed'); check(); }
        finally { await active.cancel(scope); }
      },
      ask: async (message, phrases) => (await question(message, [{ value: 'Yes', label: 'Yes', phrases: phrases?.yes }, { value: 'No', label: 'No', phrases: phrases?.no }])) === 'Yes',
      choose: (message, choices) => question(message, choices),
      confirm: async (message, label = 'Continue', phrases) => { await question(message, [{ value: label, label, phrases }], true); },
      waitForLoaded: async message => { await question(message, ['Items are loaded'], true); },
      followPerson: async (opts = {}) => {
        check(); const scope = active.activity(active.root);
        const movement = active.move(scope, { kind: 'move', distanceM: .08, speedMps: .1 });
        const arrival = question((options.waitForArrivalAfterStop ? 'デモ：短い移動後は停止して待機します。準備ができたら到着を押してください。 ' : '') + (opts.message ?? 'We have arrived?'), [{ value: opts.buttonLabel ?? 'We have arrived', label: opts.buttonLabel ?? 'We have arrived', phrases: opts.phrases }]);
        try {
          if (options.waitForArrivalAfterStop) {
            const first = await wait(Promise.race([
              arrival.then(() => 'arrival' as const),
              movement.then(result => { completed(result, 'completed'); return 'stopped' as const; }),
            ]));
            if (first === 'stopped') await wait(arrival);
            await active.cancel(scope);
            const result = await movement;
            if (result.kind !== 'terminal' || !['completed', 'cancelled'].includes(result.outcome))
              throw new Error('demo-motion-did-not-stop');
            check();
          } else {
            await wait(Promise.race([arrival, movement.then(() => { throw new Error('following-ended-before-arrival'); })]));
            await active.cancel(scope); completed(await movement, 'cancelled'); check();
          }
        } finally { await active.cancel(scope); }
      },
      say: message => { check(); if (report.messages.length >= 128 || message.length > 4096) throw new Error('speech-limit'); report.messages.push(message); inputs.say(message); },
      greetPerson: unsupported, guideTo: unsupported,
    };
    await wait(Promise.resolve().then(() => definition.run(api))); check();
    if (active.failure) throw active.failure;
  } catch (e) { error = e; stop(e); }
  finally {
    clearTimeout(deadline); options.signal?.removeEventListener('abort', externalAbort);
    // Keep host health alive while managed cancellation waits for terminal evidence.
    try { if (runner) await runner.cancel(runner.root); } catch (e) { error ??= e; }
    closing = true; clearInterval(heartbeat);
    if (runEpoch && !rpc.signal.aborted) {
      try { await control('closeRun', { runId, runEpoch }); }
      catch (e) {
        if (!error) error = e;
        try { if (!options.connection) await control('globalStop'); } catch { /* EOF below is the remaining port stop path. */ }
      }
    }
    if (!rpc.signal.aborted) {
      try { report.snapshot = object(await rpc.request('snapshot')); } catch (e) { error ??= e; }
    }
    try { await options.onFinished?.({ status: error ? 'failed' : 'completed', reason: error ? String(error).slice(0, 512) : 'service-completed' }); }
    catch (e) { error ??= e; }
    off(); motion?.close(); rpc.close(); child?.stdin.end();
    const kill = setTimeout(() => child?.kill('SIGKILL'), 700);
    let finalDeadline: ReturnType<typeof setTimeout> | undefined;
    try { await Promise.race([closed, new Promise<never>((_, reject) => { finalDeadline = setTimeout(() => reject(new Error('child-cleanup-timeout')), 1500); })]); }
    catch (e) { error ??= e; }
    finally { clearTimeout(kill); clearTimeout(finalDeadline); }
  }
  if (options.connection) report.closed = true; // Detached transport; shared Python runtime stays alive.
  if (error) throw Object.assign(new Error(String(error)), { report });
  return report;
}
