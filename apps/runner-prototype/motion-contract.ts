/** Versioned motion contract for the consolidated runner. No motor I/O or authority here. */
export interface Scope {
  protocolVersion: 1;
  connectionEpoch: string;
  requestId: string;
  robotId: string;
  runId: string;
  activityId: string;
  operationId: string;
}
export type MotionGoal = { kind: 'move'; distanceM: number; speedMps: number }
  | { kind: 'turn'; angleRad: number; speedRadS: number };
export type StartMotion = Scope & { kind: 'startMotion'; goal: MotionGoal };
export type ScopedCommand = Scope & { kind: 'renewMotion' | 'cancelMotion'; generation: number };
export type CommandAck = Scope & { kind: 'commandAck'; generation: number };
export type Progress = Scope & { kind: 'accepted' | 'running'; generation: number };
export type Rejected = Scope & { kind: 'rejected'; reason: string };
export type StopEvidence = { kind: 'simulated' | 'physical'; epoch: string; observedAt: number };
export type Terminal = Scope & { kind: 'terminal'; generation: number; reason: string } & (
  { outcome: 'completed' | 'cancelled' | 'interrupted'; evidence: StopEvidence }
  | { outcome: 'failed'; evidence: StopEvidence | { kind: 'not-started' } }
  | { outcome: 'stop-unconfirmed'; evidence: { kind: 'unknown' } }
);
export type MotionMessage = StartMotion | ScopedCommand | CommandAck | Progress | Rejected | Terminal;
export type MotionResult = Rejected | Terminal;

const scopeKeys = ['protocolVersion', 'connectionEpoch', 'requestId', 'robotId', 'runId', 'activityId', 'operationId'] as const;
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid-object');
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: readonly string[]) {
  if (Object.keys(value).length !== allowed.length || Object.keys(value).some(k => !allowed.includes(k))) throw new Error('invalid-fields');
}
function text(value: unknown, limit = 64): string {
  if (typeof value !== 'string' || !value.trim() || value.length > limit) throw new Error('invalid-string');
  return value;
}
function number(value: unknown, low: number, high: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high) throw new Error('invalid-number');
  return value;
}
function generation(value: unknown): number {
  const n = number(value, 1, Number.MAX_SAFE_INTEGER);
  if (!Number.isSafeInteger(n)) throw new Error('invalid-generation');
  return n;
}
function goal(value: unknown): MotionGoal {
  const g = object(value);
  if (g.kind === 'move') {
    keys(g, ['kind', 'distanceM', 'speedMps']);
    const distanceM = number(g.distanceM, -5, 5);
    if (Math.abs(distanceM) < 1e-9) throw new Error('zero-distance');
    return { kind: 'move', distanceM, speedMps: number(g.speedMps, .05, .30) };
  }
  if (g.kind === 'turn') {
    keys(g, ['kind', 'angleRad', 'speedRadS']);
    const angleRad = number(g.angleRad, -4 * Math.PI, 4 * Math.PI);
    // Existing Python TurnCommand uses degrees; preserve its nonzero threshold.
    if (Math.abs(angleRad * 180 / Math.PI) < 1e-9) throw new Error('zero-angle');
    return { kind: 'turn', angleRad, speedRadS: number(g.speedRadS, .1, 1.2) };
  }
  throw new Error('invalid-goal');
}
function evidence(value: unknown): StopEvidence | { kind: 'unknown' } | { kind: 'not-started' } {
  const e = object(value);
  if (e.kind === 'unknown' || e.kind === 'not-started') { keys(e, ['kind']); return { kind: e.kind }; }
  if (e.kind !== 'simulated' && e.kind !== 'physical') throw new Error('invalid-evidence');
  keys(e, ['kind', 'epoch', 'observedAt']);
  return { kind: e.kind, epoch: text(e.epoch), observedAt: number(e.observedAt, 0, Number.MAX_VALUE) };
}
/** Strict decode + detached canonical copy; unknown fields are errors, never ignored. */
export function parseMotionMessage(value: unknown): MotionMessage {
  const v = object(value);
  if (v.protocolVersion !== 1) throw new Error('unsupported-version');
  const s: Scope = { protocolVersion: 1, connectionEpoch: text(v.connectionEpoch), requestId: text(v.requestId), robotId: text(v.robotId), runId: text(v.runId), activityId: text(v.activityId), operationId: text(v.operationId) };
  switch (v.kind) {
    case 'startMotion': keys(v, [...scopeKeys, 'kind', 'goal']); return { ...s, kind: v.kind, goal: goal(v.goal) };
    case 'renewMotion': case 'cancelMotion': case 'accepted': case 'running': case 'commandAck':
      keys(v, [...scopeKeys, 'kind', 'generation']); return { ...s, kind: v.kind, generation: generation(v.generation) };
    case 'rejected': keys(v, [...scopeKeys, 'kind', 'reason']); return { ...s, kind: v.kind, reason: text(v.reason, 256) };
    case 'terminal': {
      keys(v, [...scopeKeys, 'kind', 'generation', 'reason', 'outcome', 'evidence']);
      const e = evidence(v.evidence);
      const base = { ...s, kind: 'terminal' as const, generation: generation(v.generation), reason: text(v.reason, 256) };
      if (v.outcome === 'stop-unconfirmed' && e.kind === 'unknown') return { ...base, outcome: v.outcome, evidence: e };
      if (v.outcome === 'failed' && e.kind !== 'unknown') return { ...base, outcome: v.outcome, evidence: e };
      if (['completed', 'cancelled', 'interrupted'].includes(v.outcome as string) && (e.kind === 'simulated' || e.kind === 'physical')) return { ...base, outcome: v.outcome as 'completed' | 'cancelled' | 'interrupted', evidence: e };
      throw new Error('invalid-outcome-evidence');
    }
    default: throw new Error('unknown-kind');
  }
}

export interface MotionTransport {
  /** Must deliver a complete bounded message or throw. No automatic retries. */
  send(message: MotionMessage): void;
  subscribe(message: (value: unknown) => void, disconnected: (reason: string) => void): () => void;
}
function capacity(value: number) { if (!Number.isSafeInteger(value) || value < 1) throw new Error('invalid-capacity'); }
function sameScope(a: Scope, b: Scope) { return scopeKeys.every(k => a[k] === b[k]); }
interface Pending {
  start: StartMotion;
  generation?: number;
  settled: boolean;
  cancelRequest?: string;
  cancelSent?: boolean;
  resolve: (result: MotionResult) => void;
  reject: (error: Error) => void;
}
/** Connection-scoped correlation. Completed IDs are retained until connection disposal. */
export class MotionClient {
  private records = new Map<string, Pending>();
  private requests = new Set<string>();
  private closed = false;
  private unsubscribe: () => void = () => {};
  private transport: MotionTransport;
  private epoch: string;
  private limit: number;
  constructor(transport: MotionTransport, epoch: string, limit = 256) {
    capacity(limit); this.epoch = text(epoch); this.limit = limit; this.transport = transport;
    this.unsubscribe = transport.subscribe(v => this.receive(v), reason => this.close(reason));
    if (this.closed) this.unsubscribe();
  }
  start(value: StartMotion): Promise<MotionResult> {
    return new Promise((resolve, reject) => {
      if (this.closed) throw new Error('connection-closed');
      const start = parseMotionMessage(value);
      if (start.kind !== 'startMotion') throw new Error('expected-start');
      if (start.connectionEpoch !== this.epoch) throw new Error('stale-epoch');
      if (this.records.has(start.operationId) || this.requests.has(start.requestId)) throw new Error('duplicate-start');
      if (this.records.size >= this.limit) throw new Error('capacity-exhausted');
      this.records.set(start.operationId, { start, settled: false, resolve, reject });
      this.requests.add(start.requestId);
      try { this.transport.send(start); } catch (e) { this.close(String(e)); }
    });
  }
  /** Ignore only an obsolete scoped renewal/cancel rejection after a known terminal. */
  rejectCommand(message: MotionMessage, error: unknown): boolean {
    const p = this.records.get(message.operationId);
    if ((message.kind === 'renewMotion' || message.kind === 'cancelMotion') && p?.settled &&
      p.generation === message.generation && scopeKeys.every(k => k === 'requestId' || p.start[k] === message[k])) return false;
    this.close(String(error)); return true;
  }
  renew(operationId: string, requestId: string): void {
    const p = this.records.get(operationId);
    if (this.closed || !p || p.settled || p.cancelRequest || p.generation === undefined) return;
    text(requestId);
    if (this.requests.has(requestId)) throw new Error('duplicate-request');
    if (this.requests.size >= this.limit * 4) { this.close('request-capacity-exhausted'); return; }
    this.requests.add(requestId);
    const { goal: _goal, ...scope } = p.start;
    try { this.transport.send({ ...scope, kind: 'renewMotion', requestId, generation: p.generation }); }
    catch (e) { this.close(String(e)); }
  }
  cancel(operationId: string, requestId: string): void {
    const p = this.records.get(operationId);
    if (this.closed || !p || p.settled || p.cancelRequest) return;
    text(requestId);
    if (this.requests.has(requestId)) throw new Error('duplicate-request');
    this.requests.add(requestId); p.cancelRequest = requestId;
    this.sendCancel(p);
  }
  private sendCancel(p: Pending) {
    if (!p.cancelRequest || p.cancelSent || p.settled || p.generation === undefined) return;
    p.cancelSent = true;
    const { goal: _goal, ...scope } = p.start;
    try { this.transport.send({ ...scope, kind: 'cancelMotion', requestId: p.cancelRequest, generation: p.generation }); }
    catch (e) { this.close(String(e)); }
  }
  private receive(value: unknown) {
    if (this.closed) return;
    let m: MotionMessage;
    try { m = parseMotionMessage(value); } catch { this.close('invalid-message'); return; }
    const p = this.records.get(m.operationId);
    if (!p || !sameScope(p.start, m) || p.settled) return;
    if (m.kind === 'startMotion' || m.kind === 'renewMotion' || m.kind === 'cancelMotion' || m.kind === 'commandAck') { this.close('wrong-direction'); return; }
    if (m.kind === 'rejected') {
      if (p.generation !== undefined) { this.close('rejected-after-acceptance'); return; }
      p.settled = true; p.resolve(m); return;
    }
    if (p.generation !== undefined && p.generation !== m.generation) return;
    p.generation = m.generation;
    if (m.kind === 'terminal') { p.settled = true; p.resolve(m); }
    else this.sendCancel(p);
  }
  close(reason = 'client-disposed') {
    if (this.closed) return;
    this.closed = true;
    for (const p of this.records.values()) if (!p.settled) { p.settled = true; p.reject(new Error('operation-uncertain: ' + reason)); }
    this.unsubscribe();
    this.records.clear(); this.requests.clear();
  }
}

/** Reference admission ledger for contract tests; not a replacement for Python authority.
 * Only a duplicate=false return may create work. No eviction within a connection.
 */
export class StartLedger {
  private records = new Map<string, { fingerprint: string; generation: number }>();
  private requests = new Set<string>();
  private epoch: string;
  private limit: number;
  constructor(epoch: string, limit = 256) { this.epoch = text(epoch); capacity(limit); this.limit = limit; }
  admit(value: unknown): { generation: number; duplicate: boolean } {
    const start = parseMotionMessage(value);
    if (start.kind !== 'startMotion') throw new Error('expected-start');
    if (start.connectionEpoch !== this.epoch) throw new Error('stale-epoch');
    const fingerprint = JSON.stringify(start);
    const old = this.records.get(start.operationId);
    if (old) {
      if (old.fingerprint !== fingerprint) throw new Error('id-conflict');
      return { generation: old.generation, duplicate: true };
    }
    if (this.requests.has(start.requestId)) throw new Error('id-conflict');
    if (this.records.size >= this.limit) throw new Error('capacity-exhausted');
    const generation = this.records.size + 1;
    this.records.set(start.operationId, { fingerprint, generation }); this.requests.add(start.requestId);
    return { generation, duplicate: false };
  }
}
