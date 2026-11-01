export interface FollowTuning {
  targetWidth: number;
  widthDeadband: number;
  bearingDeadband: number;
  distanceGain: number;
  bearingGain: number;
  maxSpeed: number;
  maxTurn: number;
  acceleration: number;
  deceleration: number;
  angularAcceleration: number;
  staleAfter: number;
}

export const defaultFollowTuning: Readonly<FollowTuning> = {
  targetWidth: 0.6, widthDeadband: 0.03, bearingDeadband: 0.04,
  distanceGain: 0.6, bearingGain: 1.2, maxSpeed: 0.15, maxTurn: 0.2,
  acceleration: 0.12, deceleration: 0.3, angularAcceleration: 0.5,
  staleAfter: 1.8
};

export interface FollowObservation {
  width: number;
  /** Robot-frame bearing in radians: positive is left. */
  bearing: number;
  observedAt: number;
}

export interface FollowVelocity { vx: number; wz: number }
const clamp = (v: number, low: number, high: number) => Math.min(high, Math.max(low, v));
const deadband = (v: number, band: number) => Math.sign(v) * Math.max(0, Math.abs(v) - band);
const slew = (current: number, target: number, delta: number) =>
  current + clamp(target - current, -delta, delta);

/** Pure controller. Caller owns command leases, permissions and observation identity. */
export class ContinuousFollowController {
  private velocity: FollowVelocity = { vx: 0, wz: 0 };
  constructor(readonly tuning: Readonly<FollowTuning> = defaultFollowTuning) {
    if (Object.values(tuning).some(v => !Number.isFinite(v) || v <= 0)
      || tuning.targetWidth > 1) throw new Error("Invalid follow tuning");
  }

  reset(): FollowVelocity {
    this.velocity = { vx: 0, wz: 0 };
    return { ...this.velocity };
  }

  step(person: FollowObservation | null, now: number, dt: number, allowed: boolean): FollowVelocity {
    if (!allowed || !person || !Number.isFinite(now) || !Number.isFinite(dt)
      || dt <= 0 || dt > 0.25 || !Number.isFinite(person.width)
      || person.width <= 0 || person.width > 1 || !Number.isFinite(person.bearing)
      || !Number.isFinite(person.observedAt) || now < person.observedAt
      || now - person.observedAt > this.tuning.staleAfter) return this.reset();
    const t = this.tuning;
    const turn = clamp(t.bearingGain * deadband(person.bearing, t.bearingDeadband), -t.maxTurn, t.maxTurn);
    const forward = clamp(t.distanceGain * deadband(t.targetWidth - person.width, t.widthDeadband), 0, t.maxSpeed)
      * Math.max(0, Math.cos(person.bearing));
    this.velocity = {
      vx: slew(this.velocity.vx, forward, dt * (forward > this.velocity.vx ? t.acceleration : t.deceleration)),
      wz: slew(this.velocity.wz, turn, dt * t.angularAcceleration)
    };
    return { ...this.velocity };
  }
}
