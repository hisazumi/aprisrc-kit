export interface TeamProfile {
  teamName: string;
  serviceName: string;
  defaultMissionId: string;
}

/** Change these values for a service prototype without editing platform code. */
export const teamProfile: TeamProfile = {
  teamName: "APRIS Prototype Team",
  serviceName: "Rover Service",
  defaultMissionId: "challenger-starter"
};
