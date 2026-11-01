import { useState } from "react";
import type { PersonMotion } from "../simulation/manualPerson";

interface Props {
  enabled: boolean;
  visible: boolean;
  motion: PersonMotion;
  speed: number;
  onMotion(motion: PersonMotion): void;
  onPlace(action: "enter" | "leave" | "reset"): void;
  onSpeed(speed: number): void;
  onSay(text: string): void;
}
export function ManualPersonPanel({ enabled, visible, motion, speed, onMotion, onPlace, onSpeed, onSay }: Props) {
  const [text, setText] = useState("");
  return <section className="manual-person" aria-label="Test person">
    <h3>Test person</h3>
    <p role="status">{visible ? "In view" : "Outside view"} · {motion === "still" ? "Standing" : "Walking"}</p>
    <fieldset disabled={!enabled}>
      <div className="scene-toolbar">
        <button className="button" onClick={() => onPlace("enter")}>Enter view</button>
        <button className="button" onClick={() => onPlace("leave")}>Leave view</button>
        <button className="button" onClick={() => onPlace("reset")}>Reset person</button>
      </div>
      <div className="scene-toolbar" role="group" aria-label="Person movement">
        {([ ["away", "Move away"], ["closer", "Come closer"], ["left", "Walk left"], ["right", "Walk right"], ["still", "Stand still"] ] as const).map(([value, label]) =>
          <button className="button" key={value} aria-pressed={motion === value} onClick={() => onMotion(value)}>{label}</button>)}
      </div>
      <label>Walking speed: {speed.toFixed(2)} m/s
        <input aria-label="Person walking speed" type="range" min="0.05" max="0.3" step="0.01" value={speed} onChange={e => onSpeed(e.currentTarget.valueAsNumber)} />
      </label>
      <form className="scene-toolbar" onSubmit={event => { event.preventDefault(); if (text.trim()) { onSay(text.trim()); setText(""); } }}>
        <label>Person says<input aria-label="Person says" value={text} maxLength={300} onChange={e => setText(e.target.value)} /></label>
        <button className="button" type="submit" disabled={!text.trim()}>Say</button>
      </form>
    </fieldset>
  </section>;
}
