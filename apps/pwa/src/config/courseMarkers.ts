export type CourseDestination = "desk" | "kitchen" | "entrance";

export interface CourseMarker {
  id: number;
  label: string;
  destination?: CourseDestination;
  xM: number;
  yM: number;
  yawDeg: number;
}

/**
 * Known marker poses in the course coordinate system.
 * Replace this example when the event course is measured.
 */
export const courseMarkers: readonly CourseMarker[] = [
  { id: 1, label: "Entrance", destination: "entrance", xM: 0, yM: 0, yawDeg: 0 },
  { id: 2, label: "Desk", destination: "desk", xM: 2, yM: 0, yawDeg: 180 },
  { id: 3, label: "Kitchen", destination: "kitchen", xM: 0, yM: 2, yawDeg: -90 }
];
