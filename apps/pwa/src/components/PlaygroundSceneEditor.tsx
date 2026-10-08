import type { PlaygroundScene } from "../simulation/playgroundScene";
import { scenePreset } from "../simulation/playgroundScene";

interface Props {
  scene: PlaygroundScene;
  disabled: boolean;
  onChange: (scene: PlaygroundScene) => void;
  onSave: () => void;
  onLoad: () => void;
  notice: string;
}

export function PlaygroundSceneEditor({ scene, disabled, onChange, onSave, onLoad, notice }: Props) {
  return <section className="scene-editor" aria-label="Test scene">
    <h3>Test scene</h3>
    <fieldset disabled={disabled}>
      <div className="playground-actions">
        {(["front", "behind", "missing"] as const).map((kind) => <button className="button button--quiet" key={kind}
          onClick={() => onChange(scenePreset(kind))}>{kind === "front" ? "In view" : kind === "behind" ? "Behind rover" : "Not visible"}</button>)}
      </div>
      {(["origin", "visitor", "entrance", "desk"] as const).map((key) => <div className="scene-coordinates" key={key}>
        <strong>{key === "origin" ? "Rover" : key === "visitor" ? "Visitor" : key === "entrance" ? "Entrance" : "Desk"}</strong>
        {(["x", "y"] as const).map((axis) => <label key={axis}>{axis} (m)<input type="number" min={-10} max={10} step={.05}
          aria-label={`${key} ${axis}`} value={scene[key][axis]} onChange={(event) => {
            const value = event.target.valueAsNumber;
            if (Number.isFinite(value) && Math.abs(value) <= 10) onChange({ ...scene, [key]: { ...scene[key], [axis]: value } });
          }} /></label>)}
      </div>)}
      <label>Rover heading (degrees)<input type="number" min={-180} max={180} step={5}
        value={Math.round(scene.origin.yaw * 180 / Math.PI)} onChange={(event) => {
          const value = event.target.valueAsNumber;
          if (Number.isFinite(value) && Math.abs(value) <= 180) onChange({ ...scene, origin: { ...scene.origin, yaw: value * Math.PI / 180 } });
        }} /></label>
      <label><input type="checkbox" checked={scene.hidden} onChange={(event) => onChange({ ...scene, hidden: event.target.checked })} />Marker initially hidden</label>
      <label><input type="checkbox" checked={scene.blocked} onChange={(event) => onChange({ ...scene, blocked: event.target.checked })} />Path initially blocked</label>
      <div className="playground-actions"><button className="button button--quiet" onClick={onSave}>Save scene</button><button className="button button--quiet" onClick={onLoad}>Load scene</button></div>
    </fieldset>
    {notice && <p role="status">{notice}</p>}
  </section>;
}
