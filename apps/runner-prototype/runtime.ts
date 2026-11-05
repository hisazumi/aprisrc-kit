// Contract experiment only: no hardware transport or physical safety authority.
export type Scope = { runId: string; activityId: string; epoch: number };
export type Token = Scope & { generation: number };
export type Event = { type: string; payload?: unknown };
export type Result = { status: 'completed' | 'cancelled' | 'interrupted'; evidence: 'virtual-invalidated' };
const key = (s: Scope) => JSON.stringify([s.epoch, s.runId, s.activityId]);

export class FakeMotion {
  owner?: Token;
  guard?: string;
  generation = 0;
  acquire(s: Scope): Token {
    if (this.guard || this.owner) throw new Error('motion-inhibited-or-busy');
    this.owner = { ...s, generation: ++this.generation };
    return { ...this.owner };
  }
  current(t: Token): boolean {
    return !!this.owner && key(t) === key(this.owner) && t.generation === this.owner.generation;
  }
  stop(t: Token): boolean {
    if (!this.current(t)) return false;
    this.owner = undefined;
    return true; // Pending virtual actuation is invalidated; no physics step needed.
  }
  hold(id: string) {
    if (this.owner || this.guard) throw new Error('not-stationary-or-held');
    this.guard = id;
  }
  clear(id: string) {
    if (id !== this.guard) throw new Error('wrong-guard');
    this.guard = undefined;
  }
}

type Activity = { scope: Scope; queue: Event[]; handler: (event: Event) => void };
type Operation = { token: Token; due: number; resolve: (r: Result) => void };
export class Runtime {
  epoch = 0;
  time = 0;
  paused = false;
  motion = new FakeMotion();
  private serial = 0;
  private runs = new Map<string, string>();
  private activities = new Map<string, Activity>();
  private operations = new Map<number, Operation>();
  private prompts = new Map<string, { scope: Scope; guard?: string }>();
  readonly queueLimit = 8;

  start(service: string): Scope {
    if ([...this.runs.values()].includes(service)) throw new Error('duplicate-start');
    const s = { runId: `run-${++this.serial}`, activityId: 'root', epoch: this.epoch };
    this.runs.set(s.runId, service);
    this.activities.set(key(s), { scope: s, queue: [], handler: () => {} });
    return s;
  }
  private live(s: Scope) {
    if (s.epoch !== this.epoch || !this.runs.has(s.runId) || !this.activities.has(key(s))) {
      throw new Error('stale-scope');
    }
  }
  activity(parent: Scope, handler: (event: Event) => void): Scope {
    this.live(parent);
    // First slice: flat children of the run root, not arbitrary nesting.
    if (parent.activityId !== 'root') throw new Error('root-required');
    const s = { ...parent, activityId: `activity-${++this.serial}` };
    this.activities.set(key(s), { scope: s, queue: [], handler });
    return s;
  }
  send(to: Scope, event: Event) {
    this.live(to);
    const a = this.activities.get(key(to))!;
    if (a.queue.length >= this.queueLimit) throw new Error('queue-full');
    a.queue.push(structuredClone(event));
  }
  dispatch() {
    // One transition per activity per turn. Handlers must return synchronously.
    for (const a of [...this.activities.values()]) {
      if (!this.activities.has(key(a.scope))) continue;
      const event = a.queue.shift();
      if (event) {
        try { a.handler(event); }
        catch (error) {
          this.cancel({ ...a.scope, activityId: 'root' }, 'interrupted');
          throw error;
        }
      }
    }
  }
  move(s: Scope, duration: number) {
    this.live(s);
    if (!Number.isFinite(duration) || duration <= 0) throw new Error('invalid-duration');
    const token = this.motion.acquire(s);
    const result = new Promise<Result>(resolve => {
      this.operations.set(token.generation, { token, due: this.time + duration, resolve });
    });
    return { token, result };
  }
  private finish(op: Operation, status: Result['status']) {
    this.motion.stop(op.token);
    this.operations.delete(op.token.generation);
    op.resolve({ status, evidence: 'virtual-invalidated' });
  }
  step(dt: number) {
    if (!Number.isFinite(dt) || dt < 0) throw new Error('invalid-step');
    if (!this.paused) this.time += dt;
    for (const op of [...this.operations.values()]) {
      if (this.time >= op.due) this.finish(op, 'completed');
    }
    this.dispatch();
  }
  cancel(s: Scope, status: Result['status'] = 'cancelled') {
    this.live(s);
    const matches = (other: Scope) => other.runId === s.runId &&
      (s.activityId === 'root' || other.activityId === s.activityId);
    // Fence scopes before resolving promises, so late cleanup cannot reacquire.
    for (const [id, a] of this.activities) if (matches(a.scope)) this.activities.delete(id);
    if (s.activityId === 'root') this.runs.delete(s.runId);
    for (const op of [...this.operations.values()]) if (matches(op.token)) this.finish(op, status);
    for (const [id, p] of this.prompts) if (matches(p.scope)) this.prompts.delete(id);
    // A cancelled human handover does not establish clearance: guard stays held.
  }
  prompt(s: Scope, stationary = false): string {
    this.live(s);
    const id = `prompt-${++this.serial}`;
    if (stationary) this.motion.hold(id);
    this.prompts.set(id, { scope: s, guard: stationary ? id : undefined });
    return id;
  }
  answer(id: string, clearToMove = false) {
    const p = this.prompts.get(id);
    if (!p) throw new Error('stale-prompt');
    this.live(p.scope);
    if (p.guard && !clearToMove) throw new Error('clearance-required');
    if (p.guard) this.motion.clear(p.guard);
    this.prompts.delete(id);
    return p.scope;
  }
  globalStop() {
    for (const runId of [...this.runs.keys()]) {
      this.cancel({ runId, activityId: 'root', epoch: this.epoch }, 'interrupted');
    }
  }
  reset() {
    this.globalStop();
    // Fake-only reset discards the complete virtual scene, including virtual people.
    this.motion.guard = undefined;
    this.epoch++;
    this.time = 0;
    this.paused = false;
  }
  snapshot() {
    return { target: 'fake-only', epoch: this.epoch, time: this.time, paused: this.paused,
      runs: this.runs.size, activities: this.activities.size, prompts: this.prompts.size,
      owner: this.motion.owner, guard: this.motion.guard };
  }
}
