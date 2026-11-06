/** Trusted local control protocol. Roles require enforcement at a future network boundary. */
export interface ControlScope {
  protocolVersion: 1;
  connectionEpoch: string;
  requestId: string;
  robotId: string;
}
export type ControlRequest = ControlScope & (
  { kind: 'openOperator' | 'globalStop' | 'snapshot' }
  | { kind: 'operatorHeartbeat'; operatorId: string; sequence: number }
  | { kind: 'openRun'; operatorId: string; runId: string }
  | { kind: 'closeRun' | 'acquireHandover'; runId: string; runEpoch: string }
  | { kind: 'runnerHeartbeat'; runId: string; runEpoch: string; sequence: number }
  | { kind: 'clearHandover'; operatorId: string; guardId: string; confirmed: true }
  | { kind: 'recover'; operatorId: string; guardId: string | null; confirmed: true }
);
export type ControlReply = ControlScope & {
  kind: 'controlReply'; command: ControlRequest['kind']; operatorId: string | null;
  runId: string | null; runEpoch: string | null; guardId: string | null;
  inhibited: boolean; stopPending: boolean;
};
const fields = {
  openOperator: [], globalStop: [], snapshot: [],
  operatorHeartbeat: ['operatorId', 'sequence'], openRun: ['operatorId', 'runId'],
  closeRun: ['runId', 'runEpoch'], runnerHeartbeat: ['runId', 'runEpoch', 'sequence'],
  acquireHandover: ['runId', 'runEpoch'], clearHandover: ['operatorId', 'guardId', 'confirmed'],
  recover: ['operatorId', 'guardId', 'confirmed'],
} as const;
const base = ['protocolVersion', 'connectionEpoch', 'requestId', 'robotId', 'kind'];
function text(v: unknown): string {
  if (typeof v !== 'string' || !v.trim() || v.length > 64) throw new Error('invalid-string');
  return v;
}
function exact(m: Record<string, unknown>, names: readonly string[]) {
  if (Object.keys(m).length !== names.length || Object.keys(m).some(k => !names.includes(k))) throw new Error('invalid-fields');
}
export function parseControlMessage(value: unknown): ControlRequest | ControlReply {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid-object');
  const m = value as Record<string, unknown>;
  if (m.protocolVersion !== 1) throw new Error('unsupported-version');
  const s: ControlScope & Record<string, unknown> = { protocolVersion: 1, connectionEpoch: text(m.connectionEpoch), requestId: text(m.requestId), robotId: text(m.robotId), kind: text(m.kind) };
  if (m.kind === 'controlReply') {
    exact(m, [...base, 'command', 'operatorId', 'runId', 'runEpoch', 'guardId', 'inhibited', 'stopPending']);
    if (typeof m.command !== 'string' || !Object.hasOwn(fields, m.command)) throw new Error('invalid-command');
    s.command = m.command;
    for (const k of ['operatorId', 'runId', 'runEpoch', 'guardId']) s[k] = m[k] === null ? null : text(m[k]);
    if ((s.runId === null) !== (s.runEpoch === null)) throw new Error('invalid-run-state');
    for (const k of ['inhibited', 'stopPending']) { if (typeof m[k] !== 'boolean') throw new Error('invalid-boolean'); s[k] = m[k]; }
    // Every field and cross-field invariant above is checked at this wire boundary.
    return s as unknown as ControlReply;
  }
  if (typeof m.kind !== 'string' || !Object.hasOwn(fields, m.kind)) throw new Error('unknown-kind');
  const names = fields[m.kind as keyof typeof fields];
  exact(m, [...base, ...names]);
  for (const k of names) {
    if (k === 'confirmed') { if (m[k] !== true) throw new Error('clearance-required'); s[k] = true; }
    else if (k === 'sequence') { if (!Number.isSafeInteger(m[k]) || (m[k] as number) < 1) throw new Error('invalid-sequence'); s[k] = m[k]; }
    else s[k] = k === 'guardId' && m.kind === 'recover' && m[k] === null ? null : text(m[k]);
  }
  return s as unknown as ControlRequest;
}
