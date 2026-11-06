import type { Readable, Writable } from 'node:stream';
type Pending = { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> };
/** Bounded JSON-lines request/reply transport. Never retries a command. */
export class JsonLineRpc {
  private output: Writable;
  private pending = new Map<number, Pending>();
  private listeners = new Set<(v: Record<string, unknown>) => void>();
  private buffer = Buffer.alloc(0);
  private serial = 0;
  private lifecycle = new AbortController();
  readonly signal = this.lifecycle.signal;
  private limits: { maxFrameBytes: number; maxPending: number; maxWriteBytes: number; requestMs: number };
  constructor(input: Readable, output: Writable, options: Partial<JsonLineRpc['limits']> = {}) {
    this.output = output;
    this.limits = { maxFrameBytes: 65_536, maxPending: 32, maxWriteBytes: 131_072, requestMs: 1000, ...options };
    for (const n of Object.values(this.limits)) if (!Number.isSafeInteger(n) || n < 1) throw new Error('invalid-limit');
    input.on('data', (chunk: Buffer | string) => this.consume(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    input.on('error', e => this.fail(e)); output.on('error', e => this.fail(e));
    input.on('end', () => this.fail(new Error('stream-ended')));
    input.on('close', () => this.fail(new Error('stream-closed')));
  }
  onEvent(listener: (v: Record<string, unknown>) => void): () => void {
    if (this.signal.aborted) throw new Error('connection-closed');
    if (this.listeners.size >= 16) throw new Error('listener-capacity');
    this.listeners.add(listener); return () => { this.listeners.delete(listener); };
  }
  request(action: string, data: object = {}): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (this.signal.aborted) throw new Error('connection-closed');
      if (this.pending.size >= this.limits.maxPending) throw new Error('request-capacity');
      if (this.serial >= Number.MAX_SAFE_INTEGER) throw new Error('request-id-exhausted');
      const id = ++this.serial;
      const frame = Buffer.from(JSON.stringify({ ...data, id, action }) + '\n');
      if (frame.length > this.limits.maxFrameBytes) throw new Error('outbound-frame-too-large');
      if (this.output.writableLength + frame.length > this.limits.maxWriteBytes) {
        const error = new Error('write-buffer-limit'); this.fail(error); throw error;
      }
      const timer = setTimeout(() => this.fail(new Error('request-timeout')), this.limits.requestMs);
      this.pending.set(id, { resolve, reject, timer });
      try { this.output.write(frame, error => { if (error) this.fail(error); }); }
      catch (e) { this.fail(e); }
    });
  }
  private consume(chunk: Buffer) {
    if (this.signal.aborted) return;
    let start = 0;
    while (start < chunk.length) {
      const newline = chunk.indexOf(10, start);
      const end = newline === -1 ? chunk.length : newline + 1;
      const part = chunk.subarray(start, end);
      if (this.buffer.length + part.length > this.limits.maxFrameBytes) { this.fail(new Error('inbound-frame-too-large')); return; }
      this.buffer = Buffer.concat([this.buffer, part]); start = end;
      if (newline === -1) return;
      try {
        const m: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(this.buffer));
        this.buffer = Buffer.alloc(0);
        if (!m || typeof m !== 'object' || Array.isArray(m)) throw new Error('invalid-envelope');
        const value = m as Record<string, unknown>;
        if (value.kind === 'reply') {
          if (!Number.isSafeInteger(value.id) || typeof value.ok !== 'boolean') throw new Error('invalid-reply');
          const p = this.pending.get(value.id as number);
          if (p) {
            this.pending.delete(value.id as number); clearTimeout(p.timer);
            if (value.ok) p.resolve(value.value); else p.reject(new Error(String(value.error)));
          }
        } else {
          if (typeof value.kind !== 'string') throw new Error('invalid-event');
          for (const listener of [...this.listeners]) listener(value);
        }
      } catch (e) { this.fail(e); return; }
      if (this.signal.aborted) return;
    }
  }
  fail(reason: unknown) {
    if (this.signal.aborted) return;
    const error = new Error('operation-uncertain: ' + String(reason));
    // Fence before callbacks; no reentrant request can enter this connection.
    this.lifecycle.abort(error);
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(error); }
    this.pending.clear(); this.listeners.clear(); this.buffer = Buffer.alloc(0);
  }
  close() { this.fail('transport-closed'); }
}
