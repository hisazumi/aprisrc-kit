import { useCallback, useEffect, useRef, useState } from "react";

interface JoystickProps {
  disabled: boolean;
  onDrive: (vx: number, wz: number) => void;
  onStop: () => void;
}

interface Vector {
  x: number;
  y: number;
}

export const JOYSTICK_DEAD_ZONE = 0.08;
export const JOYSTICK_TRANSMIT_INTERVAL_MS = 200;

export function applyJoystickDeadZone(vector: Vector): Vector {
  const snapped = {
    x: Math.abs(vector.x) <= JOYSTICK_DEAD_ZONE ? 0 : vector.x,
    y: Math.abs(vector.y) <= JOYSTICK_DEAD_ZONE ? 0 : vector.y,
  };
  const magnitude = Math.hypot(snapped.x, snapped.y);
  if (magnitude <= JOYSTICK_DEAD_ZONE) return { x: 0, y: 0 };

  const boundedMagnitude = Math.min(magnitude, 1);
  const remappedMagnitude =
    (boundedMagnitude - JOYSTICK_DEAD_ZONE) / (1 - JOYSTICK_DEAD_ZONE);
  const scale = remappedMagnitude / magnitude;
  return { x: snapped.x * scale, y: snapped.y * scale };
}

export function Joystick({ disabled, onDrive, onStop }: JoystickProps) {
  const padRef = useRef<HTMLDivElement>(null);
  const vectorRef = useRef<Vector>({ x: 0, y: 0 });
  const [vector, setVector] = useState<Vector>({ x: 0, y: 0 });
  const [active, setActive] = useState(false);

  const updateFromPointer = useCallback((clientX: number, clientY: number) => {
    const pad = padRef.current;
    if (!pad) return;
    const rect = pad.getBoundingClientRect();
    const radius = Math.max(1, Math.min(rect.width, rect.height) / 2 - 34);
    let x = (clientX - (rect.left + rect.width / 2)) / radius;
    let y = (clientY - (rect.top + rect.height / 2)) / radius;
    const magnitude = Math.hypot(x, y);
    if (magnitude > 1) {
      x /= magnitude;
      y /= magnitude;
    }
    const next = applyJoystickDeadZone({ x, y });
    vectorRef.current = next;
    setVector(next);
  }, []);

  const stop = useCallback(() => {
    vectorRef.current = { x: 0, y: 0 };
    setVector({ x: 0, y: 0 });
    setActive(false);
    onStop();
  }, [onStop]);

  useEffect(() => {
    if (!active || disabled) return;
    const transmit = () => {
      const current = vectorRef.current;
      const vx = -current.y * 0.3;
      const wz = -current.x * 1.2;
      onDrive(vx, wz);
    };
    transmit();
    const timer = window.setInterval(transmit, JOYSTICK_TRANSMIT_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [active, disabled, onDrive]);

  useEffect(() => {
    if (disabled && active) stop();
  }, [active, disabled, stop]);

  return (
    <div
      ref={padRef}
      className={`joystick ${disabled ? "joystick--disabled" : ""}`}
      role="application"
      aria-label="Virtual joystick"
      onPointerDown={(event) => {
        if (disabled) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        setActive(true);
        updateFromPointer(event.clientX, event.clientY);
      }}
      onPointerMove={(event) => {
        if (!active || disabled) return;
        updateFromPointer(event.clientX, event.clientY);
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
    >
      <span className="joystick__axis joystick__axis--x" />
      <span className="joystick__axis joystick__axis--y" />
      <div
        className="joystick__knob"
        style={{ transform: `translate(${vector.x * 72}px, ${vector.y * 72}px)` }}
      />
      <span className="joystick__label joystick__label--forward">FWD</span>
      <span className="joystick__label joystick__label--left">LEFT</span>
      <span className="joystick__label joystick__label--right">RIGHT</span>
    </div>
  );
}
