import { useEffect, useState } from "react";

import type { RoverState } from "../protocol";

export interface CommandedVelocity {
  sampleId: number;
  vx: number;
  wz: number;
}

interface MotionTraceProps {
  command?: CommandedVelocity;
  state: RoverState | null;
}

interface TraceSample {
  at: number;
  commandedVx: number;
  commandedWz: number;
  observedVx: number;
  observedWz: number;
}

const WINDOW_MS = 12_000;
const WIDTH = 760;
const HEIGHT = 178;
const LEFT = 54;
const RIGHT = 14;
const TOP = 12;
const BOTTOM = 28;

function tracePath(
  samples: TraceSample[],
  value: (sample: TraceSample) => number,
  maximum: number,
): string {
  if (samples.length === 0) return "";
  const end = samples.at(-1)?.at ?? 0;
  const start = end - WINDOW_MS;
  const x = (at: number) => LEFT + ((at - start) / WINDOW_MS) * (WIDTH - LEFT - RIGHT);
  const y = (next: number) =>
    TOP + ((maximum - next) / (maximum * 2)) * (HEIGHT - TOP - BOTTOM);
  return samples
    .map((sample, index) => `${index === 0 ? "M" : "L"}${x(sample.at).toFixed(1)},${y(value(sample)).toFixed(1)}`)
    .join(" ");
}

function TracePlot({
  samples,
  title,
  maximum,
  commanded,
  observed,
}: {
  samples: TraceSample[];
  title: string;
  maximum: number;
  commanded?: (sample: TraceSample) => number;
  observed: (sample: TraceSample) => number;
}) {
  const plotWidth = WIDTH - LEFT - RIGHT;
  const plotHeight = HEIGHT - TOP - BOTTOM;
  const yFor = (value: number) => TOP + ((maximum - value) / (maximum * 2)) * plotHeight;

  return (
    <div className="motion-trace__plot">
      <strong>{title}</strong>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title} over 12 seconds`}>
        <rect className="motion-trace__frame" x={LEFT} y={TOP} width={plotWidth} height={plotHeight} />
        {[-maximum, 0, maximum].map((value) => (
          <g key={value}>
            <line className="motion-trace__grid" x1={LEFT} x2={WIDTH - RIGHT} y1={yFor(value)} y2={yFor(value)} />
            <text className="motion-trace__axis" x={LEFT - 8} y={yFor(value) + 4} textAnchor="end">
              {value.toFixed(1)}
            </text>
          </g>
        ))}
        {[0, 3, 6, 9, 12].map((seconds) => {
          const x = LEFT + (seconds / 12) * plotWidth;
          return (
            <g key={seconds}>
              <line className="motion-trace__grid motion-trace__grid--vertical" x1={x} x2={x} y1={TOP} y2={HEIGHT - BOTTOM} />
              <text className="motion-trace__axis" x={x} y={HEIGHT - 9} textAnchor={seconds === 0 ? "start" : seconds === 12 ? "end" : "middle"}>
                {seconds - 12}s
              </text>
            </g>
          );
        })}
        {commanded && <path className="motion-trace__line motion-trace__line--commanded" d={tracePath(samples, commanded, maximum)} />}
        <path className="motion-trace__line motion-trace__line--observed" d={tracePath(samples, observed, maximum)} />
      </svg>
    </div>
  );
}

export function MotionTrace({ command, state }: MotionTraceProps) {
  const [samples, setSamples] = useState<TraceSample[]>([]);

  useEffect(() => {
    if (!state) return;
    const at = performance.now();
    const next: TraceSample = {
      at,
      commandedVx: command?.vx ?? 0,
      commandedWz: command?.wz ?? 0,
      observedVx: state.velocity.vx,
      observedWz: state.velocity.wz,
    };
    setSamples((current) => [...current.filter((sample) => at - sample.at <= WINDOW_MS), next]);
  }, [command?.sampleId, state]);

  return (
    <article className="panel motion-trace">
      <div className="panel__heading">
        <div>
          <p className="section-label">MOTION TRACE · LAST 12 SECONDS</p>
          <h2>{command ? "Command vs factory feedback" : "Rover velocity estimate"}</h2>
        </div>
        <div className="motion-trace__legend" aria-label="Motion trace legend">
          {command && <span><i className="motion-trace__swatch motion-trace__swatch--commanded" />Command</span>}
          <span><i className="motion-trace__swatch motion-trace__swatch--observed" />Observed</span>
        </div>
      </div>
      <div className="motion-trace__plots">
        <TracePlot
          samples={samples}
          title="Angular velocity (rad/s)"
          maximum={1.2}
          commanded={command ? (sample) => sample.commandedWz : undefined}
          observed={(sample) => sample.observedWz}
        />
        <TracePlot
          samples={samples}
          title="Linear velocity (m/s)"
          maximum={0.3}
          commanded={command ? (sample) => sample.commandedVx : undefined}
          observed={(sample) => sample.observedVx}
        />
      </div>
    </article>
  );
}
