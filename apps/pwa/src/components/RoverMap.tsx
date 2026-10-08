import type { Pose } from "../protocol";
import type { VirtualPersonTarget } from "../simulation/virtualPerson";

interface RoverMapProps {
  pose: Pose | null;
  path: Pose[];
  person?: VirtualPersonTarget | null;
  markers?: readonly { id: number; label: string; x: number; y: number; selected: boolean; visible: boolean }[];
  focusTarget?: VirtualPersonTarget | null;
}

const WIDTH = 620;
const HEIGHT = 420;
const SCALE = 90;

interface MapCenter {
  x: number;
  y: number;
}

function mapCenter(pose: Pose | null, person: VirtualPersonTarget | null): MapCenter {
  if (pose && person) {
    return {
      x: (pose.x + person.x) / 2,
      y: (pose.y + person.y) / 2
    };
  }
  if (pose) return { x: pose.x, y: pose.y };
  if (person) return { x: person.x, y: person.y };
  return { x: 0, y: 0 };
}

function screenPoint(pose: Pose, center: Readonly<MapCenter>, scale = SCALE): { x: number; y: number } {
  return {
    x: WIDTH / 2 - (pose.y - center.y) * scale,
    y: HEIGHT / 2 - (pose.x - center.x) * scale
  };
}

export function RoverMap({ pose, path, person = null, markers = [], focusTarget = null }: RoverMapProps) {
  let center = mapCenter(pose, focusTarget ?? person);
  let scale = SCALE;
  if (markers.length) {
    const objects = [...markers, ...(pose ? [pose] : []), ...(person ? [person] : [])];
    const minX = Math.min(...objects.map((p) => p.x)), maxX = Math.max(...objects.map((p) => p.x));
    const minY = Math.min(...objects.map((p) => p.y)), maxY = Math.max(...objects.map((p) => p.y));
    center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
    scale = Math.min(SCALE, (HEIGHT - 140) / Math.max(1, maxX - minX), (WIDTH - 140) / Math.max(1, maxY - minY));
  }
  const point = pose ? screenPoint(pose, center, scale) : { x: WIDTH / 2, y: HEIGHT / 2 };
  const personPoint = person
    ? screenPoint({ x: person.x, y: person.y, yaw: 0 }, center, scale)
    : null;
  const points = path.map((item) => {
    const screen = screenPoint(item, center, scale);
    return `${screen.x},${screen.y}`;
  });
  const yawDegrees = pose ? (-pose.yaw * 180) / Math.PI : 0;
  const worldOrigin = screenPoint({ x: 0, y: 0, yaw: 0 }, center, scale);

  return (
    <svg className="rover-map" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-label="Simulated rover map">
      <defs>
        <pattern id="small-grid" width={scale / 2} height={scale / 2} patternUnits="userSpaceOnUse">
          <path d={`M ${scale / 2} 0 L 0 0 0 ${scale / 2}`} fill="none" stroke="rgba(21,37,31,.08)" strokeWidth="1" />
        </pattern>
        <pattern id="grid" width={scale} height={scale} patternUnits="userSpaceOnUse">
          <rect width={scale} height={scale} fill="url(#small-grid)" />
          <path d={`M ${scale} 0 L 0 0 0 ${scale}`} fill="none" stroke="rgba(21,37,31,.16)" strokeWidth="1.5" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#grid)" />
      <line x1={worldOrigin.x} y1="0" x2={worldOrigin.x} y2={HEIGHT} className="map-axis" />
      <line x1="0" y1={worldOrigin.y} x2={WIDTH} y2={worldOrigin.y} className="map-axis" />
      {points.length > 1 && <polyline points={points.join(" ")} className="map-path" />}
      {markers.map((marker) => {
        const at = screenPoint({ x: marker.x, y: marker.y, yaw: 0 }, center, scale);
        return <g key={marker.id} transform={`translate(${at.x} ${at.y})`}
          className={`map-marker ${marker.selected ? "map-marker--selected" : ""} ${marker.visible ? "" : "map-marker--hidden"}`}
          aria-label={`${marker.label} marker ${marker.id}${marker.visible ? "" : " hidden"}`}>
          <rect x="-16" y="-16" width="32" height="32" rx="2" />
          <text textAnchor="middle" y="5">{marker.id}</text>
          <text textAnchor="middle" y="34">{marker.label}</text>
        </g>;
      })}
      {personPoint && (
        <g className="map-person" transform={`translate(${personPoint.x} ${personPoint.y})`}>
          <circle r="19" />
          <path d="M -15 28 C -13 10 13 10 15 28" />
          <text x="42" y="0">person</text>
        </g>
      )}
      <g transform={`translate(${point.x} ${point.y}) rotate(${yawDegrees})`}>
        <circle r="24" className="rover-body" />
        <path d="M 0 -28 L -11 -8 L 11 -8 Z" className="rover-heading" />
        <line x1="-19" y1="0" x2="19" y2="0" className="rover-axle" />
      </g>
      <text x="18" y="28" className="map-label">1 square = 0.5 m</text>
      <text x={WIDTH / 2 + 8} y="22" className="map-label">forward +x</text>
    </svg>
  );
}
