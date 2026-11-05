// Single fake robot. No hardware transport. All host deadlines use monotonic seconds.
export const limits = { ttl: 0.25, lease: 0.4, progress: 1, stop: 0.2 } as const;
export type MotionToken = { session: string; generation: number };
export type Terminal = { token: MotionToken; status: 'completed' | 'cancelled' | 'interrupted' | 'stop-unconfirmed'; reason: string };
type Active = { token: MotionToken; due: number; expires: number; deadline: number };
type Stopping = { active: Active; status: Terminal['status']; reason: string; evidenceAt: number; deadline: number };
export class Gateway {
  private serial = 0;
  private session?: string;
  private leaseUntil = 0;
  private active?: Active;
  private stopping?: Stopping;
  private guard?: string;
  private inhibited = false;
  private pause = false;
  private virtualTime = 0;
  private last: number;
  // Fake evidence/progress injection only, not an adapter contract.
  evidenceDelay = 0;
  stalled = false;
  terminal: (event: Terminal) => void = () => {};
  revoked: (reason: string) => void = () => {};
  now: () => number;
  constructor(now: () => number) { this.now = now; this.last = now(); }
  admit() {
    this.tick();
    if (this.session || this.active || this.stopping || this.inhibited || this.guard) throw new Error('admission-inhibited');
    this.session = 'session-' + ++this.serial;
    this.leaseUntil = this.now() + limits.lease;
    return this.session;
  }
  private valid(session: string) {
    this.tick();
    if (!session || session !== this.session) throw new Error('revoked-session');
  }
  heartbeat(session: string) { this.valid(session); this.leaseUntil = this.now() + limits.lease; }
  begin(session: string, duration: number): MotionToken {
    this.valid(session);
    if (!Number.isFinite(duration) || duration <= 0 || duration > limits.progress) throw new Error('invalid-duration');
    if (this.active || this.stopping || this.guard || this.inhibited) throw new Error('motion-inhibited');
    const token = { session, generation: ++this.serial };
    this.active = { token, due: this.virtualTime + duration, expires: this.now() + limits.ttl,
      deadline: this.virtualTime + limits.progress };
    return { ...token };
  }
  private matches(t: MotionToken) {
    return this.active?.token.session === t.session && this.active.token.generation === t.generation;
  }
  renew(t: MotionToken) {
    this.valid(t.session);
    if (!this.matches(t) || this.stopping) throw new Error('stale-motion');
    this.active!.expires = this.now() + limits.ttl;
  }
  stop(t: MotionToken) {
    this.valid(t.session);
    if (!this.matches(t) || this.stopping) throw new Error('stale-motion');
    this.requestStop('cancelled', 'scoped-stop');
  }
  hold(session: string) {
    this.valid(session);
    if (this.active || this.stopping || this.guard || this.inhibited) throw new Error('not-stationary');
    this.guard = session;
  }
  clear(session: string, confirmed: boolean) {
    this.valid(session);
    if (this.guard !== session || confirmed !== true) throw new Error('clearance-required');
    this.guard = undefined;
  }
  revoke(reason: string) {
    const hadSession = !!this.session;
    this.session = undefined;
    this.requestStop('interrupted', reason);
    if (hadSession) this.revoked(reason);
  }
  recover(confirmed: boolean) {
    this.tick();
    if (!confirmed || this.session || this.active || this.stopping) throw new Error('recovery-not-ready');
    // Explicit fake operator assertion of standstill AND human clearance.
    this.inhibited = false; this.guard = undefined;
  }
  setPause(paused: boolean) { this.tick(); this.pause = paused; }
  private requestStop(status: Terminal['status'], reason: string) {
    if (!this.active) return;
    if (this.stopping) {
      // Revocation wins over a goal reached while stop evidence is still pending.
      if (status === 'interrupted' && this.stopping.status !== 'interrupted') {
        this.stopping.status = status; this.stopping.reason = reason;
      }
      return;
    }
    this.stopping = { active: this.active, status, reason,
      evidenceAt: this.now() + this.evidenceDelay, deadline: this.now() + limits.stop };
  }
  tick() {
    const now = this.now();
    if (!this.pause) this.virtualTime += Math.max(0, now - this.last);
    this.last = now;
    if (this.session && now >= this.leaseUntil) this.revoke('lease-expired');
    if (this.active && !this.stopping) {
      if (now >= this.active.expires) this.revoke('command-ttl');
      else if (this.virtualTime >= this.active.deadline) this.revoke('progress-deadline');
      else if (!this.stalled && this.virtualTime >= this.active.due) this.requestStop('completed', 'virtual-goal');
    }
    const stopping = this.stopping;
    if (stopping && (now >= stopping.evidenceAt || now >= stopping.deadline)) {
      const confirmed = stopping.evidenceAt <= stopping.deadline && now >= stopping.evidenceAt;
      this.active = undefined; this.stopping = undefined;
      if (!confirmed) { this.inhibited = true; this.session = undefined; }
      this.terminal({ token: stopping.active.token, status: confirmed ? stopping.status : 'stop-unconfirmed',
        reason: confirmed ? stopping.reason : 'stop-evidence-timeout' });
      if (!confirmed) this.revoked('stop-unconfirmed');
    }
  }
  snapshot() {
    this.tick();
    return { target: 'fake-only', session: this.session, owner: this.active?.token,
      moving: !!this.active && !this.stopping && !this.pause, stopping: !!this.stopping,
      inhibited: this.inhibited, guard: this.guard, paused: this.pause, virtualTime: this.virtualTime };
  }
}
