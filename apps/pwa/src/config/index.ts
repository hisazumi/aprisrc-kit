import {
  courseMarkers,
  type CourseDestination,
  type CourseMarker
} from "./courseMarkers";
import { teamProfile, type TeamProfile } from "./teamProfile";

export interface ServiceConfig {
  team: TeamProfile;
  courseMarkers: readonly CourseMarker[];
}

export const serviceConfig: ServiceConfig = {
  team: teamProfile,
  courseMarkers
};

export type { CourseDestination, CourseMarker, TeamProfile };
