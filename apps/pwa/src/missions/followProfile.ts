export type FollowProfile = "simulator" | "ironx" | false;

export function selectFollowProfile(adapter: string | null, continuousFollow: string | undefined): FollowProfile {
  if (adapter === "simulator") return "simulator";
  if (adapter === "ironx_network" && continuousFollow !== "0") return "ironx";
  return false;
}

export function followProfileTuning(profile: FollowProfile) {
  if (profile === "simulator") return { maxSpeed: 0.25, distanceGain: 0.8 };
  if (profile === "ironx") return { maxSpeed: 0.15, distanceGain: 0.6 };
  return undefined;
}
