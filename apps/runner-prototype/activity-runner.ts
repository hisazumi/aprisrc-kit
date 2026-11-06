import { randomUUID } from 'node:crypto';
import type { MotionClient, MotionGoal, MotionResult } from './motion-contract.ts';

export type ActivityScope = Readonly<{ runId: string; runEpoch: string; activityId: string }>;
export type ActivityEvent = { type: string; payload?: unknown };
export interface MotionCapability {
  move(scope: ActivityScope, goal: MotionGoal, signal: AbortSignal): Promise<MotionResult>;
}
/** Adapter to the single Python motion authority. No second owner/guard model in Node. */
export function motionCapability(client: MotionClient, robotId: string): MotionCapability {
  return { move(scope, goal, signal) {
    if (signal.aborted) return Promise.reject(new Error('activity-cancelled'));
    const operationId = randomUUID();
    const result = client.start({ protocolVersion: 1, connectionEpoch: scope.runEpoch,
      requestId: randomUUID(), robotId, runId: scope.runId, activityId: scope.activityId,
      operationId, kind: 'startMotion', goal });
    const renewal = setInterval(() => client.renew(operationId, randomUUID()), 40);
    const abort = () => { clearInterval(renewal); client.cancel(operationId, randomUUID()); };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    return result.finally(() => { clearInterval(renewal); signal.removeEventListener('abort', abort); });
  } };
}
class CancelledPrompt extends Error {}
interface Activity {
  scope: ActivityScope; parent?: string; live: boolean; uncertain: boolean; abort: AbortController;
  queue: ActivityEvent[]; handler: (event: ActivityEvent) => unknown;
  tasks: Set<Promise<unknown>>; cleanups: Set<() => unknown>; done?: Promise<void>;
}
export class ActivityRunner {
  readonly root: ActivityScope;
  failure: Error | null = null;
  private activities = new Map<string, Activity>();
  private prompts = new Map<string, { owner: Activity; choices: string[]; resolve: (s: string) => void; dispose: () => void }>();
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private scheduled?: ReturnType<typeof setImmediate>;
  private motion: MotionCapability;
  private limits: { queueLimit: number; activityLimit: number; resourceLimit: number; joinMs: number };
  constructor(runId: string, runEpoch: string, motion: MotionCapability,
    options: Partial<{ queueLimit: number; activityLimit: number; resourceLimit: number; joinMs: number }> = {}) {
    if (!runId || !runEpoch) throw new Error('invalid-run-scope');
    this.motion = motion;
    this.limits = { queueLimit: 8, activityLimit: 256, resourceLimit: 64, joinMs: 1000, ...options };
    for (const n of Object.values(this.limits)) if (!Number.isSafeInteger(n) || n < 1) throw new Error('invalid-limit');
    this.root = Object.freeze({ runId, runEpoch, activityId: randomUUID() });
    this.add(this.root, undefined, () => {});
  }
  private add(scope: ActivityScope, parent: string | undefined, handler: Activity['handler']) {
    this.activities.set(scope.activityId, { scope, parent, handler, live: true, uncertain: false, abort: new AbortController(), queue: [], tasks: new Set(), cleanups: new Set() });
  }
  private record(s: ActivityScope): Activity {
    const a = this.activities.get(s.activityId);
    if (!a || s.runId !== this.root.runId || s.runEpoch !== this.root.runEpoch) throw new Error('stale-scope');
    return a;
  }
  private live(s: ActivityScope) { const a = this.record(s); if (!a.live) throw new Error('activity-closed'); return a; }
  private room(a: Activity, count = 1) { if (a.tasks.size + a.cleanups.size + count > this.limits.resourceLimit) throw new Error('resource-capacity'); }
  activity(parent: ActivityScope, handler: Activity['handler'] = () => {}): ActivityScope {
    this.live(parent);
    if (this.activities.size >= this.limits.activityLimit) throw new Error('activity-capacity');
    const scope = Object.freeze({ ...this.root, activityId: randomUUID() });
    this.add(scope, parent.activityId, handler); return scope;
  }
  /** Small high-level facade; no raw transport or unscoped stop is exposed. */
  capabilities(s: ActivityScope) {
    this.live(s);
    return { move: (goal: MotionGoal) => this.move(s, goal),
      prompt: (choices: string[]) => this.prompt(s, choices),
      after: (ms: number, event: ActivityEvent) => this.after(s, ms, event),
      subscribe: (dispose: () => unknown) => this.subscribe(s, dispose),
      spawn: (handler?: Activity['handler']) => this.activity(s, handler) };
  }
  send(to: ActivityScope, event: ActivityEvent) {
    const a = this.live(to);
    if (a.queue.length >= this.limits.queueLimit) throw new Error('queue-full');
    if (!event.type) throw new Error('invalid-event');
    a.queue.push(structuredClone(event));
    if (!this.scheduled) this.scheduled = setImmediate(() => { this.scheduled = undefined; this.dispatch(); });
  }
  dispatch() {
    for (const a of [...this.activities.values()]) {
      if (!a.live) continue;
      const event = a.queue.shift(); if (!event) continue;
      try {
        const result = a.handler(event);
        if (result && typeof (result as PromiseLike<unknown>).then === 'function') {
          void Promise.resolve(result).catch(() => {});
          throw new Error('async-handler-not-supported');
        }
      } catch (e) { this.fail(e); break; }
    }
    if ([...this.activities.values()].some(a => a.live && a.queue.length) && !this.scheduled) {
      this.scheduled = setImmediate(() => { this.scheduled = undefined; this.dispatch(); });
    }
  }
  private fail(error: unknown) {
    this.failure ??= error instanceof Error ? error : new Error(String(error));
    void this.cancel(this.root).catch(e => { this.failure ??= e; });
  }
  private track<T>(a: Activity, task: Promise<T>): Promise<T> {
    a.tasks.add(task);
    void task.then(() => a.tasks.delete(task), () => a.tasks.delete(task));
    return task;
  }
  move(s: ActivityScope, goal: MotionGoal): Promise<MotionResult> {
    const a = this.live(s); this.room(a);
    let task: Promise<MotionResult>;
    try { task = this.motion.move(a.scope, goal, a.abort.signal); }
    catch (e) { this.fail(e); throw e; }
    this.track(a, task);
    void task.then(result => {
      if (result.kind === 'terminal' && result.outcome === 'stop-unconfirmed') { a.uncertain = true; this.fail(new Error('stop-unconfirmed')); }
    }, error => { a.uncertain = true; this.fail(error); });
    return task;
  }
  subscribe(s: ActivityScope, dispose: () => unknown): () => void {
    const a = this.live(s); this.room(a); a.cleanups.add(dispose);
    return () => { if (a.cleanups.delete(dispose)) { const task = Promise.resolve().then(dispose); this.track(a, task); void task.catch(e => this.fail(e)); } };
  }
  after(s: ActivityScope, ms: number, event: ActivityEvent): () => void {
    const a = this.live(s); this.room(a);
    if (!Number.isFinite(ms) || ms < 0 || ms > 2_147_483_647) throw new Error('invalid-delay');
    const copy = structuredClone(event);
    const timer = setTimeout(() => {
      this.timers.delete(timer); a.cleanups.delete(dispose);
      if (a.live) { try { this.send(s, copy); } catch (e) { this.fail(e); } }
    }, ms);
    const dispose = () => { clearTimeout(timer); this.timers.delete(timer); a.cleanups.delete(dispose); };
    this.timers.add(timer); a.cleanups.add(dispose); return dispose;
  }
  prompt(s: ActivityScope, choices: string[]): { id: string; result: Promise<string> } {
    const a = this.live(s); this.room(a, 2);
    if (!choices.length || choices.some(c => typeof c !== 'string' || !c)) throw new Error('invalid-choices');
    const id = randomUUID(); let resolve!: (s: string) => void; let reject!: (e: Error) => void;
    const result = new Promise<string>((ok, no) => { resolve = ok; reject = no; });
    const dispose = () => { this.prompts.delete(id); a.cleanups.delete(dispose); reject(new CancelledPrompt('prompt-cancelled')); };
    a.cleanups.add(dispose); this.prompts.set(id, { owner: a, choices: [...choices], resolve, dispose });
    return { id, result: this.track(a, result) };
  }
  answer(id: string, value: string) {
    const p = this.prompts.get(id); if (!p || !p.owner.live) throw new Error('stale-prompt');
    if (!p.choices.includes(value)) throw new Error('invalid-answer');
    this.prompts.delete(id); p.owner.cleanups.delete(p.dispose); p.resolve(value);
    // An ordinary answer is never human-clearance authority; Python owns handover guards.
  }
  cancel(scope: ActivityScope): Promise<void> {
    const start = this.record(scope); if (start.done) return start.done;
    const members = [...this.activities.values()].filter(a => {
      let current: Activity | undefined = a;
      while (current) { if (current === start) return true; current = current.parent ? this.activities.get(current.parent) : undefined; }
      return false;
    });
    const prior = [...new Set(members.flatMap(a => a.done ? [a.done] : []))];
    const fresh = members.filter(a => !a.done);
    // Fence the entire subtree before running any callback, resolving a prompt or aborting I/O.
    for (const a of fresh) { a.live = false; a.queue.length = 0; }
    let resolve!: () => void; let reject!: (e: Error) => void;
    const done = new Promise<void>((ok, no) => { resolve = ok; reject = no; });
    for (const a of fresh) a.done = done;
    const cleanup: Promise<unknown>[] = [];
    for (const a of fresh) {
      a.abort.abort();
      for (const dispose of a.cleanups) cleanup.push(Promise.resolve().then(dispose));
      a.cleanups.clear();
    }
    const tasks = fresh.flatMap(a => [...a.tasks]);
    const timeout = setTimeout(() => {
      const error = new Error('cleanup-timeout: stop remains unconfirmed'); this.failure ??= error; reject(error);
    }, this.limits.joinMs);
    void Promise.all([Promise.allSettled(tasks), Promise.allSettled([...prior, ...cleanup])]).then(([work, outcomes]) => {
      clearTimeout(timeout);
      const failures = outcomes.filter(o => o.status === 'rejected');
      const uncertain = fresh.some(a => a.uncertain) || work.some(o => o.status === 'rejected' && !(o.reason instanceof CancelledPrompt));
      if (failures.length || uncertain) { const error = new Error('cleanup-failed'); this.failure ??= error; reject(error); }
      else resolve();
    });
    if (scope.activityId === this.root.activityId) { clearImmediate(this.scheduled); this.scheduled = undefined; }
    void done.catch(() => {}); return done;
  }
  snapshot() {
    return { activities: [...this.activities.values()].filter(a => a.live).length,
      prompts: this.prompts.size, timers: this.timers.size,
      pending: [...this.activities.values()].reduce((n, a) => n + a.tasks.size, 0), failure: this.failure?.message ?? null };
  }
}
