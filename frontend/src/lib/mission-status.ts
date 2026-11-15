import type { MissionStatus } from "@/types";

/** The only allowed mission status changes. */
export const STATUS_TRANSITIONS: Record<MissionStatus, MissionStatus[]> = {
  DRAFT: ["PLANNED"],
  PLANNED: ["FINALIZED", "DRAFT"],
  FINALIZED: [],
};

export function canTransition(from: MissionStatus, to: MissionStatus): boolean {
  return STATUS_TRANSITIONS[from].includes(to);
}
