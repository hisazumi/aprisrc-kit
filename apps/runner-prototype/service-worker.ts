// Browser-free execution of the existing, unchanged student service.
import { performance } from 'node:perf_hooks';
import { myService } from '../pwa/src/missions/myService.ts';
import type { StudentServiceApi } from '../pwa/src/service/studentService.ts';
import type { MotionToken, Terminal } from './gateway-core.ts';
type Reply = { kind: 'reply'; id: number; ok: boolean; value?: unknown; error?: string };
const send = (message: unknown) => { if (process.connected) process.send!(message, () => {}); };
let serial = 0;
let session = '';
const lifecycle = new AbortController();
const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
const motions = new Map<number, { resolve: (event: Terminal) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> }>();
let current: MotionToken | undefined;
function rpc<T>(action: string, data: object = {}): Promise<T> {
  lifecycle.signal.throwIfAborted();
  const id = ++serial;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('gateway-response-timeout')); }, 2000);
    pending.set(id, { resolve: value => resolve(value as T), reject, timer });
    send({ kind: 'request', id, action, session, ...data });
  });
}
function abort(reason: string) {
  lifecycle.abort(new Error(reason));
  for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error(reason)); }
  pending.clear();
}
async function begin(duration: number) {
  const token = await rpc<MotionToken>('move', { duration });
  current = token;
  const result = new Promise<Terminal>((resolve, reject) => {
    const timer = setTimeout(() => { motions.delete(token.generation); reject(new Error('motion-result-timeout')); }, 3000);
    motions.set(token.generation, { resolve, reject, timer });
  });
  void result.catch(() => {});
  return { token, result };
}
async function move(duration: number) {
  const op = await begin(duration); const event = await op.result;
  if (event.status !== 'completed') throw new Error(event.status);
  lifecycle.signal.throwIfAborted();
}
async function prompt(message: string, choices: string[], stationary = false) {
  if (stationary) await rpc('hold');
  const answer = await rpc<string>('prompt', { message, choices, stationary });
  lifecycle.signal.throwIfAborted();
  if (!choices.includes(answer)) throw new Error('invalid-answer');
  return answer;
}
const unsupported = async (): Promise<never> => { throw new Error('capability-not-supported-in-experiment'); };
const api: StudentServiceApi = {
  waitForPerson: async () => { await rpc('person'); },
  approachPerson: () => move(0.08),
  ask: async message => (await prompt(message, ['Yes', 'No'])) === 'Yes',
  confirm: async (message, label = 'Continue') => { await prompt(message, [label], true); },
  waitForLoaded: async message => { await prompt(message, ['Items are loaded'], true); },
  choose: async (message, choices) => prompt(message, choices.map(c => typeof c === 'string' ? c : c.value)),
  followPerson: async (options = {}) => {
    const op = await begin(1);
    // No unscoped cleanup stop. Supervisor revokes this session on any failure.
    await prompt(options.message ?? 'We have arrived?', [options.buttonLabel ?? 'We have arrived']);
    await rpc('stop', { token: op.token });
    const event = await op.result;
    if (event.status !== 'cancelled') throw new Error(event.status);
    lifecycle.signal.throwIfAborted();
  },
  say: message => { lifecycle.signal.throwIfAborted(); send({ kind: 'say', session, message }); },
  greetPerson: unsupported,
  guideTo: unsupported,
};
let started = false;
let heartbeat: ReturnType<typeof setInterval>;
process.on('message', async (message: any) => {
  if (message.kind === 'reply') {
    const reply = message as Reply; const p = pending.get(reply.id);
    if (!p) return;
    clearTimeout(p.timer); pending.delete(reply.id);
    if (reply.ok) p.resolve(reply.value); else p.reject(new Error(reply.error));
  } else if (message.kind === 'terminal') {
    const event = message.event as Terminal;
    if (event.token.session !== session) return;
    const p = motions.get(event.token.generation);
    if (!p) return;
    clearTimeout(p.timer); motions.delete(event.token.generation);
    if (current?.generation === event.token.generation) current = undefined;
    p.resolve(event);
  } else if (message.kind === 'revoked') {
    abort(message.reason);
  } else if (message.kind === 'block') {
    const until = performance.now() + 1500;
    while (performance.now() < until) { /* deliberate CPU-blocking service fault */ }
  } else if (message.kind === 'disconnect') {
    process.disconnect?.();
  } else if (message.kind === 'start' && !started) {
    started = true; session = message.session;
    heartbeat = setInterval(() => send({ kind: 'heartbeat', session, token: current }), 40);
    try {
      await myService.run(api);
      lifecycle.signal.throwIfAborted();
      send({ kind: 'service-result', session, status: 'completed' });
    } catch (error) {
      send({ kind: 'service-result', session, status: 'failed', reason: String(error) });
    } finally {
      clearInterval(heartbeat);
      for (const p of pending.values()) clearTimeout(p.timer);
      for (const p of motions.values()) clearTimeout(p.timer);
      pending.clear(); motions.clear();
      if (process.connected) process.disconnect?.();
    }
  }
});
process.on('disconnect', () => {
  abort('gateway-disconnected'); clearInterval(heartbeat);
  for (const p of motions.values()) { clearTimeout(p.timer); p.reject(new Error('gateway-disconnected')); }
  motions.clear();
});
