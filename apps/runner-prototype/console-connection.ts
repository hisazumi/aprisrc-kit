import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { runFakeService, type HostConnection, type ServiceInputs } from './service-host.ts';
import type { StudentService } from '../pwa/src/service/studentService.ts';

/** Local simulator binding; no command replay, no operator heartbeat or recovery. */
export class ConsoleConnection {
  readonly lifecycle = new AbortController();
  readonly signal = this.lifecycle.signal;
  private listeners = new Set<(v: Record<string, unknown>) => void>();
  private cursor = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private pending = 0;
  private token: string;
  private origin: string;
  constructor(token: string, origin = 'http://127.0.0.1:8766') {
    this.token = token; this.origin = origin;
    if (origin !== 'http://127.0.0.1:8766') throw new Error('loopback-console-only');
  }
  async http(path: string, body?: unknown): Promise<any> {
    this.signal.throwIfAborted();
    if (this.pending >= 32) throw new Error('request-capacity');
    this.pending++;
    try {
      const response = await fetch(this.origin + '/api/' + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { Authorization: 'Bearer ' + this.token, Origin: this.origin, 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.any([this.signal, AbortSignal.timeout(1000)]),
      });
      const text = await response.text();
      if (Buffer.byteLength(text) > 262144) throw new Error('response-too-large');
      const value = JSON.parse(text);
      if (!response.ok) throw new Error(value.detail || 'console-request-failed');
      return value;
    } finally { this.pending--; }
  }
  async initialize() {
    const state = await this.http('state'); this.cursor = state.eventCursor;
    if (!Number.isSafeInteger(this.cursor)) throw new Error('invalid-event-cursor');
    this.timer = setTimeout(() => void this.poll(), 40);
    return state;
  }
  private eventRead: Promise<void> = Promise.resolve();
  private readEvents(): Promise<void> {
    const read = this.eventRead.then(async () => {
      const state = await this.http('state');
      const log = state.eventLog as { cursor: number; event: Record<string, unknown> }[];
      if (state.eventCursor < this.cursor || (log.length && log[0].cursor > this.cursor + 1)) throw new Error('event-gap-or-restart');
      for (const entry of log) if (entry.cursor > this.cursor) {
        this.cursor = entry.cursor; for (const listener of this.listeners) listener(entry.event);
      }
    });
    this.eventRead = read.catch(() => {});
    return read;
  }
  private async poll() {
    try {
      await this.readEvents();
      if (!this.signal.aborted) this.timer = setTimeout(() => void this.poll(), 40);
    } catch (e) { this.lifecycle.abort(e); }
  }
  async request(action: string, data: any = {}): Promise<unknown> {
    if (action === 'snapshot') return this.http('state');
    if (action === 'control') return this.http(action, data.message);
    if (action === 'motion') {
      try { return await this.http(action, data.message); }
      catch (error) {
        // HTTP replies and the event stream are separate. Deliver a preceding terminal
        // before a late renew/cancel error; MotionClient still checks exact scope/generation.
        await this.readEvents();
        throw error;
      }
    }
    throw new Error('unsupported-attached-action');
  }
  onEvent(listener: (v: Record<string, unknown>) => void) {
    if (this.listeners.size >= 16) throw new Error('listener-capacity');
    this.listeners.add(listener); return () => { this.listeners.delete(listener); };
  }
  close() { clearTimeout(this.timer); this.lifecycle.abort(new Error('console-detached')); this.listeners.clear(); }
}

export async function runConsoleService(definition: StudentService, token: string,
  options: { signal?: AbortSignal; serviceMs?: number } = {}) {
  const rpc = new ConsoleConnection(token);
  let attachment: HostConnection | undefined;
  let output = Promise.resolve();
  try {
    const state = await rpc.initialize();
    if (!state.control.operatorId || state.control.inhibited || state.control.guardId || state.control.runEpoch)
      throw new Error('operator-must-recover-before-service');
    const run = await rpc.http('service/start', { controlEpoch: state.controlEpoch, operatorId: state.control.operatorId });
    attachment = { rpc, ...run };
    const inputs: ServiceInputs = {
      recoveryClearance: true, // Attached mode never invokes recovery; operator did it in /console.
      operatorPresent: () => false, // Only /console is allowed to keep operator presence alive.
      waitForPerson: async signal => { // Explicit synthetic observation entered through /app.
        await prompt({ id: randomUUID(), message: '試験入力：人物が見つかりましたか？', choices: ['人物を検出'], stationary: false }, signal);
      },
      prompt: (question, signal) => prompt(question, signal),
      say: message => { output = output.then(() => rpc.http('service/say', { runEpoch: run.runEpoch, message })).then(() => {}); void output.catch(() => {}); },
    };
    async function prompt(question: { id: string; message: string; choices: readonly string[]; stationary: boolean }, signal: AbortSignal) {
      await output;
      await rpc.http('service/prompt', { runEpoch: run.runEpoch, prompt: {
        id: question.id, message: question.message, choices: question.choices, stationary: question.stationary,
      } });
      while (true) {
        signal.throwIfAborted();
        const s = await rpc.http('service/state');
        if (!s.live || s.runEpoch !== run.runEpoch) throw new Error('service-revoked');
        if (s.answered?.questionId === question.id && (!question.stationary || !s.guardId)) {
          const answer = await rpc.http('service/consume', { runEpoch: run.runEpoch, questionId: question.id });
          return { value: answer.value as string, humanClear: question.stationary ? true : undefined };
        }
        await delay(40, undefined, { signal });
      }
    }
    // Flush final speech before the host closes this run.
    const wrapped: StudentService = { ...definition, run: async api => { await definition.run(api); await output; } };
    return await runFakeService(wrapped, inputs, { backend: 'simulator', connection: attachment,
      serviceMs: options.serviceMs ?? 120000, signal: options.signal });
  } finally { rpc.close(); }
}
