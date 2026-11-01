import { useRef, useState } from "react";
import { parseStudentScene, studentScenes, type StudentScene, type SceneStep, type SceneFrame } from "../simulation/studentScene";

interface Props {
  scene: StudentScene;
  onChange(scene: StudentScene): void;
}
const actionNames = { walk: "Walk", stand: "Stand", disappear: "Disappear" };

export function StudentSceneExecution({ scene, frame, active, onNext }: {
  scene: StudentScene; frame: SceneFrame; active: boolean; onNext(): void;
}) {
  const label = !active ? "Trial ended" : frame.phase === "complete" ? "All steps finished"
    : frame.phase === "walking" ? "Walking..." : !frame.manual ? "Waiting for timer..."
    : `Next: ${actionNames[scene.steps[frame.index].action]}`;
  return <div aria-label="Trial execution">
    <h3>{active ? "Running" : "Last trial"}: {scene.name}</h3>
    <p role="status">{frame.phase === "complete" ? "Scene actions complete" :
      `Step ${frame.index + 1} / ${scene.steps.length}: ${!active ? "Stopped" : frame.manual ? "Waiting for Next step" : frame.phase === "walking" ? "Walking" : "Waiting for timer"}`}</p>
    <ol aria-label="Trial sequence">{scene.steps.map((step, index) => <li key={index}
      aria-current={active && frame.index === index ? "step" : undefined}>
      {actionNames[step.action]} · {index < frame.index ? "Done" : frame.index === index && frame.phase === "walking" && active ? "In progress" : "Pending"}
    </li>)}</ol>
    <button className="button" aria-label="Next step" disabled={!active || !frame.manual} onClick={onNext}>{label}</button>
    <ul>{scene.checks.map((check, index) => <li key={index}>{check}</li>)}</ul>
  </div>;
}

export function StudentScenePanel({ scene, onChange }: Props) {
  const upload = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");
  const change = (next: StudentScene) => { setFileError(""); onChange(next); };
  const stepChange = (index: number, update: Partial<SceneStep>) => change({ ...scene,
    steps: scene.steps.map((step, i) => i === index ? { ...step, ...update } : step) });
  const numeric = (label: string, value: number, update: (value: number) => void, min: number, max: number, step = 0.1) =>
    <label>{label}<input type="number" aria-label={label} value={Number.isFinite(value) ? value : ""} min={min} max={max} step={step}
      onChange={event => update(event.currentTarget.valueAsNumber)} /></label>;
  const download = () => {
    try {
      const valid = parseStudentScene(scene);
      const url = URL.createObjectURL(new Blob([JSON.stringify(valid, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "student-scene.json"; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000); setFileError("");
    } catch (cause) { setFileError(cause instanceof Error ? cause.message : "Invalid scene"); }
  };
  return <section className="student-scene" aria-label="Test scene">
    <h2>Selected scenario</h2>
    <div className="scene-toolbar">
      <label>Preset<select aria-label="Scene preset" value={studentScenes.some(s => s.name === scene.name) ? scene.name : "custom"}
        onChange={event => { const selected = studentScenes.find(s => s.name === event.target.value); if (selected) change(structuredClone(selected)); }}>
        <option value="custom" disabled>Custom</option>
        {studentScenes.map(preset => <option key={preset.name}>{preset.name}</option>)}
      </select></label>
      <button className="button" onClick={download}>Export JSON</button>
      <button className="button" onClick={() => upload.current?.click()}>Import JSON</button>
      <input ref={upload} aria-label="Import scene file" type="file" accept=".json,application/json" hidden
        onChange={async event => {
          const file = event.currentTarget.files?.[0]; event.currentTarget.value = "";
          if (!file) return;
          try {
            if (file.size > 64_000) throw new Error("Scene file must be smaller than 64 KB");
            const parsed = parseStudentScene(JSON.parse(await file.text()));
            change(parsed);
          } catch (cause) { setFileError(cause instanceof Error ? cause.message : "Invalid scene file"); }
        }} />
    </div>
    {fileError && <p role="alert">{fileError}</p>}
    {scene.steps.length === 0 ? <p>Stationary scene · No movement steps</p> :
      <ol aria-label="Scene sequence">{scene.steps.map((step, index) => <li key={index}>
        <strong>{actionNames[step.action]}</strong>
        {step.action === "walk" && ` · ${step.points.length} waypoint(s) · ${step.speedMps} m/s`}
        {` · ${step.trigger.type === "manual" ? "Manual" : `${step.trigger.seconds} s delay`}`}
      </li>)}</ol>}
    <ul>{scene.checks.map((check, i) => <li key={i}>{check}</li>)}</ul>
    <details><summary>Edit scene</summary>
      <fieldset>
        <label>Name<input value={scene.name} onChange={e => change({ ...scene, name: e.target.value })} /></label>
        <div className="scene-fields">
          {numeric("Rover x (m)", scene.rover.x, x => change({ ...scene, rover: { ...scene.rover, x } }), -10, 10)}
          {numeric("Rover y (m)", scene.rover.y, y => change({ ...scene, rover: { ...scene.rover, y } }), -10, 10)}
          {numeric("Rover heading (deg)", Math.round(scene.rover.yaw * 180 / Math.PI), deg => change({ ...scene, rover: { ...scene.rover, yaw: deg * Math.PI / 180 } }), -180, 180, 1)}
          {numeric("Person x (m)", scene.person.x, x => change({ ...scene, person: { ...scene.person, x } }), -10, 10)}
          {numeric("Person y (m)", scene.person.y, y => change({ ...scene, person: { ...scene.person, y } }), -10, 10)}
        </div>
        <ol className="scene-steps">{scene.steps.map((step, index) => <li key={index}>
          <div className="scene-fields">
            <label>Action<select aria-label={`Step ${index + 1} action`} value={step.action} onChange={e => stepChange(index, {
              action: e.target.value as SceneStep["action"], points: step.points.length ? step.points : [{ ...scene.person }]
            })}><option value="walk">Walk</option><option value="stand">Stand</option><option value="disappear">Disappear</option></select></label>
            <label>Start<select aria-label={`Step ${index + 1} start`} value={step.trigger.type} onChange={e => stepChange(index, {
              trigger: e.target.value === "manual" ? { type: "manual" } : { type: "delay", seconds: 2 }
            })}><option value="manual">Next step</option><option value="delay">After delay</option></select></label>
            {step.trigger.type === "delay" && numeric(`Step ${index + 1} delay (s)`, step.trigger.seconds,
              seconds => stepChange(index, { trigger: { type: "delay", seconds } }), 0, 120)}
            {step.action === "walk" && numeric(`Step ${index + 1} speed (m/s)`, step.speedMps,
              speedMps => stepChange(index, { speedMps }), 0.01, 0.5, 0.01)}
          </div>
          {step.action === "walk" && <div>{step.points.map((point, p) => <div className="scene-fields" key={p}>
            {numeric(`Step ${index + 1} point ${p + 1} x (m)`, point.x,
              x => stepChange(index, { points: step.points.map((v, j) => j === p ? { ...v, x } : v) }), -10, 10)}
            {numeric(`Step ${index + 1} point ${p + 1} y (m)`, point.y,
              y => stepChange(index, { points: step.points.map((v, j) => j === p ? { ...v, y } : v) }), -10, 10)}
            <button className="button" disabled={step.points.length === 1} onClick={() => stepChange(index, { points: step.points.filter((_, j) => j !== p) })}>Remove point</button>
          </div>)}<button className="button" disabled={step.points.length >= 20} onClick={() => stepChange(index, { points: [...step.points, { ...step.points.at(-1)! }] })}>Add waypoint</button></div>}
          <button className="button" onClick={() => change({ ...scene, steps: scene.steps.filter((_, i) => i !== index) })}>Remove step</button>
        </li>)}</ol>
        <button className="button" disabled={scene.steps.length >= 20} onClick={() => change({ ...scene, steps: [...scene.steps,
          { action: "walk", trigger: { type: "manual" }, speedMps: 0.1, points: [{ ...scene.person }] }] })}>Add step</button>
        <label>Checks<textarea rows={3} value={scene.checks.join("\n")} onChange={e => change({ ...scene, checks: e.target.value.split("\n") })} /></label>
      </fieldset>
    </details>
  </section>;
}
